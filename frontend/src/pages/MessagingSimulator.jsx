import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Navbar } from "@/components/Navbar";
import { prettyType, WAGE_BRACKETS, REASON_OPTIONS } from "@/lib/ui";
import { Send, CheckCheck, Bot, Sparkles, ArrowLeft, Loader2 } from "lucide-react";

const STATUS_CHIPS = [
  { key: "employed", label: "Employed" },
  { key: "self_employed", label: "Self-employed" },
  { key: "unemployed", label: "Still searching" },
  { key: "apprentice", label: "In further training" },
];

export default function MessagingSimulator() {
  const { traineeId } = useParams();
  const navigate = useNavigate();
  const [trainee, setTrainee] = useState(null);
  const [followup, setFollowup] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [phase, setPhase] = useState("status"); // status -> wage -> reason -> done
  const [pending, setPending] = useState({});
  const [busy, setBusy] = useState(false);

  const pushSys = (text, extra = {}) => setMessages((m) => [...m, { from: "sys", text, ts: Date.now(), ...extra }]);
  const pushUser = (text) => setMessages((m) => [...m, { from: "user", text, ts: Date.now() }]);
  const pushAI = (node) => setMessages((m) => [...m, { from: "ai", node, ts: Date.now() }]);

  const load = useCallback(async () => {
    const { data } = await api.get(`/trainees/${traineeId}`);
    setTrainee(data.trainee);
    const fu = await api.get(`/followups?trainee_id=${traineeId}`);
    const items = fu.data.items || [];
    const target = items.find((f) => f.status === "pending") || items.find((f) => f.status !== "responded") || items[items.length - 1];
    setFollowup(target || null);
    const interval = (target?.interval_label || "3_month").replace("_", "-");
    setMessages((prev) => prev.length ? prev : [{
      from: "sys", ts: Date.now(),
      text: `Namaste ${data.trainee.full_name.split(" ")[0]}! 🙏 This is SkillTrace checking in (${interval} follow-up). Are you currently:`,
      chips: true,
    }]);
  }, [traineeId]);

  useEffect(() => { load(); }, [load]);

  const finalizeFollowup = async (structured) => {
    if (!followup) return;
    try {
      await api.post(`/followups/${followup.id || followup._id}/respond`, {
        channel_used: "whatsapp", structured_response: structured,
      });
    } catch (e) { /* non-blocking for demo */ }
  };

  const handleStatus = async (statusKey, label) => {
    pushUser(label);
    setPending({ type: statusKey });
    if (statusKey === "employed" || statusKey === "self_employed" || statusKey === "apprentice") {
      pushSys("Great news! 🎉 What is your approximate monthly income?", { wage: true });
      setPhase("wage");
    } else {
      pushSys("Thanks for letting us know. What's the main reason you haven't been placed yet?", { reason: true });
      setPhase("reason");
    }
  };

  const handleWage = async (bracket) => {
    pushUser(bracket);
    setBusy(true);
    const type = pending.type;
    try {
      const { data: emp } = await api.post("/employment", {
        trainee_id: traineeId, type, wage_bracket: bracket,
        employer_name: type === "self_employed" ? "Self-owned" : "Employer (pending verification)",
        sector: trainee?.district ? undefined : undefined,
      });
      await finalizeFollowup({ employment_type: type, wage_bracket: bracket });
      if (type === "employed") {
        const { data: v } = await api.post(`/employment/${emp.id || emp._id}/request-verification`);
        pushAI(
          <div>
            <div className="flex items-center gap-1.5 font-semibold text-emerald-700"><CheckCheck className="h-4 w-4" /> Outcome recorded (Self-Reported)</div>
            <p className="mt-1 text-slate-600">An employer verification link was generated. In production this is sent to the employer over WhatsApp/SMS.</p>
            <button data-testid="open-verify-link-btn" onClick={() => window.open(v.verification_path, "_blank")}
              className="mt-2 inline-flex items-center gap-1.5 text-xs font-semibold rounded-md bg-brand text-white px-3 py-1.5 hover:bg-brand-hover">
              <Sparkles className="h-3.5 w-3.5" /> Open employer verification page
            </button>
          </div>
        );
      } else {
        pushAI(<div className="flex items-center gap-1.5 font-semibold text-emerald-700"><CheckCheck className="h-4 w-4" /> Outcome recorded (Self-Reported)</div>);
      }
      toast.success("Employment outcome saved");
      setPhase("done");
    } catch (e) {
      toast.error("Could not save outcome");
    } finally { setBusy(false); }
  };

  const handleReason = async (reason) => {
    pushUser(reason.label);
    setBusy(true);
    try {
      await api.post("/non-placement-reason", { trainee_id: traineeId, reason_category: reason.value });
      await finalizeFollowup({ employment_type: "unemployed", reason: reason.value });
      pushAI(<div className="flex items-center gap-1.5 font-semibold text-slate-700"><CheckCheck className="h-4 w-4" /> Non-placement reason logged for course improvement.</div>);
      toast.success("Reason recorded");
      setPhase("done");
    } catch (e) { toast.error("Could not save"); } finally { setBusy(false); }
  };

  const handleFreeText = async () => {
    const text = input.trim();
    if (!text) return;
    setInput("");
    pushUser(text);
    setBusy(true);
    try {
      const { data } = await api.post("/ml/classify-response", { raw_text: text });
      pushAI(
        <div data-testid="ml-classification-card">
          <div className="flex items-center gap-1.5 font-semibold text-brand"><Bot className="h-4 w-4" /> AI Classifier</div>
          <div className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
            <span className="text-slate-400">Intent</span><span className="font-semibold text-slate-800">{prettyType(data.predicted_category)}</span>
            <span className="text-slate-400">Sector guess</span><span className="font-semibold text-slate-800">{data.sector_guess || "—"}</span>
            <span className="text-slate-400">Confidence</span><span className="font-semibold text-slate-800">{Math.round((data.confidence || 0) * 100)}%</span>
            <span className="text-slate-400">Method</span><span className="font-semibold text-slate-800">{data.method}</span>
          </div>
        </div>
      );
      // route to the appropriate next step based on prediction
      const cat = data.predicted_category;
      setPending({ type: cat });
      if (cat === "unemployed") {
        pushSys("Understood. What's the main reason?", { reason: true });
        setPhase("reason");
      } else {
        pushSys("Got it 👍 Roughly what is your monthly income?", { wage: true });
        setPhase("wage");
      }
    } catch (e) { toast.error("Classifier error"); } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <div className="max-w-2xl mx-auto px-4 py-6">
        <button data-testid="sim-back-btn" onClick={() => navigate(-1)} className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-brand mb-4">
          <ArrowLeft className="h-4 w-4" /> Back
        </button>

        <div className="rounded-2xl overflow-hidden border border-slate-200 shadow-sm bg-white" data-testid="whatsapp-simulator">
          {/* WhatsApp header */}
          <div className="flex items-center gap-3 px-4 py-3 bg-[#075E54] text-white">
            <div className="h-9 w-9 rounded-full bg-white/20 grid place-items-center font-semibold">
              {trainee?.full_name?.[0] || "?"}
            </div>
            <div className="leading-tight">
              <div className="font-semibold text-sm">{trainee?.full_name || "Trainee"}</div>
              <div className="text-[11px] text-white/70">SkillTrace Follow-Up · simulated</div>
            </div>
            <span className="ml-auto text-[10px] uppercase tracking-wider bg-white/15 rounded-full px-2 py-0.5">Demo</span>
          </div>

          {/* Messages */}
          <div className="wa-bg px-3 py-4 space-y-2 h-[52vh] overflow-y-auto" data-testid="sim-messages">
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.from === "user" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[80%] rounded-lg px-3 py-2 text-sm shadow-sm ${
                  m.from === "user" ? "bg-[#DCF8C6] text-slate-800"
                    : m.from === "ai" ? "bg-white border border-brand/20 text-slate-700"
                    : "bg-white text-slate-800"}`}>
                  {m.node ? m.node : <span>{m.text}</span>}
                  {m.chips && phase === "status" && i === messages.length - 1 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {STATUS_CHIPS.map((c) => (
                        <button key={c.key} data-testid={`whatsapp-quick-reply-${c.key}`} onClick={() => handleStatus(c.key, c.label)}
                          className="text-xs font-medium rounded-full border border-brand/30 text-brand hover:bg-brand hover:text-white px-3 py-1 transition-colors">
                          {c.label}
                        </button>
                      ))}
                    </div>
                  )}
                  {m.wage && phase === "wage" && i === messages.length - 1 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {WAGE_BRACKETS.map((w) => (
                        <button key={w} data-testid={`whatsapp-wage-${w}`} onClick={() => handleWage(w)}
                          className="text-xs font-medium rounded-full border border-emerald-300 text-emerald-700 hover:bg-emerald-600 hover:text-white px-3 py-1 transition-colors">
                          ₹ {w}
                        </button>
                      ))}
                    </div>
                  )}
                  {m.reason && phase === "reason" && i === messages.length - 1 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {REASON_OPTIONS.map((r) => (
                        <button key={r.value} data-testid={`whatsapp-reason-${r.value}`} onClick={() => handleReason(r)}
                          className="text-xs font-medium rounded-full border border-slate-300 text-slate-600 hover:bg-slate-700 hover:text-white px-3 py-1 transition-colors">
                          {r.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {busy && <div className="flex justify-start"><div className="bg-white rounded-lg px-3 py-2 text-sm shadow-sm text-slate-400 flex items-center gap-1"><Loader2 className="h-3.5 w-3.5 animate-spin" /> typing…</div></div>}
          </div>

          {/* Input */}
          <div className="flex items-center gap-2 px-3 py-3 border-t border-slate-200 bg-white">
            <input data-testid="whatsapp-freetext-input" value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleFreeText()}
              placeholder='Type a free-text reply e.g. "haan job lag gayi 18k salary"'
              className="flex-1 rounded-full border border-slate-300 px-4 py-2 text-sm outline-none focus:border-brand" />
            <button data-testid="whatsapp-simulator-send-btn" onClick={handleFreeText} disabled={busy}
              className="h-10 w-10 grid place-items-center rounded-full bg-[#075E54] text-white hover:bg-[#0b7a6e] disabled:opacity-60">
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
        <p className="mt-3 text-xs text-slate-400 text-center">Free-text replies are routed through the explainable ML classifier. Structured replies use quick-reply chips. Every captured outcome is tagged <b>Self-Reported</b> until an employer verifies it.</p>
      </div>
    </div>
  );
}
