import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  PieChart, Pie, Cell,
} from "recharts";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Navbar } from "@/components/Navbar";
import { StatCard } from "@/components/StatCard";
import { DISTRICTS, SECTORS, AGE_GROUPS, CHART_COLORS, REASON_OPTIONS } from "@/lib/ui";
import { Filter, Loader2, Trophy } from "lucide-react";

const REASON_LABEL = Object.fromEntries(REASON_OPTIONS.map((r) => [r.value, r.label]));
const CONF_COLORS = { verified: "#10B981", self_reported: "#F59E0B", unreachable: "#F43F5E" };

export default function AdminDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [providers, setProviders] = useState([]);
  const [programs, setPrograms] = useState([]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [f, setF] = useState({ district: "", provider_id: "", program_id: "", gender: "", age_group: "" });

  useEffect(() => {
    Promise.all([api.get("/providers"), api.get("/programs")]).then(([p, pr]) => {
      setProviders(p.data); setPrograms(pr.data);
    }).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = Object.entries(f).filter(([, v]) => v).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
      const { data } = await api.get(`/analytics/overview${qs ? `?${qs}` : ""}`);
      setData(data);
    } catch (e) { toast.error("Failed to load analytics"); } finally { setLoading(false); }
  }, [f]);

  useEffect(() => { load(); }, [load]);

  const wageData = data ? Object.entries(data.wage_distribution).map(([bracket, count]) => ({ bracket, count })) : [];
  const reasonData = data ? Object.entries(data.non_placement_reasons).map(([k, v]) => ({ name: REASON_LABEL[k] || k, value: v })) : [];
  const confData = data ? Object.entries(data.confidence_breakdown).map(([k, v]) => ({ name: k, value: v })) : [];

  const setFilter = (k, v) => setF((prev) => ({ ...prev, [k]: v }));

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
        <h1 className="font-heading text-2xl sm:text-3xl font-bold text-slate-900">Government Analytics Dashboard</h1>
        <p className="text-sm text-slate-500 mt-0.5">Compare providers, courses, cohorts and districts — with honest data-confidence scoring.</p>

        {/* Filters */}
        <div className="mt-5 bg-white rounded-xl border border-slate-200/90 shadow-sm p-4">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3"><Filter className="h-3.5 w-3.5" /> Filters</div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <Select testId="filter-district-select" label="District" value={f.district} onChange={(v) => setFilter("district", v)} options={DISTRICTS} />
            <Select testId="filter-provider-select" label="Provider" value={f.provider_id} onChange={(v) => setFilter("provider_id", v)}
              options={providers.map((p) => ({ value: p._id, label: p.name }))} />
            <Select testId="filter-course-select" label="Course" value={f.program_id} onChange={(v) => setFilter("program_id", v)}
              options={programs.map((p) => ({ value: p._id, label: p.course_name }))} />
            <Select testId="filter-gender-select" label="Gender" value={f.gender} onChange={(v) => setFilter("gender", v)} options={["Male", "Female"]} />
            <Select testId="filter-age-select" label="Age group" value={f.age_group} onChange={(v) => setFilter("age_group", v)} options={AGE_GROUPS} />
          </div>
        </div>

        {loading || !data ? (
          <div className="flex items-center gap-2 text-slate-400 py-20 justify-center"><Loader2 className="h-5 w-5 animate-spin" /> Loading analytics…</div>
        ) : (
          <>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-6">
              <StatCard testId="stat-total" label="Trainees" value={data.totals.total_trainees} />
              <StatCard testId="stat-placement" label="Placement Rate" value={`${data.totals.placement_rate}%`} accent="text-indiagreen" />
              <StatCard testId="stat-verified" label="Employer-Verified" value={data.totals.verified_count} accent="text-emerald-600" />
              <StatCard testId="stat-reachable" label="Reachable Rate" value={`${data.totals.reachable_rate}%`} accent="text-brand" sub="responded vs unreachable" />
            </div>

            <div className="grid lg:grid-cols-2 gap-6 mt-6">
              <ChartCard title="Placement Rate by Provider" testId="chart-by-provider">
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={data.by_provider} margin={{ left: -10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
                    <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-12} textAnchor="end" height={60} />
                    <YAxis tick={{ fontSize: 11 }} unit="%" />
                    <Tooltip content={<CT unit="%" />} />
                    <Bar dataKey="placement_rate" name="Placement %" fill="#1E3A8A" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>

              <ChartCard title="Placement Rate by Sector" testId="chart-by-sector">
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={data.by_sector} margin={{ left: -10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
                    <XAxis dataKey="sector" tick={{ fontSize: 10 }} interval={0} angle={-12} textAnchor="end" height={60} />
                    <YAxis tick={{ fontSize: 11 }} unit="%" />
                    <Tooltip content={<CT unit="%" />} />
                    <Bar dataKey="placement_rate" name="Placement %" fill="#0EA5E9" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>

              <ChartCard title="Wage Bracket Distribution" testId="chart-wage">
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={wageData} margin={{ left: -10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
                    <XAxis dataKey="bracket" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                    <Tooltip content={<CT />} />
                    <Bar dataKey="count" name="Trainees" fill="#15803D" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>

              <ChartCard title="Non-Placement Reasons" testId="chart-reasons">
                {reasonData.length === 0 ? <Empty /> : (
                  <ResponsiveContainer width="100%" height={280}>
                    <PieChart>
                      <Pie data={reasonData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={55} outerRadius={95} paddingAngle={2}>
                        {reasonData.map((e, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                      </Pie>
                      <Tooltip content={<CT />} />
                      <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" />
                    </PieChart>
                  </ResponsiveContainer>
                )}
              </ChartCard>
            </div>

            <div className="grid lg:grid-cols-2 gap-6 mt-6">
              {/* Confidence breakdown */}
              <ChartCard title="Data Confidence Breakdown" testId="chart-confidence"
                subtitle="We surface data quality instead of hiding it — verified vs self-reported vs unreachable.">
                <div className="flex items-center gap-4">
                  <ResponsiveContainer width="55%" height={220}>
                    <PieChart>
                      <Pie data={confData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={50} outerRadius={90} paddingAngle={2}>
                        {confData.map((e, i) => <Cell key={i} fill={CONF_COLORS[e.name] || "#94A3B8"} />)}
                      </Pie>
                      <Tooltip content={<CT />} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="flex-1 space-y-2">
                    {confData.map((c) => (
                      <div key={c.name} className="flex items-center justify-between text-sm">
                        <span className="flex items-center gap-2 capitalize text-slate-600">
                          <span className="h-2.5 w-2.5 rounded-full" style={{ background: CONF_COLORS[c.name] || "#94A3B8" }} />
                          {c.name.replace("_", " ")}
                        </span>
                        <span className="font-semibold text-slate-800">{c.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </ChartCard>

              {/* District ranking */}
              <ChartCard title="District Ranking by Outcomes" testId="district-ranking">
                <div className="space-y-2">
                  {data.district_ranking.map((d, i) => (
                    <div key={d.district} data-testid={`district-row-${i}`} onClick={() => setFilter("district", d.district)}
                      className="flex items-center gap-3 rounded-lg border border-slate-200 px-4 py-2.5 hover:border-brand cursor-pointer">
                      <span className={`grid place-items-center h-7 w-7 rounded-full text-xs font-bold ${i === 0 ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-500"}`}>
                        {i === 0 ? <Trophy className="h-3.5 w-3.5" /> : i + 1}
                      </span>
                      <span className="font-semibold text-slate-800 flex-1">{d.district}</span>
                      <span className="text-xs text-slate-400">{d.total} trainees</span>
                      <span className="font-bold text-indiagreen">{d.placement_rate}%</span>
                    </div>
                  ))}
                </div>
              </ChartCard>
            </div>

            {/* Provider drill-down list */}
            <div className="mt-6 bg-white rounded-xl border border-slate-200/90 shadow-sm">
              <div className="px-5 py-4 border-b border-slate-100 font-heading font-semibold text-slate-800">Provider Drill-Down</div>
              <div className="divide-y divide-slate-100">
                {data.by_provider.map((p, i) => (
                  <div key={p.name} data-testid={`provider-drill-${i}`}
                    className="flex items-center justify-between px-5 py-3 hover:bg-slate-50/70">
                    <div>
                      <div className="font-semibold text-slate-800 text-sm">{p.name}</div>
                      <div className="text-xs text-slate-400">{p.total} trainees</div>
                    </div>
                    <span className="font-bold text-indiagreen">{p.placement_rate}%</span>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function Select({ label, value, onChange, options, testId }) {
  const opts = options.map((o) => typeof o === "string" ? { value: o, label: o } : o);
  return (
    <div>
      <label className="text-[11px] font-medium text-slate-500">{label}</label>
      <select data-testid={testId} value={value} onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-lg border border-slate-300 px-2.5 py-2 text-sm outline-none focus:border-brand bg-white">
        <option value="">All</option>
        {opts.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}

function ChartCard({ title, subtitle, children, testId }) {
  return (
    <div data-testid={testId} className="bg-white rounded-xl border border-slate-200/90 shadow-sm p-5">
      <div className="font-heading font-semibold text-slate-800">{title}</div>
      {subtitle && <p className="text-xs text-slate-400 mt-0.5 mb-2">{subtitle}</p>}
      <div className="mt-2">{children}</div>
    </div>
  );
}
function CT({ active, payload, label, unit = "" }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-slate-200 rounded-lg shadow-md p-2 text-xs">
      {label && <div className="font-semibold text-slate-700 mb-0.5">{label}</div>}
      {payload.map((p, i) => <div key={i} className="text-slate-600">{p.name}: <b>{p.value}{unit}</b></div>)}
    </div>
  );
}
function Empty() { return <div className="h-[280px] grid place-items-center text-sm text-slate-400">No non-placement data for this filter</div>; }
