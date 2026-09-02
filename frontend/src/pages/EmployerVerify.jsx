import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { ShieldCheck, Check, X, Activity, Loader2 } from "lucide-react";
import { prettyType } from "@/lib/ui";

export default function EmployerVerify() {
  const { token } = useParams();
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.get(`/employment/verify/${token}`)
      .then(({ data }) => setInfo(data))
      .catch((e) => setError(e?.response?.data?.detail || "Invalid or expired link"))
      .finally(() => setLoading(false));
  }, [token]);

  const submit = async (confirmed) => {
    setSubmitting(true);
    try {
      const { data } = await api.post(`/employment/verify/${token}`, { confirmed });
      setResult(data.employer_verified ? "confirmed" : "declined");
    } catch (e) {
      setError(e?.response?.data?.detail || "Could not submit");
    } finally { setSubmitting(false); }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <div className="border-b border-slate-200 bg-white">
        <div className="max-w-3xl mx-auto px-4 h-16 flex items-center gap-2.5">
          <span className="h-9 w-9 rounded-lg bg-brand text-white grid place-items-center"><Activity className="h-5 w-5" /></span>
          <div className="font-heading font-bold text-lg">SkillTrace<span className="text-saffron"> AI</span></div>
        </div>
      </div>

      <div className="flex-1 grid place-items-center px-4 py-10">
        <div className="w-full max-w-md bg-white rounded-2xl border border-slate-200 shadow-sm p-7" data-testid="employer-verify-card">
          {loading ? (
            <div className="flex items-center gap-2 text-slate-500"><Loader2 className="h-5 w-5 animate-spin" /> Loading…</div>
          ) : error ? (
            <div className="text-center py-6">
              <div className="h-12 w-12 rounded-full bg-rose-50 text-rose-500 grid place-items-center mx-auto"><X className="h-6 w-6" /></div>
              <h2 className="mt-4 font-heading text-xl font-bold text-slate-900">Link unavailable</h2>
              <p className="mt-1 text-sm text-slate-500" data-testid="verify-error-msg">{error}</p>
            </div>
          ) : result ? (
            <div className="text-center py-6" data-testid="verify-result">
              <div className={`h-12 w-12 rounded-full grid place-items-center mx-auto ${result === "confirmed" ? "bg-emerald-50 text-emerald-600" : "bg-slate-100 text-slate-500"}`}>
                {result === "confirmed" ? <Check className="h-6 w-6" /> : <X className="h-6 w-6" />}
              </div>
              <h2 className="mt-4 font-heading text-xl font-bold text-slate-900">
                {result === "confirmed" ? "Thank you — employment verified!" : "Response recorded"}
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                {result === "confirmed"
                  ? "This outcome is now marked Verified in SkillTrace. No account needed. You may close this page."
                  : "We've noted this person does not work at your organization. Thank you."}
              </p>
            </div>
          ) : info?.used ? (
            <div className="text-center py-6">
              <div className="h-12 w-12 rounded-full bg-slate-100 text-slate-500 grid place-items-center mx-auto"><ShieldCheck className="h-6 w-6" /></div>
              <h2 className="mt-4 font-heading text-xl font-bold text-slate-900">Already responded</h2>
              <p className="mt-1 text-sm text-slate-500">This verification link has already been used. Thank you.</p>
            </div>
          ) : (
            <div>
              <div className="flex items-center gap-2 text-brand"><ShieldCheck className="h-5 w-5" /><span className="text-xs font-semibold uppercase tracking-wider">Employment Verification</span></div>
              <h2 className="mt-3 font-heading text-2xl font-bold text-slate-900 leading-snug">Do you confirm this person works at your organization?</h2>
              <div className="mt-5 rounded-xl bg-slate-50 border border-slate-200 p-4 space-y-2 text-sm">
                <Row label="Person" value={info?.trainee_name} />
                <Row label="Reported as" value={prettyType(info?.type)} />
                {info?.employer_name && <Row label="Employer" value={info.employer_name} />}
                {info?.sector && <Row label="Sector" value={info.sector} />}
              </div>
              <div className="mt-6 grid grid-cols-2 gap-3">
                <button data-testid="employer-verify-yes-btn" disabled={submitting} onClick={() => submit(true)}
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-indiagreen hover:bg-emerald-800 text-white font-semibold py-3 transition-colors disabled:opacity-60">
                  <Check className="h-5 w-5" /> Yes, confirm
                </button>
                <button data-testid="employer-verify-no-btn" disabled={submitting} onClick={() => submit(false)}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50 font-semibold py-3 transition-colors disabled:opacity-60">
                  <X className="h-5 w-5" /> No
                </button>
              </div>
              <p className="mt-4 text-[11px] text-slate-400 text-center">No login or account required. This link is single-use and expires in 14 days.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-slate-400">{label}</span>
      <span className="font-semibold text-slate-800 text-right">{value || "—"}</span>
    </div>
  );
}
