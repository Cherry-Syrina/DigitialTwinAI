import { Link } from "react-router-dom";
import { ArrowUpRight, Pencil, UploadCloud, UserRound } from "lucide-react";
import { useApp } from "../store";
import { DataTag, EmptyState, PageHeader, Panel, Spinner, ValueRow, fmtTime } from "../components/ui";

export default function Profile() {
  const { profile, history, twin, loading, selectedId } = useApp();

  if (loading) return <Spinner label="Loading profile…" />;
  if (!profile)
    return (
      <>
        <PageHeader title="Patient Profile" breadcrumb="Cohort" />
        <div className="card">
          <EmptyState
            icon={UserRound}
            title="No patient selected"
            description="Choose an existing patient or register a demonstration profile to view a patient record."
            action={<><Link className="btn-primary" to="/patients">Choose patient</Link><Link className="btn-secondary" to="/patients/new">Add patient</Link></>}
          />
        </div>
      </>
    );

  const latest = twin?.latest_reading;

  return (
    <>
      <PageHeader
        title={profile.name}
        breadcrumb="Cohort"
        subtitle="Demographics, medical history, EHR records and recent sensor activity."
        meta={
          <>
            <DataTag label={profile.data_label} />
            <span className="badge bg-slate-100 text-slate-600">{profile.patient_id}</span>
          </>
        }
        actions={
          <>
            <Link className="btn-secondary" to="/data-entry">
              <UploadCloud className="h-4 w-4" /> Add medical data
            </Link>
            <Link className="btn-secondary" to={`/patients/${selectedId}/edit`}>
              <Pencil className="h-4 w-4" /> Edit profile
            </Link>
            <Link className="btn-primary" to="/overview">
              Open in dashboard
              <ArrowUpRight className="h-4 w-4" />
            </Link>
          </>
        }
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel title="Demographics">
          <ValueRow label="Age" value={profile.age} />
          <ValueRow label="Sex" value={profile.sex} />
          <ValueRow label="Diabetes type" value={profile.diabetes_type} />
          <ValueRow label="Years since diagnosis" value={profile.years_since_diagnosis} />
          <ValueRow label="Height / Weight" value={`${profile.height_cm} cm / ${profile.weight_kg} kg`} />
          <ValueRow label="BMI" value={profile.bmi} />
          <ValueRow label="Activity level" value={profile.activity_level} />
          <ValueRow label="Smoking status" value={profile.smoking_status} />
        </Panel>

        <Panel title="Relevant medical history">
          {profile.medical_history?.length ? (
            <ul className="list-disc space-y-1 pl-5 text-[13px] text-slate-700">
              {profile.medical_history.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          ) : (
            <p className="text-[13px] text-slate-500">No conditions recorded.</p>
          )}
          <h3 className="card-title mt-4 mb-2">Current medications</h3>
          {profile.current_medications?.length ? (
            <ul className="list-disc space-y-1 pl-5 text-[13px] text-slate-700">
              {profile.current_medications.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          ) : (
            <p className="text-[13px] text-slate-500">None recorded.</p>
          )}
          <div className="mt-4 border-t border-slate-100 pt-3 text-[12px] text-slate-500">
            Family history: {profile.family_history || "—"}
          </div>
        </Panel>

        <Panel title="Previous glucose summaries">
          <div className="space-y-2">
            {(profile.glucose_summaries || []).map((s) => (
              <div key={s.summary_period} className="rounded-md border border-slate-200 p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[13px] font-medium text-slate-900">{s.summary_period}</span>
                  <span className="text-[11px] text-slate-500">ends {fmtTime(s.summary_end_date)}</span>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-1 text-[12px] text-slate-600">
                  <span>
                    Mean: <b className="mono-num text-slate-900">{s.mean_glucose_mg_dl}</b> mg/dL
                  </span>
                  <span>
                    HbA1c: <b className="mono-num text-slate-900">{s.hba1c_pct}</b>%
                  </span>
                  <span>
                    TIR: <b className="mono-num text-slate-900">{s.time_in_range_pct}</b>%
                  </span>
                  <span>
                    Readings: <b className="mono-num text-slate-900">{s.readings_count}</b>
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="EHR-like records" bodyClass="p-0">
          <div className="thin-scroll overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Type</th>
                  <th className="text-right">HbA1c %</th>
                  <th className="text-right">BP</th>
                  <th className="text-right">LDL</th>
                </tr>
              </thead>
              <tbody>
                {(profile.ehr_records || []).slice(0, 12).map((r) => (
                  <tr key={r.record_id}>
                    <td className="mono-num text-slate-500">{r.record_date}</td>
                    <td className="text-slate-900">{r.record_type}</td>
                    <td className="mono-num text-right">{r.hba1c_pct ?? "—"}</td>
                    <td className="mono-num text-right">
                      {r.systolic_bp && r.diastolic_bp ? `${r.systolic_bp}/${r.diastolic_bp}` : "—"}
                    </td>
                    <td className="mono-num text-right">{r.ldl_mg_dl ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="Recent activity & sensors" subtitle="Last 60 readings">
          {latest && (
            <div className="mb-3 flex items-center justify-between rounded-md border border-slate-200 px-3 py-2 text-[13px]">
              <span className="text-slate-500">Latest reading</span>
              <span className="font-medium text-slate-900">
                {fmtTime(latest.timestamp)} · glucose{" "}
                <span className="mono-num">{latest.glucose_mg_dl}</span> mg/dL · HR{" "}
                <span className="mono-num">{latest.heart_rate_bpm}</span> bpm
              </span>
            </div>
          )}
          <div className="thin-scroll max-h-80 overflow-y-auto">
            <table className="table table-compact">
              <thead className="sticky top-0 z-10">
                <tr>
                  <th>Time</th>
                  <th className="text-right">Glucose</th>
                  <th className="text-right">HR</th>
                  <th className="text-right">Steps</th>
                  <th>Sleep</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {(history || [])
                  .slice(-60)
                  .reverse()
                  .map((r) => (
                    <tr key={r.timestamp}>
                      <td className="mono-num text-slate-500">{fmtTime(r.timestamp)}</td>
                      <td className="mono-num text-right font-medium text-slate-900">
                        {r.glucose_mg_dl ?? "–"}
                      </td>
                      <td className="mono-num text-right text-slate-600">{r.heart_rate_bpm ?? "–"}</td>
                      <td className="mono-num text-right text-slate-600">{r.steps_5min ?? 0}</td>
                      <td className="text-slate-600">{r.sleep_minutes ? "asleep" : "awake"}</td>
                      <td className="text-[11px] text-slate-500">
                        {r.source === "doctor_entered_reading" ? "entered" : "sensor"}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </>
  );
}
