import { useAuth } from "@/context/AuthContext";
import { ROLE_LABELS } from "@/lib/ui";
import { useNavigate } from "react-router-dom";
import { Activity, LogOut } from "lucide-react";

export function Navbar({ right }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <header className="sticky top-0 z-40 bg-white/90 backdrop-blur-md border-b border-slate-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <button
          data-testid="navbar-logo"
          onClick={() => navigate("/")}
          className="flex items-center gap-2.5 group"
        >
          <span className="h-9 w-9 rounded-lg bg-brand text-white grid place-items-center shadow-sm">
            <Activity className="h-5 w-5" />
          </span>
          <div className="text-left leading-tight">
            <div className="font-heading font-bold text-slate-900 text-lg">SkillTrace<span className="text-saffron"> AI</span></div>
            <div className="text-[10px] uppercase tracking-wider text-slate-400 -mt-0.5">Skilling Outcomes Tracker</div>
          </div>
        </button>

        <div className="flex items-center gap-3">
          {right}
          {user && (
            <>
              <div className="hidden sm:flex flex-col items-end leading-tight">
                <span className="text-sm font-semibold text-slate-800" data-testid="navbar-user-name">{user.name}</span>
                <span className="text-[11px] text-brand font-medium">{ROLE_LABELS[user.role] || user.role}</span>
              </div>
              <button
                data-testid="logout-button"
                onClick={() => { logout(); navigate("/login"); }}
                className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-600 hover:text-rose-600 border border-slate-200 hover:border-rose-200 rounded-lg px-3 py-1.5 transition-colors"
              >
                <LogOut className="h-4 w-4" /> <span className="hidden sm:inline">Logout</span>
              </button>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
