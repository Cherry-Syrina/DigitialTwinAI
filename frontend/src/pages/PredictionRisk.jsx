import { useCallback, useEffect, useState } from "react";
import { BarChart3, BrainCircuit, Gauge, Info, Sparkles, TriangleAlert } from "lucide-react";
import { useApp } from "../store";
import { api } from "../api";
import {
  EmptyState,
  ErrorBanner,
  Metric,
  PageHeader,
  Panel,
  RiskBadge,
  Spinner,
  ValueRow,
  fmtDuration,
  fmtTime,
} from "../components/ui";

const HORIZONS = [30, 60, 90, 120];

function Micmg({ v }) {
  return <span className="tabular-nums">{v} mg/dL</span>;
}

export default function PredictionRisk() {
  const { selectedId, twin, metrics, thresholds, busy } = useApp();
  const [horizon, setHorizon] = useState(60);
  const [local, setLocal] = useState(null);
  const [localError, setLocalError] = useState(null);
  const [loading, setLoading] = useState(false);

  const run = useCallback(async () => {
    if (!selectedId) return;
    setLoading(true);
    setLocalError(null);
    try {
      const pred = await api.predict(selectedId, { horizon_minutes: horizon, explain: true });
      setLocal(pred);
    } catch (err) {
      setLocalError(err.message);
    } finally {
      setLoading(false);
    }
  }, [selectedId, horizon]);

  useEffect(() => {
    run();
  }, [run]);

  const prediction = local || twin?.prediction || null;
  const contributions = local?.feature_contributions || [];
  // Risk lives in different places depending on the source:
  //  - POST /predict nests `risk` inside the response body (the prediction).
  //  - GET /digital-twin returns `risk` as a SIBLING of `prediction`
  //    (see TwinResponse in backend/app/schemas/api.py).
  // Read from both shapes so a pending/failed predict call falls back safely.
  const risk = local?.risk ?? twin?.risk ?? null;

  // threshold crossings in trajectory
  const crossings = [];
  for (const p of prediction?.trajectory || []) {
    const v = p.predicted_glucose_mg_dl;
    if (thresholds && typeof v === "number" && v > thresholds.hyper_high_mg_dl) {
      crossings.push({ type: "hyperglycemia", ts: p.timestamp, v, threshold: thresholds.hyper_high_mg_dl });
    } else if (thresholds && typeof v === "number" && v < thresholds.hypo_low_mg_dl) {
      crossings.push({ type: "hypoglycemia", ts: p.timestamp, v, threshold: thresholds.hypo_low_mg_dl });
    }
  }

  const horizonMetrics = metrics?.horizons?.[String(horizon)];

  return (
    <>
      <PageHeader
        title="Prediction & Risk Analysis"
        breadcrumb="Analytics"
        subtitle="Forecast values at future timestamps, threshold crossings, uncertainty and model performance."
        actions={
          <div
            className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white p-0.5"
            role="group"
            aria-label="Forecast horizon"
          >
            {HORIZONS.map((h) => (
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

      {(busy || loading) && !prediction ? <Spinner /> : null}
      {localError && <div className="mt-1 mb-4"><ErrorBanner message={localError} onRetry={run} /></div>}
      {!prediction && !busy && !loading && (
        <div className="card">
          <EmptyState
            icon={Gauge}
            title="No prediction available"
            description={selectedId ? "No prediction data available. Predictions need a trained model and a valid observation window. Add readings, or train the models from the project root if the server reports missing artifacts." : "Select a patient or register a demonstration profile before requesting a forecast."}
            action={
              selectedId ? (
                <>
                  <a className="btn-primary" href="#/data-entry">Add readings</a>
                  <span className="rounded-lg bg-slate-100 px-3 py-2 text-[12px] text-slate-700">python -m backend.scripts.train_model</span>
                </>
              ) : (
                <>
                  <a className="btn-primary" href="#/patients">Choose patient</a>
                  <a className="btn-secondary" href="#/patients/new">Add patient</a>
                </>
              )
            }
          />
        </div>
      )}

      {prediction && (
        <>
          <div className="mb-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
            <Panel title={`Forecast at +${prediction.horizon_minutes} min`} subtitle="Point forecast for the selected horizon">
              <Metric
                label="Expected glucose"
                tone="teal"
                value={prediction.predicted_glucose_mg_dl}
                unit="mg/dL"
                hint={fmtTime(prediction.prediction_timestamp)}
              />
              <div className="mt-3 space-y-2 border-t border-slate-100 pt-3">
                <div className="flex items-center justify-between text-[13px]">
                  <span className="text-slate-500">Current glucose</span>
                  <Micmg v={prediction.current_glucose_mg_dl ?? "n/a"} />
                </div>
                <div className="flex items-center justify-between text-[13px]">
                  <span className="text-slate-500">Overall risk</span>
                  <RiskBadge level={risk?.level} />
                </div>
              </div>
              {risk && (
                <div className="mt-3 rounded-md bg-slate-50 px-3 py-2 text-[12px] text-slate-600">
                  Predicted range over horizon: {risk.predicted_min_mg_dl ?? "n/a"} –{" "}
                  {risk.predicted_max_mg_dl ?? "n/a"} mg/dL (assessed {risk.assessed_values_count ?? "n/a"} values)
                </div>
              )}
              <p className="mt-3 text-[11px] leading-relaxed text-slate-500">{prediction.disclaimer}</p>
            </Panel>

            <Panel title="Predicted trajectory" subtitle="Values at each trained horizon">
              <table className="table table-compact">
                <thead>
                  <tr>
                    <th>Horizon</th>
                    <th>Timestamp</th>
                    <th className="text-right">Predicted</th>
                  </tr>
                </thead>
                <tbody>
                  {(prediction.trajectory || []).map((p) => (
                    <tr key={p.horizon_minutes}>
                      <td className="font-medium text-slate-900">+{p.horizon_minutes} min</td>
                      <td className="mono-num text-slate-500">{fmtTime(p.timestamp)}</td>
                      <td
                        className={`mono-num text-right font-medium ${
                          p.predicted_glucose_mg_dl > thresholds?.hyper_high_mg_dl ? "text-amber-700" : "text-slate-900"
                        }`}
                      >
                        {p.predicted_glucose_mg_dl} mg/dL
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="mt-3 border-t border-slate-100 pt-3">
                <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-slate-500">
                  Threshold crossings
                </h3>
                {crossings.length === 0 ? (
                  <p className="text-[13px] text-slate-500">None within this horizon.</p>
                ) : (
                  <ul className="space-y-1.5">
                    {crossings.map((c, i) => (
                      <li key={i} className="rounded bg-slate-50 px-2.5 py-1.5 text-[12px] text-slate-700">
                        <span className="font-medium">{c.type}</span> at {fmtTime(c.ts)} — {c.v} mg/dL vs
                        threshold {c.threshold}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </Panel>

            <Panel title={`Model metrics @ +${horizon}m`} subtitle="Held-out synthetic test data">
              {horizonMetrics ? (
                <div className="space-y-0.5">
                  <ValueRow label="Selected model" value={horizonMetrics.selected_model ?? "n/a"} />
                  <ValueRow label="Test rows" value={horizonMetrics.rows_test ?? "n/a"} />
                  <ValueRow
                    label="MAE"
                    value={horizonMetrics.metrics?.mae != null ? `${horizonMetrics.metrics.mae} mg/dL` : "n/a"}
                    mono
                  />
                  <ValueRow
                    label="RMSE"
                    value={horizonMetrics.metrics?.rmse != null ? `${horizonMetrics.metrics.rmse} mg/dL` : "n/a"}
                    mono
                  />
                  <ValueRow
                    label="Persistence MAE"
                    value={
                      horizonMetrics.baselines?.persistence?.mae != null
                        ? `${horizonMetrics.baselines.persistence.mae} mg/dL`
                        : "n/a"
                    }
                    mono
                  />
                  <ValueRow
                    label="Improvement vs baseline"
                    value={
                      horizonMetrics.mae_improvement_over_persistence != null
                        ? `${horizonMetrics.mae_improvement_over_persistence} mg/dL`
                        : "n/a"
                    }
                    mono
                  />
                </div>
              ) : (
                <div className="text-[13px] text-slate-500">
                  <p>No metrics for this horizon yet.</p>
                  <p className="mt-1 text-[12px] text-slate-500">
                    <code className="rounded bg-slate-100 px-1.5 py-0.5">python -m backend.scripts.train_model</code> from the project root.
                  </p>
                </div>
              )}
              <div className="mt-3 border-t border-slate-100 pt-3 text-[11px] leading-relaxed text-slate-500">
                Time-ordered 70/15/15 train/validation/test split; model selection uses validation, while the final test segment is reserved for evaluation and chronological interval calibration/coverage. Metrics are on
                held-out synthetic test data only and do not establish clinical accuracy.
              </div>
            </Panel>
          </div>

          <Panel
            title="Contributing factors"
            subtitle="Approximate local sensitivity for the selected horizon's model"
          >
            {contributions.length === 0 ? (
              <p className="text-[13px] text-slate-500">
                No per-prediction explanation produced — feature contributions require the selected
                horizon's model artifact.
              </p>
            ) : (
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {contributions.map((c) => (
                  <div key={c.feature} className="rounded-md border border-slate-200 p-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-[12.5px] font-medium text-slate-800">
                        {c.feature.replace(/_/g, " ")}
                      </span>
                      <span
                        className={`mono-num text-[12.5px] font-semibold ${
                          c.contribution >= 0 ? "text-amber-700" : "text-teal-700"
                        }`}
                      >
                        {c.contribution >= 0 ? "+" : ""}
                        {c.contribution}
                      </span>
                    </div>
                    <div className="mt-1.5 h-1 w-full rounded bg-slate-100">
                      <div
                        className="h-1 rounded bg-teal-600"
                        style={{ width: `${Math.min(100, c.relative_share_pct)}%` }}
                      />
                    </div>
                    <div className="mt-1 text-[10.5px] text-slate-500">
                      {c.relative_share_pct}% of top contributing features
                    </div>
                  </div>
                ))}
              </div>
            )}
            <div className="mt-3 flex items-start gap-2 border-t border-slate-100 pt-3 text-[11px] leading-relaxed text-slate-500">
              <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-500" />
              <span>
                Contributions are an approximate local sensitivity — the change in prediction when a
                feature is replaced by its training-set median. This is a model-derived diagnostic, not
                a clinical explanation. Threshold flags are configurable demonstration values, not
                validated for any patient.
              </span>
            </div>
          </Panel>
        </>
      )}
    </>
  );
}
