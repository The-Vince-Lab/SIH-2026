import { useState, useEffect } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { DISTRICTS } from "@/lib/ui";
import { X, UserPlus, AlertTriangle, Loader2, ShieldCheck } from "lucide-react";

const SCOPES = [
  { value: "employment_status", label: "Employment status" },
  { value: "wage_data", label: "Wage / income data" },
  { value: "contact_for_verification", label: "Contact for employer verification" },
];

export default function EnrollTraineeModal({ open, onClose, onDone, programs }) {
  const [form, setForm] = useState(blank());
  const [scopes, setScopes] = useState(SCOPES.map((s) => s.value));
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dup, setDup] = useState(null); // { possible_matches }

  useEffect(() => { if (open) { setForm(blank()); setScopes(SCOPES.map((s) => s.value)); setConsent(false); setDup(null); } }, [open]);
  if (!open) return null;

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const submit = async (force = false) => {
    if (!consent) { toast.error("Consent is required to enroll a trainee"); return; }
    if (!form.full_name || !form.phone_number || !form.program_id) { toast.error("Please fill name, phone and program"); return; }
    setBusy(true);
    try {
      const { data } = await api.post(`/trainees${force ? "?force=true" : ""}`, {
        full_name: form.full_name, phone_number: form.phone_number, dob: form.dob || null,
        gender: form.gender, district: form.district, state: "Maharashtra",
        consent: { given: true, scope: scopes },
      });
      if (data.requires_confirmation) { setDup(data); setBusy(false); return; }
      // create enrollment
      const tid = data.id || data._id;
      await api.post("/enrollments", {
        trainee_id: tid, program_id: form.program_id,
        attendance_percent: Number(form.attendance_percent) || 0,
        assessment_score: Number(form.assessment_score) || 0,
        certified: form.certified, certification_date: form.certified ? (form.certification_date || todayISO()) : null,
      });
      toast.success("Trainee enrolled with consent captured");
      onDone?.();
      onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not enroll trainee");
    } finally { setBusy(false); }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-slate-900/50 backdrop-blur-sm p-4" data-testid="enroll-modal">
      <div className="w-full max-w-2xl bg-white rounded-2xl shadow-xl border border-slate-200 max-h-[92vh] overflow-y-auto">
        <div className="sticky top-0 flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-white">
          <div className="flex items-center gap-2 font-heading font-bold text-slate-900"><UserPlus className="h-5 w-5 text-brand" /> Enroll New Trainee</div>
          <button data-testid="enroll-modal-close" onClick={onClose} className="text-slate-400 hover:text-slate-700"><X className="h-5 w-5" /></button>
        </div>

        {dup ? (
          <div className="p-6" data-testid="duplicate-warning">
            <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4">
              <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
              <div>
                <div className="font-semibold text-amber-800">Possible existing trainee found</div>
                <p className="text-sm text-amber-700 mt-0.5">Our identity matcher found likely matches across programs. Is this the same person?</p>
              </div>
            </div>
            <div className="mt-4 space-y-2">
              {dup.possible_matches.map((m) => (
                <div key={m.trainee_id} className="flex items-center justify-between rounded-lg border border-slate-200 px-4 py-2.5">
                  <div>
                    <div className="font-semibold text-slate-800 text-sm">{m.name}</div>
                    <div className="text-xs text-slate-400">{(m.reasons || []).join(" · ")}</div>
                  </div>
                  <span className="text-sm font-bold text-brand">{m.similarity_score}%</span>
                </div>
              ))}
            </div>
            <div className="mt-6 flex gap-3">
              <button data-testid="dup-same-person-btn" onClick={onClose}
                className="flex-1 rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50 font-semibold py-2.5">
                It's the same person — cancel
              </button>
              <button data-testid="dup-force-create-btn" disabled={busy} onClick={() => submit(true)}
                className="flex-1 inline-flex items-center justify-center gap-2 rounded-lg bg-brand hover:bg-brand-hover text-white font-semibold py-2.5 disabled:opacity-60">
                {busy && <Loader2 className="h-4 w-4 animate-spin" />} No, this is a new person
              </button>
            </div>
          </div>
        ) : (
          <div className="p-6 space-y-5">
            <div className="grid sm:grid-cols-2 gap-4">
              <Field label="Full name *"><input data-testid="enroll-name" value={form.full_name} onChange={(e) => set("full_name", e.target.value)} className={inp} placeholder="e.g. Anjali Deshmukh" /></Field>
              <Field label="Phone number *"><input data-testid="enroll-phone" value={form.phone_number} onChange={(e) => set("phone_number", e.target.value)} className={inp} placeholder="+91 98xxxxxxxx" /></Field>
              <Field label="Date of birth"><input data-testid="enroll-dob" type="date" value={form.dob} onChange={(e) => set("dob", e.target.value)} className={inp} /></Field>
              <Field label="Gender">
                <select data-testid="enroll-gender" value={form.gender} onChange={(e) => set("gender", e.target.value)} className={inp}>
                  <option>Female</option><option>Male</option><option>Other</option>
                </select>
              </Field>
              <Field label="District">
                <select data-testid="enroll-district" value={form.district} onChange={(e) => set("district", e.target.value)} className={inp}>
                  {DISTRICTS.map((d) => <option key={d}>{d}</option>)}
                </select>
              </Field>
              <Field label="Program / Course *">
                <select data-testid="enroll-program" value={form.program_id} onChange={(e) => set("program_id", e.target.value)} className={inp}>
                  <option value="">Select a course…</option>
                  {(programs || []).map((p) => <option key={p._id} value={p._id}>{p.course_name} ({p.sector})</option>)}
                </select>
              </Field>
              <Field label="Attendance %"><input data-testid="enroll-attendance" type="number" value={form.attendance_percent} onChange={(e) => set("attendance_percent", e.target.value)} className={inp} placeholder="0-100" /></Field>
              <Field label="Assessment score"><input data-testid="enroll-score" type="number" value={form.assessment_score} onChange={(e) => set("assessment_score", e.target.value)} className={inp} placeholder="0-100" /></Field>
            </div>

            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input data-testid="enroll-certified" type="checkbox" checked={form.certified} onChange={(e) => set("certified", e.target.checked)} className="h-4 w-4 rounded border-slate-300 text-brand" />
              Mark as certified (enables follow-up scheduling)
            </label>

            {/* Consent block */}
            <div className="rounded-xl border border-brand/20 bg-brand/5 p-4">
              <div className="flex items-center gap-2 text-brand font-semibold text-sm"><ShieldCheck className="h-4 w-4" /> Consent (required)</div>
              <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                We collect employment & wage outcomes via periodic WhatsApp/SMS check-ins to measure training impact.
                The trainee can revoke consent at any time. Only the data scopes selected below will be used.
              </p>
              <div className="mt-3 flex flex-wrap gap-3">
                {SCOPES.map((s) => (
                  <label key={s.value} className="flex items-center gap-1.5 text-xs text-slate-700">
                    <input type="checkbox" checked={scopes.includes(s.value)}
                      onChange={(e) => setScopes((prev) => e.target.checked ? [...prev, s.value] : prev.filter((x) => x !== s.value))}
                      className="h-3.5 w-3.5 rounded border-slate-300 text-brand" data-testid={`consent-scope-${s.value}`} />
                    {s.label}
                  </label>
                ))}
              </div>
              <label className="mt-3 flex items-start gap-2 text-sm font-medium text-slate-800">
                <input data-testid="consent-checkbox" type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 h-4 w-4 rounded border-slate-300 text-brand" />
                The trainee has given informed consent to be contacted and tracked for the selected scopes.
              </label>
            </div>

            <div className="flex gap-3 pt-1">
              <button onClick={onClose} className="flex-1 rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50 font-semibold py-2.5">Cancel</button>
              <button data-testid="enroll-submit-btn" disabled={busy || !consent} onClick={() => submit(false)}
                className="flex-1 inline-flex items-center justify-center gap-2 rounded-lg bg-brand hover:bg-brand-hover text-white font-semibold py-2.5 disabled:opacity-50">
                {busy && <Loader2 className="h-4 w-4 animate-spin" />} Enroll Trainee
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const inp = "mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-brand focus:ring-2 focus:ring-brand/20";
function Field({ label, children }) { return <div><label className="text-xs font-medium text-slate-600">{label}</label>{children}</div>; }
function blank() { return { full_name: "", phone_number: "", dob: "", gender: "Female", district: "Pune", program_id: "", attendance_percent: "", assessment_score: "", certified: false, certification_date: "" }; }
function todayISO() { return new Date().toISOString().slice(0, 10); }
