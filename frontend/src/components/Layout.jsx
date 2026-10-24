import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  Activity,
  BarChart3,
  ClipboardList,
  FileText,
  FlaskConical,
  Gauge,
  HeartPulse,
  Home,
  Menu,
  ScanLine,
  Sparkles,
  UploadCloud,
  UserPlus,
  Users,
  X,
} from "lucide-react";
import { useApp } from "../store";
import { DisclaimerBanner, ErrorBanner } from "./ui";

const NAV = [
  { to: "/overview", label: "Overview", icon: Home },
  { to: "/patients", label: "Patients", icon: Users, end: true },
  { to: "/patients/new", label: "Add Patient", icon: UserPlus, end: true },
  { to: "/data-entry", label: "Medical Data", icon: UploadCloud },
  { to: "/twin", label: "Digital Twin", icon: ScanLine },
  { to: "/prediction", label: "Predictions & Risk", icon: Gauge },
  { to: "/whatif", label: "What-if Simulation", icon: FlaskConical },
  { to: "/reports", label: "Reports", icon: FileText },
  { to: "/doctor", label: "Doctor View", icon: ClipboardList },
];

const linkClass = ({ isActive }) =>
  `group relative flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-[13px] transition ${
    isActive
      ? "bg-white/10 text-white shadow-[0_20px_60px_-30px_rgba(45,212,191,0.9)]"
      : "text-slate-300 hover:bg-white/5 hover:text-white"
  }`;

function NavItems({ onNavigate }) {
  return (
    <div className="space-y-1">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink key={to} to={to} end={end} className={linkClass} onClick={onNavigate}>
          {({ isActive }) => (
            <>
              {isActive && <span className="absolute left-0 top-1/2 h-6 w-0.5 -translate-y-1/2 rounded-full bg-gradient-to-b from-cyan-300 to-teal-400" />}
              <Icon className={`h-4 w-4 shrink-0 ${isActive ? "text-cyan-200" : ""}`} />
              {label}
            </>
          )}
        </NavLink>
      ))}
    </div>
  );
}

function Brand() {
  return (
    <div className="flex items-center gap-3 px-5 py-5">
      <div className="relative flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-teal-400 to-indigo-500 text-white shadow-[0_30px_60px_-30px_rgba(45,212,191,0.9)]">
        <HeartPulse className="h-5 w-5" />
        <span className="absolute -right-1 -top-1 h-2 w-2 rounded-full bg-cyan-300 shadow-[0_0_0_6px_rgba(34,211,238,0.12)]" />
      </div>
      <div className="min-w-0">
        <div className="text-[15px] font-semibold leading-tight text-white">GlucoTwin AI</div>
        <div className="text-[11px] leading-tight text-slate-400">Predictive Digital Twin</div>
      </div>
    </div>
  );
}

