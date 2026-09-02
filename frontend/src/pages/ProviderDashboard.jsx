import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Navbar } from "@/components/Navbar";
import { StatCard } from "@/components/StatCard";
import { ConfidenceBadge } from "@/components/ConfidenceBadge";
import { RiskBadge } from "@/components/RiskBadge";
import EnrollTraineeModal from "@/pages/EnrollTraineeModal";
import { FOLLOWUP_STATUS } from "@/lib/ui";
import { UserPlus, PlayCircle, MessageSquare, AlertTriangle, Loader2, ChevronRight, CheckCircle2, XCircle } from "lucide-react";

export default function ProviderDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const pid = user.provider_id;
  const [summary, setSummary] = useState(null);
  const [rows, setRows] = useState([]);
  const [atRisk, setAtRisk] = useState([]);
  const [programs, setPrograms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(false);
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, ov, ar, pr] = await Promise.all([
        api.get(`/analytics/provider/${pid}/summary`),
        api.get(`/trainees-overview?provider_id=${pid}`),
        api.get(`/analytics/provider/${pid}/at-risk-trainees?level=high`),
        api.get(`/programs`),
      ]);
      setSummary(s.data.summary);
      setRows(ov.data.items);
      setAtRisk(ar.data.at_risk_trainees);
      setPrograms(pr.data);
    } catch (e) {
      toast.error("Failed to load dashboard");
    } finally { setLoading(false); }
  }, [pid]);

  useEffect(() => { load(); }, [load]);

  const runCycle = async () => {
    setRunning(true);
    try {
      const { data } = await api.post("/followups/schedule", {});
      toast.success(`Follow-up cycle run: ${data.followups_created} check-ins scheduled across ${data.enrollments_processed} certified trainees`);
      load();
    } catch (e) { toast.error("Could not run cycle"); } finally { setRunning(false); }
  };

  if (loading) return <Shell><Loading /></Shell>;
  if (!summary) return <Shell><ErrorState onRetry={load} /></Shell>;

  return (
    <Shell>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="font-heading text-2xl sm:text-3xl font-bold text-slate-900">Provider Dashboard</h1>
          <p className="text-sm text-slate-500 mt-0.5">Track your trainees' outcomes and act on at-risk cases early.</p>
        </div>
        <div className="flex gap-2">
          <button data-testid="run-followup-cycle-btn" onClick={runCycle} disabled={running}
            className="inline-flex items-center gap-2 rounded-lg border border-brand/30 text-brand hover:bg-brand/5 font-semibold text-sm px-4 py-2.5 disabled:opacity-60">
            {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />} Run Follow-Up Cycle
          </button>
          <button data-testid="enroll-trainee-button" onClick={() => setModal(true)}
            className="inline-flex items-center gap-2 rounded-lg bg-brand hover:bg-brand-hover text-white font-semibold text-sm px-4 py-2.5">
            <UserPlus className="h-4 w-4" /> Enroll New Trainee
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-6">
        <StatCard testId="stat-placement-rate" label="Placement Rate" value={`${summary.placement_rate}%`} accent="text-indiagreen" sub="employed / self-employed / apprentice" />
        <StatCard testId="stat-total-trainees" label="My Trainees" value={summary.total_trainees} />
        <StatCard testId="stat-certified" label="Certified" value={summary.certified} accent="text-brand" />
        <StatCard testId="stat-verified" label="Employer-Verified" value={summary.verified_count} accent="text-emerald-600" sub="highest confidence tier" />
      </div>

      <div className="grid lg:grid-cols-3 gap-6 mt-6">
        {/* Trainees table */}
        <div className="lg:col-span-2 min-w-0 bg-white rounded-xl border border-slate-200/90 shadow-sm">
          <div className="px-5 py-4 border-b border-slate-100 font-heading font-semibold text-slate-800">My Trainees</div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[640px]">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-slate-400 bg-slate-50/70">
                  <th className="px-5 py-2.5 font-medium">Name</th>
                  <th className="px-3 py-2.5 font-medium">Course</th>
                  <th className="px-3 py-2.5 font-medium">Attend.</th>
                  <th className="px-3 py-2.5 font-medium">Certified</th>
                  <th className="px-3 py-2.5 font-medium">Follow-up</th>
                  <th className="px-3 py-2.5 font-medium">Confidence</th>
                  <th className="px-3 py-2.5 font-medium"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r, i) => {
                  const st = FOLLOWUP_STATUS[r.latest_followup_status] || FOLLOWUP_STATUS.pending;
                  return (
                    <tr key={r.trainee_id} data-testid={`trainee-table-row-${i}`} className="hover:bg-slate-50/70">
                      <td className="px-5 py-3 font-semibold text-slate-800 cursor-pointer" onClick={() => navigate(`/trainee/${r.trainee_id}`)}>{r.full_name}</td>
                      <td className="px-3 py-3 text-slate-600">{r.course_name || "—"}</td>
                      <td className="px-3 py-3 text-slate-600">{r.attendance_percent != null ? `${r.attendance_percent}%` : "—"}</td>
                      <td className="px-3 py-3">{r.certified ? <CheckCircle2 className="h-4 w-4 text-emerald-500" /> : <XCircle className="h-4 w-4 text-slate-300" />}</td>
                      <td className="px-3 py-3"><span className={`text-xs font-medium px-2 py-0.5 rounded-full border ${st.cls}`}>{st.label}</span></td>
                      <td className="px-3 py-3"><ConfidenceBadge score={r.confidence_score} /></td>
                      <td className="px-3 py-3">
                        <div className="flex items-center gap-1.5">
                          <button data-testid={`simulate-btn-${i}`} title="Open messaging simulator" onClick={() => navigate(`/simulator/${r.trainee_id}`)}
                            className="text-slate-400 hover:text-brand"><MessageSquare className="h-4 w-4" /></button>
                          <button title="View journey" onClick={() => navigate(`/trainee/${r.trainee_id}`)}
                            className="text-slate-400 hover:text-brand"><ChevronRight className="h-4 w-4" /></button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {/* At-risk panel */}
        <div className="bg-white rounded-xl border border-slate-200/90 shadow-sm" data-testid="at-risk-panel">
          <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2 font-heading font-semibold text-slate-800">
            <AlertTriangle className="h-4 w-4 text-red-500" /> At-Risk Trainees
          </div>
          <div className="p-4 space-y-3 max-h-[520px] overflow-y-auto">
            {atRisk.length === 0 && <p className="text-sm text-slate-400 text-center py-6">No high-risk trainees 🎉</p>}
            {atRisk.map((t, i) => (
              <div key={t.trainee_id} data-testid={`at-risk-row-${i}`} onClick={() => navigate(`/trainee/${t.trainee_id}`)}
                className="rounded-lg border border-red-100 bg-red-50/40 p-3 cursor-pointer hover:border-red-300 transition-colors">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-800 text-sm">{t.full_name}</span>
                  <RiskBadge level={t.risk_level} />
                </div>
                <div className="mt-1 text-xs text-slate-500">{t.course_sector} · Risk {Math.round(t.risk_score * 100)}%</div>
                {t.top_contributing_factors?.[0] && (
                  <div className="mt-1.5 text-xs text-red-700 font-medium">↑ {t.top_contributing_factors[0]}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      <EnrollTraineeModal open={modal} onClose={() => setModal(false)} onDone={load} programs={programs} />
    </Shell>
  );
}

function Shell({ children }) {
  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8">{children}</main>
    </div>
  );
}
function Loading() { return <div className="flex items-center gap-2 text-slate-400 py-20 justify-center"><Loader2 className="h-5 w-5 animate-spin" /> Loading dashboard…</div>; }
function ErrorState({ onRetry }) {
  return (
    <div className="flex flex-col items-center gap-3 text-slate-500 py-24" data-testid="dashboard-error">
      <AlertTriangle className="h-8 w-8 text-amber-500" />
      <p className="font-medium">We couldn't load your dashboard.</p>
      <button onClick={onRetry} className="rounded-lg bg-brand text-white font-semibold text-sm px-4 py-2">Retry</button>
    </div>
  );
}
