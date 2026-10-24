import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FileText, Pencil, Plus, Search, UserRound, Users } from "lucide-react";
import { useApp } from "../store";
import { DataTag, EmptyState, PageHeader, Panel, Spinner } from "../components/ui";

export default function Patients() {
  const { patients, selectPatient, loading } = useApp();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return patients;
    return patients.filter((p) =>
      [p.patient_id, p.name, p.diabetes_type, p.sex].some((v) =>
        String(v ?? "").toLowerCase().includes(q)
      )
    );
  }, [patients, query]);

  const open = (id) => {
    selectPatient(id);
    navigate("/overview");
  };

  return (
    <>
      <PageHeader
        title="Patients"
        breadcrumb="Cohort"
        subtitle="Every synthetic dataset profile and every patient registered through this application."
        actions={
          <Link className="btn-primary" to="/patients/new">
            <Plus className="h-4 w-4" /> Add patient
          </Link>
        }
      />

      <Panel
        title="Patient roster"
        subtitle={`${filtered.length} of ${patients.length} patient${patients.length === 1 ? "" : "s"}`}
        action={
          <div className="relative w-56">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" />
            <input
              type="search"
              className="input h-8 py-1 pl-8 text-[12.5px]"
              placeholder="Search name, ID or type"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search patients"
            />
          </div>
        }
        bodyClass="p-0"
      >
        {loading && patients.length === 0 ? (
          <Spinner label="Loading patients…" />
        ) : patients.length === 0 ? (
          <EmptyState
            icon={Users}
            title="No patients available"
            description="Register a patient to start entering readings, running the digital twin and generating reports."
            action={
              <Link className="btn-primary" to="/patients/new">
                <Plus className="h-4 w-4" /> Add patient
              </Link>
            }
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={Search}
            title="No matching patients"
            description={`No patient matches “${query}”. Clear the search to see the full roster.`}
            action={
              <button type="button" className="btn-secondary" onClick={() => setQuery("")}>
                Clear search
              </button>
            }
          />
        ) : (
          <div className="thin-scroll overflow-x-auto">
            <table className="table min-w-[840px]">
              <thead>
                <tr>
                  <th>Patient ID</th>
                  <th>Name</th>
                  <th>Age / Sex</th>
                  <th>Diabetes</th>
                  <th className="text-right">Latest glucose</th>
                  <th className="text-right">Readings</th>
                  <th>Record</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((p) => (
                  <tr key={p.patient_id}>
                    <td className="font-medium text-slate-900">{p.patient_id}</td>
                    <td className="font-medium text-slate-900">{p.name}</td>
                    <td className="mono-num text-slate-600">
                      {p.age} / {p.sex}
                    </td>
                    <td className="text-slate-600">{p.diabetes_type}</td>
                    <td className="mono-num text-right font-medium text-slate-900">
                      {p.latest_glucose_mg_dl ?? "—"}
                      {p.latest_glucose_mg_dl ? " mg/dL" : ""}
                    </td>
                    <td className="mono-num text-right text-slate-600">{p.sensor_rows ?? "—"}</td>
                    <td>
                      <DataTag label={p.data_label} />
                    </td>
                    <td>
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          className="btn-ghost"
                          onClick={() => open(p.patient_id)}
                          title={`Open ${p.name} in the dashboard`}
                        >
                          <UserRound className="h-3.5 w-3.5" /> Open
                        </button>
                        <Link
                          className="btn-ghost"
                          to={`/patients/${p.patient_id}/edit`}
                          title={`Edit ${p.name}`}
                        >
                          <Pencil className="h-3.5 w-3.5" /> Edit
                        </Link>
                        <button
                          className="btn-ghost"
                          onClick={() => {
                            selectPatient(p.patient_id);
                            navigate("/reports");
                          }}
                          title={`Open the report for ${p.name}`}
                        >
                          <FileText className="h-3.5 w-3.5" /> Report
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