export default function Layout() {
  const { patients, selectedId, selectPatient, twin, busy, error, health } = useApp();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  const selected = patients.find((p) => p.patient_id === selectedId);
  const apiState = health?.status === "ok" ? "ok" : health?.status || "checking";

  return (
    <div className="relative flex min-h-screen overflow-hidden">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute -top-40 left-1/2 h-[28rem] w-[28rem] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,rgba(45,212,191,0.14),transparent)]" />
        <div className="absolute top-20 right-[-10%] h-[22rem] w-[22rem] rounded-full bg-[radial-gradient(circle,rgba(99,102,241,0.12),transparent)]" />
      </div>

      {/* Desktop sidebar */}
      <aside className="relative z-10 hidden h-screen w-72 shrink-0 flex-col border-r border-white/5 bg-[radial-gradient(120%_120%_at_0%_0%,rgba(34,211,238,0.16),transparent),linear-gradient(180deg,#0b1026_0%,#0f172a_100%)] md:flex">
        <Brand />
        <nav aria-label="Primary" className="thin-scroll flex-1 overflow-y-auto px-4">
          <NavItems />
        </nav>
        <div className="px-5 pb-5">
          <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-white/5 p-4">
            <div className="absolute -right-6 -top-6 h-16 w-16 rounded-full bg-cyan-400/10" />
            <div className="relative flex items-center gap-2 text-[11px] text-slate-300">
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  apiState === "ok" ? "bg-emerald-400" : apiState === "degraded" ? "bg-amber-400" : "bg-slate-500"
                }`}
              />
              <span>System status · API {apiState}</span>
            </div>
            <div className="relative mt-1 flex items-center gap-2 text-[10px] uppercase tracking-[0.16em] text-slate-400">
              <Sparkles className="h-3 w-3" />
              <span>Precision forecasting</span>
            </div>
          </div>
        </div>
      </aside>

      {/* Mobile drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div className="absolute inset-0 bg-slate-950/60" onClick={() => setDrawerOpen(false)} aria-hidden="true" />
          <div className="absolute left-0 top-0 flex h-full w-72 flex-col bg-[linear-gradient(180deg,#0b1026_0%,#0f172a_100%)]">
            <div className="flex items-center justify-between">
              <Brand />
              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                className="mr-4 rounded-full p-1.5 text-slate-400 hover:bg-white/10 hover:text-white"
                aria-label="Close navigation"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <nav aria-label="Primary" className="thin-scroll flex-1 overflow-y-auto px-4">
              <NavItems onNavigate={() => setDrawerOpen(false)} />
            </nav>
          </div>
        </div>
      )}

      {/* Main */}
      <div className="relative z-10 flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-40 border-b border-slate-200/70 bg-white/70 backdrop-blur-xl">
          <div className="flex h-16 items-center gap-3 px-4 md:px-6 lg:px-10">
            <button
              type="button"
              onClick={() => setDrawerOpen(true)}
              className="rounded-full p-1.5 text-slate-600 hover:bg-slate-900/5 md:hidden"
              aria-label="Open navigation"
            >
              <Menu className="h-5 w-5" />
            </button>
            <div className="flex items-center gap-2 md:hidden">
              <HeartPulse className="h-4 w-4 text-teal-500" />
              <span className="text-[13px] font-semibold text-slate-900">GlucoTwin AI</span>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <div className="hidden items-center gap-2 rounded-full border border-slate-200/80 bg-white/80 px-2 py-1 text-[11px] text-slate-500 lg:flex">
                <Activity className="h-3.5 w-3.5 text-teal-500" />
                <span>{busy ? "Syncing twin…" : "Live twin state"}</span>
              </div>
              <div className="flex items-center gap-2 rounded-full border border-slate-200/80 bg-white/80 px-3 py-1">
                <span className="text-[11px] uppercase tracking-[0.14em] text-slate-500">Patient</span>
                <select
                  className="bg-transparent text-[12.5px] text-slate-700 focus:outline-none"
                  value={selectedId || ""}
                  onChange={(e) => selectPatient(e.target.value)}
                >
                  {patients.length === 0 && <option value="">No patients</option>}
                  {patients.map((p) => (
                    <option key={p.patient_id} value={p.patient_id}>
                      {p.patient_id} · {p.name}
                    </option>
                  ))}
                </select>
              </div>
              {selected && (
                <div className="hidden items-center gap-2 rounded-full border border-slate-200/80 bg-white/80 px-3 py-1 text-[11px] text-slate-500 md:flex">
                  <BarChart3 className="h-3.5 w-3.5 text-indigo-500" />
                  <span>{selected.name}</span>
                </div>
              )}
            </div>
          </div>
        </header>

        <DisclaimerBanner />

        {error && (
          <div className="px-4 pt-4 md:px-6 lg:px-10">
            <div className="mx-auto max-w-[1440px]">
              <ErrorBanner message={error} />
            </div>
          </div>
        )}

        <main className="flex-1 px-4 py-6 md:px-6 md:py-8 lg:px-10">
          <div className="mx-auto max-w-[1440px]">
            <Outlet />
          </div>
        </main>

        <footer className="border-t border-slate-200/70 bg-white/60 px-4 py-4 text-center text-[11px] text-slate-500 backdrop-blur md:px-6 lg:px-10">
          <div className="mx-auto flex max-w-[1440px] items-center justify-between">
            <span>GlucoTwin AI · Predictive Digital Twin</span>
            {twin?.last_updated && (
              <span className="hidden sm:block">
                Updated {new Date(twin.last_updated).toLocaleString("en-GB", { hour12: false })}
              </span>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
}
