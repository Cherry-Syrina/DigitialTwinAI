import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, FastForward, Info, RefreshCw } from "lucide-react";
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

export default function TwinMonitor() {
  const { twin, history, thresholds, busy, advanceDemo, refreshTwin, selectedId } = useApp();
  const [steps, setSteps] = useState(12);

  const traj = twin?.prediction?.trajectory || [];
  const latest = twin?.latest_reading;
  const pipeline = twin?.prediction?.model;
  const modelReady = Boolean(twin?.prediction) && !twin?.model_error;

  return (
    <>
      <PageHeader
        title="Digital Twin Monitor"
        breadcrumb="Monitoring"
        subtitle="Observed sensor readings against the model forecast, with the twin's live state."
        actions={
          <>
            <button type="button" className="btn-secondary" onClick={() => refreshTwin()} disabled={busy}>
              <RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} /> Refresh
            </button>
            <Link className="btn-primary" to="/prediction">
              Predictions &amp; risk
              <ArrowUpRight className="h-4 w-4" />
            </Link>
          </>
        }
      />

      <Panel
        title="Timeline"
        subtitle="Observed readings (solid) and model forecast (dashed) separated at the current time"
        className="mb-4"
      >
        {modelReady ? (
          <GlucoseChart history={history} trajectory={traj} thresholds={thresholds} height={380} />
        ) : twin?.model_error ? (
          <ModelUnavailable message={twin.model_error} onRetry={refreshTwin} />
        ) : (
          <EmptyState
            icon={Info}
            title="Twin not initialised"
            description={selectedId ? "The twin needs a valid observation window before it can forecast. Add a reading or replay the synthetic feed to build the observation window." : "Select or register a patient before starting a twin."}
            action={selectedId ? (
              <>
                <Link className="btn-primary" to="/data-entry">Add readings</Link>
                <button type="button" className="btn-secondary" onClick={() => advanceDemo(steps, selectedId)} disabled={busy || !(twin?.buffer_rows_remaining > 0)}>
                  <FastForward className="h-4 w-4" /> Replay feed
                </button>
              </>
            ) : <Link className="btn-primary" to="/patients/new">Add patient</Link>}
          />
        )}
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel title="Feed state" subtitle="Synthetic replay, not live hardware">
          {latest ? (
            <div className="space-y-3">
              <Metric label="Simulated time" value={fmtTime(twin.simulated_time)} />
              <Metric
                label="Last reading"
                value={`${latest.glucose_mg_dl ?? "—"} mg/dL`}
                hint={fmtTime(latest.timestamp)}
              />
              <Metric
                label="Readings observed"
                value={`${twin.observed_rows} / ${twin.total_rows}`}
                hint={`${twin.buffer_rows_remaining} buffered readings remaining`}
              />
              <Metric
                label="Cadence"
                value={`${twin.sensor_feed.minutes_between_readings} min`}
                hint={twin.sensor_feed.type}
              />
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-[13px] text-slate-600">No readings available for this patient yet.</p>
              <Link className="btn-secondary" to="/data-entry">Add readings</Link>
            </div>
          )}
        </Panel>

        <Panel title="Advance the feed" subtitle="Replay further generated readings into the twin">
          <div className="space-y-3">
            <div>
              <label className="label" htmlFor="advance-steps">
                Readings to replay
              </label>
              <select
                id="advance-steps"
                className="input"
                value={steps}
                onChange={(e) => setSteps(Number(e.target.value))}
              >
                <option value={6}>6 readings — 30 min</option>
                <option value={12}>12 readings — 1 hour</option>
                <option value={24}>24 readings — 2 hours</option>
                <option value={48}>48 readings — 4 hours</option>
              </select>
            </div>
            <button
              className="btn-primary w-full justify-center"
              disabled={busy || !selectedId}
              onClick={() => advanceDemo(steps, selectedId)}
            >
              <FastForward className="h-4 w-4" /> Advance {steps} readings
            </button>
            {twin && twin.buffer_rows_remaining <= 0 && (
              <p className="text-[11px] text-amber-700">
                Replay buffer exhausted — every generated reading is now observed.
              </p>
            )}
          </div>
        </Panel>

        <Panel title="Current forecast" subtitle="Latest prediction held by the twin">
          {modelReady ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-[13px] text-slate-500">Risk</span>
                <RiskBadge level={twin.risk?.level} />
              </div>
              <Metric
                label={`Forecast +${twin.prediction.horizon_minutes} min`}
                tone="teal"
                value={twin.prediction.predicted_glucose_mg_dl}
                unit="mg/dL"
                hint={fmtTime(twin.prediction.prediction_timestamp)}
              />
              <div className="border-t border-slate-100 pt-3 text-[11px] leading-relaxed text-slate-500">
                {pipeline?.type} v{pipeline?.version} · input window {pipeline?.input_window?.window_rows} readings
                ({fmtTime(pipeline?.input_window?.window_start)} → {fmtTime(pipeline?.input_window?.window_end)})
              </div>
            </div>
          ) : (
            <div className="text-[13px] text-slate-500">
              {twin?.model_error || "No prediction available yet."}
            </div>
          )}
        </Panel>
      </div>
    </>
  );
}
