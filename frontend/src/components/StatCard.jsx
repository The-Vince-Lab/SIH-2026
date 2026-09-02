export function StatCard({ label, value, sub, accent = "text-brand", testId }) {
  return (
    <div data-testid={testId} className="bg-white rounded-xl border border-slate-200/90 shadow-sm p-5 animate-fade-in-up">
      <div className="text-xs font-medium uppercase tracking-wider text-slate-500">{label}</div>
      <div className={`mt-2 text-3xl font-heading font-bold ${accent}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
    </div>
  );
}
