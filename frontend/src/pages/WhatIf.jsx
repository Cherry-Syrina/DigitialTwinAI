import { useState } from "react";
import { Link } from "react-router-dom";
import { Beaker, FileText, FlaskConical, Loader2, TriangleAlert } from "lucide-react";
import { useApp } from "../store";
import { api } from "../api";
import GlucoseChart from "../components/GlucoseChart";
import { EmptyState, ErrorBanner, PageHeader, Panel, RiskBadge, SyntheticTag } from "../components/ui";

const FIELDS = [
  {
    key: "glucose_offset_mg_dl",
    label: "Glucose offset (shift observed window)",
    min: -60,
    max: 60,
    step: 5,
    default: 0,
    unit: "mg/dL",
    tip: "Hypothetical shift applied to the last 60 minutes of glucose readings.",
  },
  {
    key: "steps_last_60m",
    label: "Activity — steps in last hour",
    min: 0,
    max: 6000,
    step: 100,
    default: 400,
    unit: "steps",
    tip: "Hypothetical physical activity in the observation window.",
  },
  {
    key: "heart_rate_last_60m",
    label: "Average heart rate (last hour)",
    min: 40,
    max: 190,
    step: 5,
    default: 75,
    unit: "bpm",
    tip: "Hypothetical average heart rate over the window.",
  },
  {
    key: "sleep_hours_24h",
    label: "Sleep in last 24 hours",
    min: 0,
    max: 14,
    step: 0.5,
    default: 7,
    unit: "h",
    tip: "Hypothetical sleep duration over the past day.",
  },
  {
    key: "minutes_since_meal",
    label: "Time since most recent meal",
    min: 0,
    max: 480,
    step: 15,
    default: 120,
    unit: "min",
    tip: "Hypothetical time since the last meal event.",
  },
  {
    key: "meal_event_recent",
    label: "Meal in last 30 minutes",
    min: 0,
    max: 1,
    step: 1,
    default: 0,
    unit: "0/1",
    tip: "Hypothetical recent meal flag (1 = meal just occurred, 0 = no).",
  },
];

export default function WhatIf() {
  const { selectedId, history, twin, thresholds } = useApp();
  const [values, setValues] = useState({});
  const [horizon, setHorizon] = useState(60);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [running, setRunning] = useState(false);

  const set = (key, v) => setValues((prev) => ({ ...prev, [key]: Number(v) }));

  const run = async () => {
    if (!selectedId) return;
    setRunning(true);
    setError(null);
    try {
      const res = await api.whatIf(selectedId, { horizon_minutes: horizon, overrides: values });
      setResult(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
    }
  };

  const baselineTraj = twin?.prediction?.trajectory || [];

  return (
    <>
      <PageHeader
        title="What-if Simulation"
        breadcrumb="Analytics"
        subtitle="Adjust hypothetical inputs to a trained model and compare the simulated forecast against the baseline."
        actions={
          <div
            className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white p-0.5"
            role="group"
            aria-label="Forecast horizon"
          >
            {[30, 60, 90, 120].map((h) => (
              <button
                key={h}
                onClick={() => setHorizon(h)}
                aria-pressed={horizon === h}
                className={`rounded px-2.5 py-1 text-[12.5px] font-medium transition ${
                  horizon === h ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                +{h}m
              </button>
            ))}
          </div>
        }
      />

      {!selectedId && (
        <div className="card mb-4">
          <EmptyState title="Choose a patient to begin" description="A what-if forecast needs a patient profile and observation history." action={<Link className="btn-primary" to="/patients">Choose patient</Link>} />
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel title="Hypothetical inputs" subtitle="Sliders map directly to model features">
          <div className="space-y-4">
            {FIELDS.map((f) => (
              <div key={f.key}>
                <div className="mb-1 flex items-center justify-between gap-2">
                  <label className="text-[12.5px] font-medium text-slate-700" htmlFor={f.key}>
                    {f.label}
                  </label>
                  <span className="mono-num text-[12.5px] font-medium text-slate-900">
                    {values[f.key] ?? f.default} {f.unit}
                  </span>
                </div>
                <input
                  id={f.key}
                  type="range"
                  className="w-full accent-teal-600"
                  min={f.min}
                  max={f.max}
                  step={f.step}
                  value={values[f.key] ?? f.default}
                  onChange={(e) => set(f.key, e.target.value)}
                />
                <p className="mt-0.5 text-[11px] text-slate-500">{f.tip}</p>
              </div>
            ))}
          </div>
          <button className="btn-primary mt-4 w-full justify-center" onClick={run} disabled={running || !selectedId}>
            {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <FlaskConical className="h-4 w-4" />}
            Recalculate scenario
          </button>
          {error && (
            <div className="mt-3">
              <ErrorBanner message={error} />
            </div>
          )}
        </Panel>

        <div className="space-y-4 lg:col-span-2">
          <Panel
            title="Simulated outcome"
            subtitle="Baseline vs hypothetical scenario"
            action={<SyntheticTag />}
          >
            {result ? (
              <>
                <div className="mb-3 flex flex-wrap items-center gap-3 text-[13px]">
                  <span className="text-slate-500">
                    Baseline (~+{result.horizon_minutes}m):{" "}
                    <b className="mono-num text-slate-900">
                      {baselineTraj.find((p) => p.horizon_minutes === result.horizon_minutes)?.predicted_glucose_mg_dl ?? "n/a"}{" "}
                      mg/dL
                    </b>
                  </span>
                  <span className="text-slate-300">→</span>
                  <span className="text-slate-500">
                    Scenario:{" "}
                    <b className="mono-num text-teal-700">{result.predicted_glucose_mg_dl} mg/dL</b>
                  </span>
                  <RiskBadge level={result.risk?.level} />
                </div>
                <div className="mb-3 flex items-start gap-2 rounded-md bg-slate-50 px-3 py-2 text-[12px] text-slate-700">
                  <Beaker className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-500" />
                  <span>
                    <b>{result.scenario.label}.</b> {result.scenario.note}
                  </span>
                </div>
                <GlucoseChart
                  history={history}
                  trajectory={result.trajectory}
                  thresholds={thresholds}
                  height={280}
                />
              </>
            ) : (
              <div className="flex min-h-64 flex-col items-center justify-center px-6 py-10 text-center">
                <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-2xl bg-teal-50 text-teal-700"><FlaskConical className="h-5 w-5" /></div>
                <h3 className="text-[14px] font-semibold text-slate-900">Your scenario will appear here</h3>
                <p className="mt-1 max-w-sm text-[13px] leading-relaxed text-slate-600">Adjust one or more inputs, then recalculate. The result compares a model-generated scenario with the current forecast.</p>
                {!twin?.prediction && <p className="mt-3 text-[12px] text-amber-800">A baseline forecast is not available yet. Add enough readings or train the model artifacts first.</p>}
              </div>
            )}
          </Panel>

          <div className="card px-4 py-3 text-[11px] leading-relaxed text-slate-500">
            These overrides map directly onto the model's input features. Unsupported or out-of-range
            values are rejected with an explicit error — nothing is silently faked. Results are
            simulated scenarios on synthetic data and must never be used as treatment recommendations.
          </div>
        </div>
      </div>
    </>
  );
}
