import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Navbar } from "@/components/Navbar";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { RiskBadge } from "@/components/RiskBadge";
import { INTERVAL_LABELS, FOLLOWUP_STATUS, prettyType } from "@/lib/ui";
import {
  ArrowLeft, GraduationCap, Award, MessageCircle, Briefcase, ShieldCheck, ShieldOff,
  MessageSquare, Loader2, MapPin, BadgeCheck, TrendingUp, History, PencilLine,
} from "lucide-react";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
} from "recharts";

const ORDER = ["1_month", "3_month", "6_month", "12_month"];
const CONSENT_ACTION = {
  granted: { label: "Consent Granted", dot: "bg-emerald-500", Icon: ShieldCheck },
  scope_updated: { label: "Scope Updated", dot: "bg-amber-500", Icon: PencilLine },
  revoked: { label: "Consent Revoked", dot: "bg-rose-500", Icon: ShieldOff },
};
const fmtInterval = (l) => ({ "1_month": "1 mo", "3_month": "3 mo", "6_month": "6 mo", "12_month": "12 mo" }[l] || l);
const fmtDate = (ts) => { try { return new Date(ts).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }); } catch { return ts; } };

export default function TraineeProfile() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [d, setD] = useState(null);
  const [followups, setFollowups] = useState([]);
  const [programs, setPrograms] = useState({});
  const [risk, setRisk] = useState(null);
  const [riskState, setRiskState] = useState("loading");
  const [consentLogs, setConsentLogs] = useState([]);
  const [wagePoints, setWagePoints] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [t, fu, pr, cl, wp] = await Promise.all([
        api.get(`/trainees/${id}`),
        api.get(`/followups?trainee_id=${id}`),
        api.get(`/programs`),
        api.get(`/trainees/${id}/consent-logs`),
        api.get(`/trainees/${id}/wage-progression`),
      ]);
      setD(t.data);
      const _fitems = (fu.data.items || []);
      const _seen = {};
      _fitems.forEach((x) => { const k = x.interval_label; if (!_seen[k] || (x.created_at || "") > (_seen[k].created_at || "")) _seen[k] = x; });
      setFollowups(Object.values(_seen).sort((a, b) => ORDER.indexOf(a.interval_label) - ORDER.indexOf(b.interval_label)));
      setPrograms(Object.fromEntries(pr.data.map((p) => [p._id, p])));
      setConsentLogs(cl.data.items || []);
      setWagePoints(wp.data.points || []);
      setRiskState("loading");
      api.get(`/analytics/trainee/${id}/risk`)
        .then((r) => { setRisk(r.data.risk); setRiskState("ok"); })
        .catch((e) => setRiskState(e?.response?.status === 400 ? "none" : "error"));
    } catch (e) { toast.error("Failed to load trainee"); } finally { setLoading(false); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  if (loading || !d) return (
    <div className="min-h-screen bg-background"><Navbar />
      <div className="flex items-center gap-2 text-slate-400 py-20 justify-center"><Loader2 className="h-5 w-5 animate-spin" /> Loading…</div>
    </div>
  );

  const { trainee, enrollments, employment } = d;
  const consent = trainee.consent || {};
  const primaryEnr = [...enrollments].sort((a, b) => (b.certified === true) - (a.certified === true))[0];
  const prog = primaryEnr ? programs[primaryEnr.program_id] : null;

  // build timeline nodes
  const nodes = [];
  if (prog) nodes.push({ icon: GraduationCap, title: "Enrolled", sub: `${prog.course_name} · ${prog.sector}`, tone: "brand" });
  if (primaryEnr?.certified) nodes.push({ icon: Award, title: "Certified", sub: primaryEnr.certification_date || "", tone: "green" });
  followups.forEach((f) => {
    const st = FOLLOWUP_STATUS[f.status] || FOLLOWUP_STATUS.pending;
    nodes.push({
      icon: MessageCircle, title: `Follow-up @ ${INTERVAL_LABELS[f.interval_label] || f.interval_label}`,
      sub: f.raw_response_text || (f.structured_response ? prettyType(f.structured_response.employment_type) : st.label),
      status: f.status, confidence: f.confidence_score, tone: "slate", followup: f,
    });
  });

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
        <button onClick={() => navigate(-1)} className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-brand mb-4">
          <ArrowLeft className="h-4 w-4" /> Back
        </button>

        {/* Header */}
        <div className="bg-white rounded-xl border border-slate-200/90 shadow-sm p-6 flex flex-wrap items-center gap-4">
          <div className="h-14 w-14 rounded-full bg-brand text-white grid place-items-center font-heading text-xl font-bold">
            {trainee.full_name[0]}
          </div>
          <div className="flex-1 min-w-[200px]">
            <h1 className="font-heading text-2xl font-bold text-slate-900" data-testid="trainee-name">{trainee.full_name}</h1>
            <div className="flex flex-wrap items-center gap-3 text-sm text-slate-500 mt-1">
              <span className="flex items-center gap-1"><MapPin className="h-3.5 w-3.5" /> {trainee.district}, {trainee.state}</span>
              <span>{trainee.gender}</span>
              {trainee.phone_masked && <span className="font-mono">{trainee.phone_masked}</span>}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {consent.given
              ? <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700"><ShieldCheck className="h-3.5 w-3.5" /> Consent Active</span>
              : <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-rose-50 border border-rose-200 text-rose-700"><ShieldOff className="h-3.5 w-3.5" /> No Consent</span>}
            <button data-testid="open-simulator-btn" onClick={() => navigate(`/simulator/${id}`)}
              className="inline-flex items-center gap-1.5 text-sm font-semibold rounded-lg bg-brand hover:bg-brand-hover text-white px-3 py-2">
              <MessageSquare className="h-4 w-4" /> Simulator
            </button>
          </div>
        </div>

        <div className="grid lg:grid-cols-3 gap-6 mt-6">
          {/* Timeline */}
          <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200/90 shadow-sm p-6" data-testid="journey-timeline">
            <h2 className="font-heading font-semibold text-slate-800 mb-5">Trainee Journey</h2>
            <ol className="relative border-l-2 border-slate-100 ml-3 space-y-6">
              {nodes.map((n, i) => {
                const Icon = n.icon;
                const tone = n.tone === "brand" ? "bg-brand" : n.tone === "green" ? "bg-indiagreen" : "bg-slate-400";
                return (
                  <li key={i} className="ml-6" data-testid={`timeline-node-${i}`}>
                    <span className={`absolute -left-[13px] grid place-items-center h-6 w-6 rounded-full text-white ${tone}`}>
                      <Icon className="h-3.5 w-3.5" />
                    </span>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold text-slate-800 text-sm">{n.title}</span>
                      {n.status && <span className={`text-[11px] font-medium px-2 py-0.5 rounded-full border ${(FOLLOWUP_STATUS[n.status] || FOLLOWUP_STATUS.pending).cls}`}>{(FOLLOWUP_STATUS[n.status] || FOLLOWUP_STATUS.pending).label}</span>}
                      {n.confidence && <ConfidenceBadge score={n.confidence} />}
                    </div>
                    {n.sub && <p className="text-sm text-slate-500 mt-0.5">{n.sub}</p>}
                  </li>
                );
              })}
            </ol>
          </div>

          {/* Side: risk + employment */}
          <div className="space-y-6">
            <div className="bg-white rounded-xl border border-slate-200/90 shadow-sm p-5" data-testid="risk-card">
              <div className="text-xs font-medium uppercase tracking-wider text-slate-400">Placement Risk (AI)</div>
              {riskState === "loading" ? (
                <p className="text-sm text-slate-400 mt-2 flex items-center gap-1.5"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Assessing…</p>
              ) : riskState === "ok" && risk ? (
                <>
                  <div className="mt-2 flex items-center gap-3">
                    <span className="text-3xl font-heading font-bold text-slate-900">{Math.round(risk.risk_score * 100)}%</span>
                    <RiskBadge level={risk.risk_level} />
                  </div>
                  <div className="mt-3 space-y-1">
                    {risk.top_contributing_factors.map((fct, i) => (
                      <div key={i} className="text-xs text-slate-600 flex items-center gap-1.5"><TrendingUp className="h-3 w-3 text-red-400" /> {fct}</div>
                    ))}
                  </div>
                </>
              ) : riskState === "none" ? (
                <p className="text-sm text-slate-400 mt-2">No enrollment to assess.</p>
              ) : (
                <p className="text-sm text-slate-400 mt-2">Could not load risk assessment.</p>
              )}
            </div>

            <div className="bg-white rounded-xl border border-slate-200/90 shadow-sm p-5" data-testid="employment-card">
              <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-slate-400"><Briefcase className="h-3.5 w-3.5" /> Employment Records</div>
              {employment.length === 0 ? (
                <p className="text-sm text-slate-400 mt-2">No outcome reported yet.</p>
              ) : (
                <div className="mt-3 space-y-3">
                  {employment.map((e) => (
                    <div key={e._id} className="rounded-lg border border-slate-100 p-3">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-slate-800 text-sm">{prettyType(e.type)}</span>
                        {e.employer_verified
                          ? <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700"><BadgeCheck className="h-3.5 w-3.5" /> Verified</span>
                          : <span className="text-[11px] font-medium text-amber-600">Self-reported</span>}
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5">
                        {e.employer_name || "—"}{e.wage_bracket ? ` · ₹${e.wage_bracket}` : ""}{e.sector ? ` · ${e.sector}` : ""}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Wage progression + Consent audit trail */}
        <div className="grid lg:grid-cols-2 gap-6 mt-6">
          <div className="bg-white rounded-xl border border-slate-200/90 shadow-sm p-6" data-testid="wage-progression">
            <div className="flex items-center gap-2 font-heading font-semibold text-slate-800"><TrendingUp className="h-4 w-4 text-indiagreen" /> Wage Progression</div>
            <p className="text-xs text-slate-400 mt-0.5 mb-3">Self-reported monthly income (₹ '000s) across follow-up check-ins.</p>
            {wagePoints.length < 2 ? (
              <div className="h-[220px] grid place-items-center text-sm text-slate-400">Not enough follow-up wage data to plot a trend.</div>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={wagePoints} margin={{ left: -12, right: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
                  <XAxis dataKey="interval_label" tickFormatter={fmtInterval} tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} unit="k" domain={[0, 32]} />
                  <Tooltip content={({ active, payload }) => active && payload?.length ? (
                    <div className="bg-white border border-slate-200 rounded-lg shadow-md p-2 text-xs">
                      <div className="font-semibold text-slate-700">{fmtInterval(payload[0].payload.interval_label)}</div>
                      <div className="text-slate-600">Bracket: <b>₹{payload[0].payload.wage_bracket}</b></div>
                      <div className="text-slate-600">Est: <b>₹{payload[0].value}k/mo</b></div>
                    </div>
                  ) : null} />
                  <Line type="monotone" dataKey="wage_value" name="Income" stroke="#15803D" strokeWidth={2.5} dot={{ r: 4, fill: "#15803D" }} activeDot={{ r: 6 }} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>

          <div className="bg-white rounded-xl border border-slate-200/90 shadow-sm p-6" data-testid="consent-audit-trail">
            <div className="flex items-center gap-2 font-heading font-semibold text-slate-800"><History className="h-4 w-4 text-brand" /> Consent Audit Trail</div>
            <p className="text-xs text-slate-400 mt-0.5 mb-3">Every grant, scope change and revocation is logged for governance & compliance.</p>
            {consentLogs.length === 0 ? (
              <p className="text-sm text-slate-400">No consent events recorded.</p>
            ) : (
              <ol className="relative border-l-2 border-slate-100 ml-2.5 space-y-4">
                {consentLogs.map((l, i) => {
                  const a = CONSENT_ACTION[l.action] || CONSENT_ACTION.granted;
                  const Icon = a.Icon;
                  return (
                    <li key={i} className="ml-6" data-testid={`consent-log-${i}`}>
                      <span className={`absolute -left-[11px] grid place-items-center h-5 w-5 rounded-full text-white ${a.dot}`}><Icon className="h-3 w-3" /></span>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-slate-800 text-sm">{a.label}</span>
                        <span className="text-xs text-slate-400">{fmtDate(l.timestamp)}</span>
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5">
                        by {l.performed_by}
                        {l.scope?.length ? ` · scopes: ${l.scope.join(", ")}` : (l.action === "revoked" ? " · all scopes withdrawn" : "")}
                      </div>
                    </li>
                  );
                })}
              </ol>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
