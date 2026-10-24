import { Link } from "react-router-dom";
import {
  Activity,
  ArrowRight,
  CalendarClock,
  Gauge,
  HeartPulse,
  ScanLine,
  Sparkles,
  TrendingUp,
  UserRound,
} from "lucide-react";
import { useApp } from "../store";
import GlucoseChart from "../components/GlucoseChart";
import {
  EmptyState,
  Metric,
  ModelUnavailable,
  PageHeader,
  Panel,
  RiskBadge,
  fmtTime,
} from "../components/ui";

const fmtClock = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
};

function Illustration() {
  return (
    <svg viewBox="0 0 420 260" className="h-full w-full">
      <defs>
        <linearGradient id="g1" x1="0" y1="0" x2="1" y2="1">
          <stop stopColor="#22d3ee" />
          <stop offset="1" stopColor="#6366f1" />
        </linearGradient>
        <linearGradient id="g2" x1="0" y1="0" x2="0" y2="1">
          <stop stopColor="rgba(20,184,166,0.4)" />
          <stop offset="1" stopColor="rgba(99,102,241,0.12)" />
        </linearGradient>
      </defs>
      <circle cx="340" cy="60" r="80" fill="url(#g2)" opacity="0.8" />
      <circle cx="80" cy="190" r="70" fill="url(#g2)" opacity="0.6" />
      <g stroke="url(#g1)" strokeWidth="2" fill="none" opacity="0.9">
        <path d="M60 150 C120 90 200 110 280 70" />
        <path d="M60 170 C140 120 220 150 320 110" strokeDasharray="6 6" opacity="0.6" />
      </g>
      <g fill="url(#g1)">
        <circle cx="60" cy="150" r="4" />
        <circle cx="140" cy="110" r="3.5" />
        <circle cx="220" cy="130" r="3.5" />
        <circle cx="320" cy="110" r="4" />
      </g>
      <rect x="70" y="40" width="190" height="46" rx="23" fill="rgba(255,255,255,0.18)" />
      <rect x="70" y="40" width="190" height="46" rx="23" stroke="rgba(255,255,255,0.4)" />
      <text x="90" y="68" fontSize="12" fill="white" opacity="0.9">
        Digital Twin · Forecast Ready
      </text>
    </svg>
  );
}

