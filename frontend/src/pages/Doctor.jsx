import { useState } from "react";
import { Link } from "react-router-dom";
import { ClipboardList, Download, FileText, Stethoscope } from "lucide-react";
import { useApp } from "../store";
import { api } from "../api";
import { DataTag, EmptyState, ErrorBanner, PageHeader, Panel, RiskBadge, fmtDuration, fmtTime } from "../components/ui";

export default function Doctor() {
  const { profile, twin, history, selectedId, thresholds } = useApp();
  const [report, setReport] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [err, setErr] = useState(null);

  const download = async () => {
    if (!selectedId) return;
    setExporting(true);
    setErr(null);
    try {
      const res = await api.report(selectedId);
      setReport(res);
      const blob = new Blob([res.content_markdown], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `glucotwin-report-${selectedId}.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr(e.message);
    } finally {
      setExporting(false);
    }
  };

  const latest = twin?.latest_reading;
  const flags = twin?.risk?.flags || [];

  if (!profile) {
    return (
      <>
        <PageHeader title="Doctor View" breadcrumb="Output" subtitle="Structured summary and exportable report." />
        <div className="card">
          <EmptyState
            icon={ClipboardList}
            title="No patient selected"
            description="Choose an existing patient or register a demonstration profile to open the structured view."
            action={<><Link className="btn-primary" to="/patients">Choose patient</Link><Link className="btn-secondary" to="/patients/new">Add patient</Link></>}
          />
        </div>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Doctor View"
        breadcrumb="Output"
        subtitle="Structured patient summary, recent observations, forecast and risk flags."
        meta={
          <>
            <DataTag label={profile?.data_label} />
            <span className="badge bg-slate-100 text-slate-600">{profile.patient_id}</span>
          </>
        }
        actions={
          <>
            <Link className="btn-secondary" to="/reports">
              <FileText className="h-4 w-4" /> Reports page
            </Link>
            <button className="btn-primary" onClick={download} disabled={exporting || !selectedId}>
              <Download className="h-4 w-4" /> {exporting ? "Exporting…" : "Export report (.md)"}
            </button>
          </>
        }
      />

      {err && <ErrorBanner message={err} />}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        <Panel title="Patient summary">
          <div className="text-[13px]">
            <div className="font-medium text-slate-900">{profile.name}</div>
            <div className="text-[11px] text-slate-500">{profile.patient_id}</div>
            <dl className="mt-2 space-y-1.5">
              <div className="flex justify-between">
                <dt className="text-slate-500">Age / Sex</dt>
                <dd className="font-medium text-slate-800">
                  {profile.age} / {profile.sex}
                </dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-500">Diabetes</dt>
                <dd className="font-medium text-slate-800">{profile.diabetes_type}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-500">Diagnosed (yrs)</dt>
                <dd className="mono-num font-medium text-slate-800">{profile.years_since_diagnosis}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-500">BMI</dt>
                <dd className="mono-num font-medium text-slate-800">{profile.bmi}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-slate-500">Latest HbA1c</dt>
                <dd className="mono-num font-medium text-slate-800">{profile.glucose_summaries?.[0]?.hba1c_pct}%</dd>
              </div>
            </dl>
          </div>
        </Panel>

        <Panel title="Current status">
          <dl className="space-y-1.5 text-[13px]">
            <div className="flex justify-between">
              <dt className="text-slate-500">Glucose</dt>
              <dd className="mono-num font-medium text-slate-900">{latest?.glucose_mg_dl ?? "n/a"} mg/dL</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-500">Heart rate</dt>
              <dd className="mono-num font-medium text-slate-800">{latest?.heart_rate_bpm ?? "n/a"} bpm</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-500">Last reading</dt>
              <dd className="font-medium text-slate-800">{fmtTime(latest?.timestamp)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-500">In window</dt>
              <dd className="mono-num font-medium text-slate-800">
                {twin?.observed_rows ?? "—"} / {twin?.total_rows ?? "—"}
              </dd>
            </div>
          </dl>
        </Panel>

        <Panel title="Forecast">
          {twin?.prediction ? (
            <div className="space-y-1.5 text-[13px]">
              <div className="flex justify-between">
                <span className="text-slate-500">+{twin.prediction.horizon_minutes}m</span>
                <span className="mono-num font-medium text-slate-900">
                  {twin.prediction.predicted_glucose_mg_dl} mg/dL
                </span>
              </div>
              {twin.prediction.trajectory.map((p) => (
                <div key={p.horizon_minutes} className="flex justify-between text-[12px]">
                  <span className="text-slate-500">+{p.horizon_minutes}m</span>
                  <span className="mono-num text-slate-600">{p.predicted_glucose_mg_dl}</span>
                </div>
              ))}
              <div className="mt-2 border-t border-slate-100 pt-2 text-[11px] text-slate-500">
                model {twin.prediction.model.type} v{twin.prediction.model.version}
              </div>
            </div>
          ) : (
            <p className="text-[13px] text-slate-500">n/a</p>
          )}
        </Panel>

        <Panel title="Risk flags">
          <div className="mb-2">
            <RiskBadge level={twin?.risk?.level} size="lg" />
          </div>
          {flags.length === 0 ? (
            <p className="text-[12px] text-slate-500">No threshold violations predicted at the current horizon.</p>
          ) : (
            <ul className="space-y-1.5">
              {flags.map((f, i) => (
                <li key={i} className="rounded bg-slate-50 px-2.5 py-1.5 text-[12px] text-slate-700">
                  <span className="font-semibold uppercase tracking-wide">{f.type}</span> — {f.message}
                  <div className="text-[10.5px] text-slate-500">at {fmtTime(f.at_timestamp)}</div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Recent observations" subtitle="Last 48 readings" bodyClass="p-0">
          <div className="thin-scroll max-h-[22rem] overflow-y-auto">
            <table className="table table-compact">
              <thead className="sticky top-0 z-10">
                <tr>
                  <th>Time</th>
                  <th className="text-right">Glucose</th>
                  <th className="text-right">Steps</th>
                  <th>Meal</th>
                  <th className="text-right">Since meal</th>
                </tr>
              </thead>
              <tbody>
                {(history || [])
                  .slice(-48)
                  .reverse()
                  .map((r) => (
                    <tr key={r.timestamp}>
                      <td className="mono-num text-slate-500">{fmtTime(r.timestamp)}</td>
                      <td className="mono-num text-right font-medium text-slate-900">
                        {r.glucose_mg_dl ?? "–"}
                      </td>
                      <td className="mono-num text-right text-slate-500">{r.steps_5min ?? 0}</td>
                      <td className="text-slate-500">{r.meal_event ? "yes" : "no"}</td>
                      <td className="mono-num text-right text-slate-500">{fmtDuration(r.minutes_since_meal)}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel
          title="Exportable report"
          subtitle="Standalone Markdown summary"
          action={<Stethoscope className="h-4 w-4 text-slate-500" />}
        >
          <p className="text-[13px] leading-relaxed text-slate-600">
            The exported report includes demographics, medical history, glucose summaries, recent
            observations, digital-twin state, forecast, risk flags, model metrics and thresholds.
            It is clearly labelled as synthetic and non-clinical.
          </p>
          <div className="mt-3 rounded-md border border-slate-200 px-3 py-2">
            <div className="flex items-center gap-2 text-[13px] font-medium text-slate-900">
              <FileText className="h-4 w-4 text-slate-500" /> glucotwin-report-{selectedId}.md
            </div>
            <div className="mt-0.5 text-[11px] text-slate-500">
              {report ? `Generated at ${fmtTime(report.generated_at)}` : "Not generated yet — use Export report above."}
            </div>
          </div>
          <div className="mt-3 border-t border-slate-100 pt-3 text-[11px] leading-relaxed text-slate-500">
            This dashboard and report are educational prototypes on synthetic data; they must not be
            used to diagnose or treat any patient. The application is not a medical device and is
            not clinically validated.
          </div>
        </Panel>
      </div>
    </>
  );
}
