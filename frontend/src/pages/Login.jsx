import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Activity, ShieldCheck, Loader2 } from "lucide-react";

const DEMO = [
  { role: "Super Admin", email: "admin@skilltrace.gov.in", password: "Admin@123", testId: "role-switcher-admin" },
  { role: "State Admin", email: "state@skilltrace.gov.in", password: "State@123", testId: "role-switcher-state" },
  { role: "District Officer", email: "district@skilltrace.gov.in", password: "District@123", testId: "role-switcher-district" },
  { role: "Training Provider", email: "provider@skilltrace.gov.in", password: "Provider@123", testId: "role-switcher-provider" },
];

const BG = "https://images.unsplash.com/photo-1760872646618-13594fc00567?crop=entropy&cs=srgb&fm=jpg&q=85&w=1600";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const doLogin = async (e, creds) => {
    if (e) e.preventDefault();
    const em = creds?.email || email;
    const pw = creds?.password || password;
    setLoading(true);
    try {
      const user = await login(em, pw);
      toast.success(`Welcome, ${user.name}`);
      navigate(user.role === "provider" ? "/provider" : "/admin");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      {/* Left brand panel */}
      <div className="relative hidden lg:flex flex-col justify-between p-12 text-white overflow-hidden">
        <div className="absolute inset-0 bg-cover bg-center" style={{ backgroundImage: `url(${BG})` }} />
        <div className="absolute inset-0 bg-brand-hover/85" />
        <div className="relative z-10 flex items-center gap-3">
          <span className="h-11 w-11 rounded-xl bg-white/15 backdrop-blur grid place-items-center">
            <Activity className="h-6 w-6" />
          </span>
          <div className="font-heading font-bold text-2xl">SkillTrace<span className="text-saffron"> AI</span></div>
        </div>
        <div className="relative z-10 max-w-md">
          <h1 className="font-heading text-4xl font-bold leading-tight tracking-tight">Know what happens <span className="text-saffron">after</span> the training ends.</h1>
          <p className="mt-4 text-white/80 leading-relaxed">Longitudinal, consent-based tracking of employment outcomes for government skilling programs — with explainable AI and honest data-confidence scoring.</p>
          <div className="mt-8 flex items-center gap-2 text-sm text-white/70">
            <ShieldCheck className="h-4 w-4" /> Consent-first · Role-based access · SIH 2026 Prototype
          </div>
        </div>
        <div className="relative z-10 text-xs text-white/50">Verified &gt; Self-Reported &gt; Unreachable — we never hide missing data.</div>
      </div>

      {/* Right form */}
      <div className="flex items-center justify-center p-6 sm:p-12 bg-background">
        <div className="w-full max-w-md">
          <div className="lg:hidden flex items-center gap-2.5 mb-8">
            <span className="h-10 w-10 rounded-lg bg-brand text-white grid place-items-center"><Activity className="h-5 w-5" /></span>
            <div className="font-heading font-bold text-xl">SkillTrace<span className="text-saffron"> AI</span></div>
          </div>
          <h2 className="font-heading text-2xl font-bold text-slate-900">Sign in to your dashboard</h2>
          <p className="text-sm text-slate-500 mt-1">Use a demo account below for instant evaluation.</p>

          <form onSubmit={doLogin} className="mt-6 space-y-4">
            <div>
              <label className="text-sm font-medium text-slate-700">Email</label>
              <input data-testid="login-email-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-brand focus:ring-2 focus:ring-brand/20 outline-none"
                placeholder="you@skilltrace.gov.in" />
            </div>
            <div>
              <label className="text-sm font-medium text-slate-700">Password</label>
              <input data-testid="login-password-input" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-brand focus:ring-2 focus:ring-brand/20 outline-none"
                placeholder="••••••••" />
            </div>
            <button data-testid="login-submit-button" type="submit" disabled={loading}
              className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-brand hover:bg-brand-hover text-white font-semibold py-2.5 transition-colors disabled:opacity-60">
              {loading && <Loader2 className="h-4 w-4 animate-spin" />} Sign In
            </button>
          </form>

          <div className="mt-8">
            <div className="text-xs font-medium uppercase tracking-wider text-slate-400 mb-3">One-click demo login</div>
            <div className="grid grid-cols-2 gap-3">
              {DEMO.map((d) => (
                <button key={d.email} data-testid={d.testId} onClick={() => doLogin(null, d)} disabled={loading}
                  className="text-left rounded-lg border border-slate-200 hover:border-brand hover:bg-brand/5 px-3 py-2.5 transition-colors disabled:opacity-60">
                  <div className="text-sm font-semibold text-slate-800">{d.role}</div>
                  <div className="text-[11px] text-slate-400 truncate">{d.email}</div>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