export default function Overview() {
  const { profile, twin, history, thresholds, health, busy, selectedId, refreshTwin, patients } = useApp();

  const traj = twin?.prediction?.trajectory || [];
  const latest = twin?.latest_reading;
  const risk = twin?.risk || null;
  const flags = risk?.flags || [];
  const modelReady = Boolean(twin?.prediction) && !twin?.model_error;

  const patient = profile || patients.find((p) => p.patient_id === selectedId) || null;
  const recentReadings = [...(history || [])].slice(-10).reverse();

  if (!selectedId) {
    return (
      <>
        <PageHeader
          title="Overview"
          breadcrumb="Dashboard"
          subtitle="A premium, API-driven digital twin for glucose forecasting and risk insights."
        />
        <div className="card">
          <EmptyState
            icon={UserRound}
            title="No patient selected"
            description="Select a patient from the header, or register a new one, to start monitoring."
            action={
              <Link className="btn-primary" to="/patients/new">
                Add patient
                <ArrowRight className="h-4 w-4" />
              </Link>
            }
          />
        </div>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Overview"
        breadcrumb="Dashboard"
        subtitle="Precision glucose analytics with observed trends, forecast trajectories and actionable risk signals."
        meta={
          <>
            <span className="chip bg-teal-50 text-teal-700">
              <Activity className="h-3 w-3" />
              {health?.status === "ok" ? "API connected" : `API ${health?.status ?? "checking"}`}
            </span>
            <span className="chip bg-indigo-50 text-indigo-700">
              <Sparkles className="h-3 w-3" />
              Synthetic demo dataset
            </span>
          </>
        }
        actions={
          <>
            <Link className="btn-secondary" to="/patients">
              Cohort
            </Link>
            <Link className="btn-primary" to="/doctor">
              Doctor view
              <ArrowRight className="h-4 w-4" />
            </Link>
          </>
        }
      />

      {/* Hero */}
      <section className="card mb-6 overflow-hidden border-0 bg-[linear-gradient(120deg,#101b35_0%,#172448_46%,#2b2a6b_100%)] shadow-[0_30px_80px_-40px_rgba(16,27,53,0.9)]">
        <div className="relative grid gap-6 p-6 md:grid-cols-[1.2fr_0.8fr] md:p-8">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(560px_260px_at_8%_-10%,rgba(34,211,238,0.22),transparent),radial-gradient(620px_300px_at_92%_0%,rgba(167,139,250,0.2),transparent)]" />
          <div className="relative">
            <div className="eyebrow hero-eyebrow">Digital Twin Intelligence</div>
            <h2 className="mt-2 text-[27px] font-semibold leading-tight tracking-[-0.02em] text-white md:text-[35px]">
              Understand today. Anticipate tomorrow.
            </h2>
            <p className="mt-3 max-w-xl text-[14px] leading-relaxed text-slate-200">
              Predictive glucose monitoring with observed sensor data, calibrated forecasts and
              configurable risk insights — presented in a clear, structured view.
            </p>
            <div className="mt-5 flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-3 rounded-full border border-white/15 bg-white/10 px-4 py-2">
                <HeartPulse className="h-4 w-4 text-cyan-300" />
                <div>
                  <div className="text-[10.5px] uppercase tracking-[0.14em] text-cyan-200">Patient</div>
                  <div className="text-[13px] font-medium text-white">
                    {patient?.name ?? "—"} · {patient?.patient_id ?? selectedId}
                  </div>
                </div>
              </div>
              <span className="chip border border-white/15 bg-white/10 text-slate-200">
                <CalendarClock className="h-3 w-3" />
                {busy ? "Updating…" : `Twin updated ${fmtClock(twin?.last_updated)}`}
              </span>
            </div>
            <div className="mt-6 flex flex-wrap gap-2">
              <Link className="btn-primary" to="/prediction">
                View predictions
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link className="btn-secondary" to="/profile">
                <UserRound className="h-4 w-4" /> Patient profile
              </Link>
              <Link
                className="inline-flex h-9 items-center gap-2 rounded-full border border-white/15 bg-white/10 px-4 text-[13px] font-medium text-white transition hover:bg-white/15"
                to="/twin"
              >
                <ScanLine className="h-4 w-4" /> Digital twin
              </Link>
            </div>
          </div>
          <div className="relative hidden md:block">
            <Illustration />
          </div>
        </div>
      </section>

      {/* KPI strip */}
      <section className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="card card-pad border-teal-100 bg-gradient-to-br from-teal-50/90 to-white">
          <Metric
            label="Current glucose"
            icon={Activity}
            value={latest?.glucose_mg_dl ?? "—"}
            unit="mg/dL"
            hint={latest ? fmtClock(latest.timestamp) : "No reading yet"}
          />
        </div>
        <div className="card card-pad border-indigo-100 bg-gradient-to-br from-indigo-50/90 to-white">
          <Metric
            label="Next forecast"
            icon={TrendingUp}
            tone="indigo"
            value={twin?.prediction ? twin.prediction.predicted_glucose_mg_dl : "—"}
            unit={twin?.prediction ? "mg/dL" : undefined}
            hint={
              twin?.prediction
                ? `+${twin.prediction.horizon_minutes} min · v${twin.prediction.model?.version ?? "—"}`
                : "Not available"
            }
          />
        </div>
        <div className="card card-pad border-amber-100/80 bg-gradient-to-br from-amber-50/70 to-white">
          <div className="metric-label flex items-center gap-1.5">
            <Gauge className="h-3.5 w-3.5 text-slate-500" />
            Risk assessment
          </div>
          <div className="mt-2">
            <RiskBadge level={risk?.level} size="lg" />
          </div>
          <div className="mt-1 text-[11px] text-slate-500">{risk?.label ?? "Not assessed"}</div>
        </div>
        <div className="card card-pad">
          <Metric
            label="Observations"
            icon={CalendarClock}
            value={twin ? `${twin.observed_rows}` : "—"}
            unit={twin ? ` / ${twin.total_rows}` : undefined}
            hint={twin?.simulated_time ? `Simulated ${fmtClock(twin.simulated_time)}` : "—"}
          />
        </div>
      </section>

      {/* Analytics */}
      <section className="grid grid-cols-1 gap-6 xl:grid-cols-[1.6fr_1fr]">
        <Panel
          title="Glucose trend & forecast"
          subtitle="Observed readings with calibrated forecast and uncertainty band"
          action={
            <Link className="btn-ghost" to="/twin">
              Full timeline
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          }
        >
          {modelReady ? (
            <GlucoseChart history={history} trajectory={traj} thresholds={thresholds} height={340} />
          ) : twin?.model_error ? (
            <ModelUnavailable message={twin.model_error} onRetry={refreshTwin} />
          ) : (
            <EmptyState
              icon={ScanLine}
              title="Forecast not ready"
              description="The digital twin needs a valid observation window before producing a forecast."
              action={
                <>
                  <Link className="btn-primary" to="/data-entry">
                    Enter readings
                  </Link>
                  <button type="button" className="btn-secondary" onClick={refreshTwin}>
                    Refresh twin
                  </button>
                </>
              }
            />
          )}
          <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-1 border-t border-slate-200/80 pt-4 text-[11px] text-slate-500">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-5 bg-slate-900" /> Observed
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-5 border-t-2 border-dashed border-indigo-500" /> Forecast
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-5 rounded-sm bg-indigo-500/12" /> 90% interval
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-5 border-t-2 border-dashed border-amber-500" /> High
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-5 border-t-2 border-dashed border-rose-500" /> Low
            </span>
          </div>
        </Panel>

        <div className="space-y-6">
          <Panel title="Risk insights" subtitle="Predicted threshold crossings">
            {flags.length === 0 ? (
              <p className="text-[13px] text-slate-500">
                {risk ? "No threshold violations predicted across the current horizon." : "Risk insights appear when a forecast is available."}
              </p>
            ) : (
              <ul className="space-y-2">
                {flags.map((f, i) => (
                  <li key={i} className="rounded-2xl border border-slate-200/80 px-3 py-2 text-[12.5px] text-slate-700">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold uppercase tracking-wide text-slate-900">{f.type}</span>
                      <span className="text-[11px] text-slate-500">{fmtTime(f.at_timestamp)}</span>
                    </div>
                    <p className="mt-1 text-slate-600">{f.message}</p>
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-4 border-t border-slate-200/80 pt-3 text-[11px] leading-relaxed text-slate-500">
              Configurable demonstration thresholds on synthetic data — not clinically validated and not
              for clinical decision-making.
            </div>
          </Panel>

          <Panel title="Recent observations" bodyClass="p-0">
            {recentReadings.length === 0 ? (
              <EmptyState
                icon={Activity}
                title="No readings yet"
                description="Import a sensor CSV or add a reading to populate the timeline."
                action={
                  <Link className="btn-primary" to="/data-entry">
                    Add medical data
                  </Link>
                }
              />
            ) : (
              <div className="thin-scroll max-h-[22rem] overflow-y-auto">
                <table className="table table-compact">
                  <thead className="sticky top-0 z-10">
                    <tr>
                      <th>Time</th>
                      <th className="text-right">Glucose</th>
                      <th className="text-right">HR</th>
                      <th className="text-right">Steps</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentReadings.map((r) => (
                      <tr key={r.timestamp}>
                        <td className="mono-num text-slate-500">{fmtClock(r.timestamp)}</td>
                        <td className="mono-num text-right font-medium text-slate-900">{r.glucose_mg_dl ?? "–"}</td>
                        <td className="mono-num text-right text-slate-500">{r.heart_rate_bpm ?? "–"}</td>
                        <td className="mono-num text-right text-slate-500">{r.steps_5min ?? "–"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="border-t border-slate-200/80 px-4 py-3">
              <Link className="btn-ghost" to="/profile">
                Full patient profile
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          </Panel>
        </div>
      </section>
    </>
  );
}
