// Shared UI constants + badge helpers for SkillTrace AI

export const DISTRICTS = ["Pune", "Nashik", "Nagpur"];
export const SECTORS = ["Retail", "Welding", "IT/ITES", "Healthcare", "Beauty & Wellness",
  "Automotive", "Construction", "Apparel", "Electronics", "Hospitality"];
export const WAGE_BRACKETS = ["<10k", "10-15k", "15-25k", "25k+"];
export const AGE_GROUPS = ["18-24", "25-34", "35+"];

export const REASON_OPTIONS = [
  { value: "skill_mismatch", label: "Skill mismatch" },
  { value: "no_local_jobs", label: "No local jobs" },
  { value: "migrated", label: "Migrated" },
  { value: "family_reasons", label: "Family reasons" },
  { value: "low_wage_offered", label: "Low wage offered" },
  { value: "further_studies", label: "Further studies" },
  { value: "other", label: "Other" },
];

export const CONFIDENCE = {
  verified: { label: "Verified", cls: "bg-emerald-50 border-emerald-200 text-emerald-800", dot: "bg-emerald-500" },
  self_reported: { label: "Self-Reported", cls: "bg-amber-50 border-amber-200 text-amber-800", dot: "bg-amber-500" },
  unreachable: { label: "Unreachable", cls: "bg-rose-50 border-rose-200 text-rose-700", dot: "bg-rose-500" },
};

export const RISK = {
  high: { label: "High Risk", cls: "bg-red-50 border-red-200 text-red-700" },
  medium: { label: "Medium Risk", cls: "bg-amber-50 border-amber-200 text-amber-700" },
  low: { label: "Low Risk", cls: "bg-emerald-50 border-emerald-200 text-emerald-700" },
};

export const FOLLOWUP_STATUS = {
  pending: { label: "Pending", cls: "bg-slate-100 border-slate-200 text-slate-600" },
  sent: { label: "Sent", cls: "bg-sky-50 border-sky-200 text-sky-700" },
  responded: { label: "Responded", cls: "bg-emerald-50 border-emerald-200 text-emerald-700" },
  unreachable: { label: "Unreachable", cls: "bg-rose-50 border-rose-200 text-rose-700" },
  escalated_to_field_agent: { label: "Escalated", cls: "bg-purple-50 border-purple-200 text-purple-700" },
};

export const INTERVAL_LABELS = {
  "1_month": "1 Month", "3_month": "3 Months", "6_month": "6 Months", "12_month": "12 Months",
};

export const ROLE_LABELS = {
  provider: "Training Provider", district_admin: "District Officer",
  state_admin: "State Admin", super_admin: "Super Admin",
};

export const CHART_COLORS = ["#1E3A8A", "#0EA5E9", "#10B981", "#D97706", "#F43F5E", "#8B5CF6", "#0284C7", "#65A30D", "#DB2777", "#475569"];

export function prettyType(t) {
  return ({ employed: "Employed", self_employed: "Self-Employed", apprentice: "Apprentice", unemployed: "Unemployed" }[t]) || t || "—";
}
