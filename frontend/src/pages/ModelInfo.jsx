import { BrainCircuit, Database, GitFork, Info, Scale } from "lucide-react";
import { useApp } from "../store";
import { ErrorBanner, PageHeader, Panel, Spinner, SyntheticTag } from "../components/ui";

export default function ModelInfo() {
  const { metrics, health, loading, setError } = useApp();

  if (loading) return <Spinner label="Loading model info…" />;
  if (!metrics) {
    return (
      <>
        <PageHeader
          title="Model Information"
          breadcrumb="Analytics"
          subtitle="Reproducible forecasting pipeline — type, data, methodology, metrics and limitations."
        />
        <ErrorBanner
          message="Model metrics are unavailable. Run `python -m backend.scripts.train_model` from the project root, then restart the API."
          onRetry={() => {
            setError(null);
            window.location.reload();
          }}
        />
      </>
    );
  }

  const horizons = Object.entries(metrics.horizons || {}).sort((a, b) => Number(a[0]) - Number(b[0]));

  return (
    <>
      <PageHeader
        title="Model Information"
        breadcrumb="Analytics"
        subtitle="Reproducible forecasting pipeline — type, data, methodology, metrics and limitations."
        actions={<SyntheticTag />}
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel title="Model & task">
          <dl className="space-y-1.5 text-[13px]">
            <div className="flex justify-between">
              <dt className="text-slate-500">Framework</dt>
              <dd className="font-medium text-slate-900">{metrics.framework}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-500">Version</dt>
              <dd className="mono-num font-medium text-slate-900">{metrics.model_version}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-500">Task</dt>
              <dd className="font-medium text-slate-900">regression</dd>
            </div>
          </dl>
          <p className="mt-2 text-[12px] leading-relaxed text-slate-500">{metrics.task}</p>
        </Panel>

        <Panel title="Training data">
          <p className="text-[13px] text-slate-700">{metrics.training_data_source}</p>
          <p className="mt-2 text-[12px] leading-relaxed text-slate-500">
            8 synthetic patient profiles · 16,128 sensor readings (5-min cadence, 7 days). Deterministic
            seed 42. Patient IDs and timestamps are excluded from predictive features.
          </p>
        </Panel>

        <Panel title="Train / test methodology">
          <p className="text-[13px] text-slate-700">{metrics.split_method}</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-[12px] text-slate-500">
            <li>Features at time t use only data available at or before t.</li>
            <li>Labels are glucose at t + horizon (30/60/90/120 min).</li>
            <li>Models compared: persistence baseline, Ridge, Gradient Boosting.</li>
            <li>Selected model = best MAE per horizon.</li>
          </ul>
        </Panel>
      </div>

      <div className="mt-4">
        <Panel title="Evaluation on held-out synthetic test data" bodyClass="p-0">
          <div className="thin-scroll overflow-x-auto">
            <table className="table min-w-[920px]">
              <thead>
                <tr>
                  <th>Horizon</th>
                  <th>Selected</th>
                  <th className="text-right">MAE (mg/dL)</th>
                  <th className="text-right">RMSE (mg/dL)</th>
                  <th className="text-right">Persistence MAE</th>
                  <th className="text-right">Ridge MAE</th>
                  <th className="text-right">GB MAE</th>
                  <th className="text-right">Δ vs persistence</th>
                  <th className="text-right">Test rows</th>
                </tr>
              </thead>
              <tbody>
                {horizons.map(([h, m]) => (
                  <tr key={h}>
                    <td className="font-medium text-slate-900">+{h} min</td>
                    <td className="text-slate-600">{m.selected_model}</td>
                    <td className="mono-num text-right font-medium">{m.metrics?.mae ?? "—"}</td>
                    <td className="mono-num text-right">{m.metrics?.rmse ?? "—"}</td>
                    <td className="mono-num text-right">{m.baselines?.persistence?.mae ?? "—"}</td>
                    <td className="mono-num text-right">{m.baselines?.ridge_regression?.mae ?? "—"}</td>
                    <td className="mono-num text-right">{m.baselines?.gradient_boosting?.mae ?? "—"}</td>
                    <td className="mono-num text-right text-teal-700">
                      {m.mae_improvement_over_persistence ?? "—"}
                    </td>
                    <td className="mono-num text-right">{m.rows_test ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="px-4 py-2 text-[11px] text-slate-500">
            All units mg/dL. Metrics demonstrate technical functioning on synthetic data only and do
            not establish clinical accuracy.
          </div>
        </Panel>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Limitations & validation requirements">
          <ul className="list-disc space-y-1.5 pl-5 text-[13px] leading-relaxed text-slate-600">
            <li>Trained and evaluated exclusively on generated, non-clinical synthetic data.</li>
            <li>No external validation, no regulatory clearance — an educational prototype, not a medical device.</li>
            <li>Forecast context beyond the input window is held constant in the demo trajectory.</li>
            <li>Thresholds are configurable demonstration values. Real use requires clinician oversight.</li>
            <li>Missing data handling is a research choice, not a clinical protocol.</li>
            <li>Models trained on one population should not be applied directly to others.</li>
          </ul>
        </Panel>

        <Panel title="Safety disclosure">
          <p className="text-[13px] leading-relaxed text-slate-600">{metrics.disclaimer}</p>
          <div className="mt-3 border-t border-slate-100 pt-3 flex items-start gap-2 text-[12px] text-slate-500">
            <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
              Keep this prototype clearly separated from clinical workflows. Any exported reports
              retain synthetic labels and non-clinical disclaimers.
            </span>
          </div>
        </Panel>
      </div>
    </>
  );
}
