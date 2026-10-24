import { useRef, useState } from "react";
import { ClipboardPlus, Download, FileSpreadsheet, LinkIcon, UploadCloud } from "lucide-react";
import { api } from "../api";
import { useApp } from "../store";
import { DataTag, EmptyState, ErrorBanner, PageHeader, Panel } from "../components/ui";

const CSV_TEMPLATE =
  "timestamp,glucose_mg_dl,heart_rate_bpm,steps_5min,sleep_minutes,meal_event,minutes_since_meal\n" +
  "2026-10-15 08:00:00,132,72,12,0,1,45\n" +
  "2026-10-15 08:30:00,128,70,6,0,0,75\n";

function toApiTimestamp(value) {
  if (!value) return "";
  const [date, time] = value.split("T");
  if (!date) return "";
  if (!time) return `${date} 00:00:00`;
  const parts = time.split(":");
  while (parts.length < 3) parts.push("00");
  return `${date} ${parts.slice(0, 3).join(":")}`;
}

function ImportResultPanel({ result }) {
  if (!result) return null;
  const bad = result.rows?.filter((r) => r.status === "rejected") || [];
  return (
    <div className="mt-3 space-y-2" data-testid="import-result">
      <p className={`text-[13px] font-medium ${result.accepted_count ? "text-teal-800" : "text-amber-800"}`}>
        {result.message}
      </p>
      <div className="text-[11px] text-slate-500">
        {result.accepted_count} accepted · {result.rejected_count} rejected · {result.duplicate_count} duplicate
        {" · "}
        {result.persisted ? "saved to the local database" : "preview only — nothing saved yet"}
      </div>
      {result.rows?.length > 0 && (
        <div className="thin-scroll max-h-64 overflow-auto rounded-md border border-slate-200">
          <table className="table table-compact min-w-[640px]">
            <thead className="sticky top-0">
              <tr>
                <th>#</th>
                <th>Timestamp</th>
                <th className="text-right">Glucose</th>
                <th className="text-right">HR</th>
                <th>Status</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row, i) => (
                <tr key={i}>
                  <td className="mono-num">{row.row_index}</td>
                  <td className="mono-num text-slate-500">{row.timestamp || "—"}</td>
                  <td className="mono-num text-right">{row.glucose_mg_dl ?? "—"}</td>
                  <td className="mono-num text-right">{row.heart_rate_bpm ?? "—"}</td>
                  <td>
                    <span className={row.status === "accepted" ? "text-teal-700" : "text-red-600"}>
                      {row.status}
                    </span>
                  </td>
                  <td className="text-slate-500">
                    {row.status === "rejected"
                      ? row.reason
                      : row.missing?.length
                      ? `missing: ${row.missing.join(", ")}`
                      : "ok"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {bad.length === 0 && result.rejected_count > 0 && (
        <p className="text-[11px] text-slate-500">{result.rejected_count} row(s) were rejected.</p>
      )}
    </div>
  );
}

export default function DataEntry() {
  const { selectedId, patients, refreshAll, profile } = useApp();
  const selected = patients.find((p) => p.patient_id === selectedId);

  const [manual, setManual] = useState({
    timestamp: "",
    glucose_mg_dl: "",
    heart_rate_bpm: "",
    steps_5min: "",
    sleep_minutes: "",
    meal_event: false,
    minutes_since_meal: "",
  });
  const [manualResult, setManualResult] = useState(null);
  const [manualError, setManualError] = useState(null);
  const [manualSaving, setManualSaving] = useState(false);

  const [csvText, setCsvText] = useState("");
  const [csvName, setCsvName] = useState("");
  const [csvFile, setCsvFile] = useState(null);
  const [csvResult, setCsvResult] = useState(null);
  const [csvError, setCsvError] = useState(null);
  const [csvBusy, setCsvBusy] = useState(false);
  const fileRef = useRef(null);

  const [ehr, setEhr] = useState({
    record_date: "",
    record_type: "",
    hba1c_pct: "",
    systolic_bp: "",
    diastolic_bp: "",
    ldl_mg_dl: "",
    clinician_note: "",
  });
  const [ehrResult, setEhrResult] = useState(null);
  const [ehrError, setEhrError] = useState(null);
  const [ehrSaving, setEhrSaving] = useState(false);

  const noPatient = !selectedId;

  const submitManual = async (e) => {
    e.preventDefault();
    setManualError(null);
    setManualResult(null);
    if (!manual.timestamp) {
      setManualError("A timestamp is required (date and time of the reading).");
      return;
    }
    const numbers = {
      glucose_mg_dl: manual.glucose_mg_dl === "" ? null : Number(manual.glucose_mg_dl),
      heart_rate_bpm: manual.heart_rate_bpm === "" ? null : Number(manual.heart_rate_bpm),
      steps_5min: manual.steps_5min === "" ? null : Number(manual.steps_5min),
      sleep_minutes: manual.sleep_minutes === "" ? null : Number(manual.sleep_minutes),
      minutes_since_meal: manual.minutes_since_meal === "" ? null : Number(manual.minutes_since_meal),
    };
    const allEmpty = Object.values(numbers).every((v) => v === null);
    if (allEmpty) {
      setManualError("Enter at least one measurement (glucose, heart rate, steps, sleep or minutes since meal).");
      return;
    }
    setManualSaving(true);
    try {
      const res = await api.importReadings(selectedId, {
        readings: [
          {
            timestamp: toApiTimestamp(manual.timestamp),
            ...numbers,
            meal_event: manual.meal_event ? 1 : 0,
          },
        ],
      });
      setManualResult(res);
      if (res.accepted_count > 0) {
        await refreshAll();
        setManual((m) => ({
          ...m,
          timestamp: "",
          glucose_mg_dl: "",
          heart_rate_bpm: "",
          steps_5min: "",
          sleep_minutes: "",
          minutes_since_meal: "",
        }));
      }
    } catch (err) {
      setManualError(err.message);
    } finally {
      setManualSaving(false);
    }
  };

  const onFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setCsvFile(file);
    setCsvName(file.name);
    setCsvResult(null);
    setCsvError(null);
    const reader = new FileReader();
    reader.onload = () => setCsvText(String(reader.result ?? ""));
    reader.onerror = () => setCsvError("Could not read the selected file.");
    reader.readAsText(file);
  };

  const runCsv = async (dryRun) => {
    setCsvError(null);
    if (!csvFile && !csvText.trim()) {
      setCsvError("Choose a CSV file or paste CSV text first.");
      return;
    }
    setCsvBusy(true);
    try {
      // A selected file is uploaded as multipart/form-data and parsed on the
      // server; pasted text uses the JSON endpoint. Both share validation.
      const res = csvFile
        ? await api.uploadReadingsCsv(selectedId, csvFile, dryRun)
        : await api.importReadingsCsv(selectedId, { csv_text: csvText, dry_run: dryRun });
      setCsvResult(res);
      if (!dryRun && res.accepted_count > 0) await refreshAll();
    } catch (err) {
      setCsvError(err.message);
      setCsvResult(null);
    } finally {
      setCsvBusy(false);
    }
  };

  const downloadTemplate = () => {
    const blob = new Blob([CSV_TEMPLATE], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "glucotwin-readings-template.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const submitEhr = async (e) => {
    e.preventDefault();
    setEhrError(null);
    setEhrResult(null);
    if (!ehr.record_date || !ehr.record_type.trim()) {
      setEhrError("Record date and record type are required.");
      return;
    }
    setEhrSaving(true);
    try {
      const payload = {
        record_date: ehr.record_date,
        record_type: ehr.record_type.trim(),
        hba1c_pct: ehr.hba1c_pct === "" ? null : Number(ehr.hba1c_pct),
        systolic_bp: ehr.systolic_bp === "" ? null : Number(ehr.systolic_bp),
        diastolic_bp: ehr.diastolic_bp === "" ? null : Number(ehr.diastolic_bp),
        ldl_mg_dl: ehr.ldl_mg_dl === "" ? null : Number(ehr.ldl_mg_dl),
        clinician_note: ehr.clinician_note.trim() || null,
      };
      const record = await api.addEhr(selectedId, payload);
      setEhrResult(record);
      await refreshAll();
      setEhr({
        record_date: "",
        record_type: "",
        hba1c_pct: "",
        systolic_bp: "",
        diastolic_bp: "",
        ldl_mg_dl: "",
        clinician_note: "",
      });
    } catch (err) {
      setEhrError(err.message);
    } finally {
      setEhrSaving(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Medical Data"
        breadcrumb="Monitoring"
        subtitle="Enter measurements manually, import a sensor CSV, or append an EHR-style record."
        meta={
          selected && (
            <>
              <span className="text-[13px] font-medium text-slate-900">{selected.name}</span>
              <span className="badge bg-slate-100 text-slate-600">{selected.patient_id}</span>
              <DataTag label={selected.data_label} />
            </>
          )
        }
      />

      {noPatient ? (
        <div className="card">
          <EmptyState
            icon={ClipboardPlus}
            title="No patient selected"
            description="Choose a patient from the header to enter measurements, import CSV, or add an EHR record."
          />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <Panel title="Manual reading entry" subtitle="Missing cells are stored as unknown (NULL)">
            <form className="space-y-3" onSubmit={submitManual} noValidate>
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                  <label className="label" htmlFor="m-ts">
                    Timestamp *
                  </label>
                  <input
                    id="m-ts"
                    type="datetime-local"
                    className="input"
                    value={manual.timestamp}
                    onChange={(e) => setManual((m) => ({ ...m, timestamp: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="label" htmlFor="m-glucose">
                    Glucose (mg/dL)
                  </label>
                  <input
                    id="m-glucose"
                    type="number"
                    min="10"
                    max="1000"
                    className="input"
                    value={manual.glucose_mg_dl}
                    onChange={(e) => setManual((m) => ({ ...m, glucose_mg_dl: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="label" htmlFor="m-hr">
                    Heart rate (bpm)
                  </label>
                  <input
                    id="m-hr"
                    type="number"
                    min="20"
                    max="300"
                    className="input"
                    value={manual.heart_rate_bpm}
                    onChange={(e) => setManual((m) => ({ ...m, heart_rate_bpm: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="label" htmlFor="m-steps">
                    Steps (5 min)
                  </label>
                  <input
                    id="m-steps"
                    type="number"
                    min="0"
                    max="100000"
                    className="input"
                    value={manual.steps_5min}
                    onChange={(e) => setManual((m) => ({ ...m, steps_5min: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="label" htmlFor="m-sleep">
                    Sleep (min)
                  </label>
                  <input
                    id="m-sleep"
                    type="number"
                    min="0"
                    max="1440"
                    className="input"
                    value={manual.sleep_minutes}
                    onChange={(e) => setManual((m) => ({ ...m, sleep_minutes: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="label" htmlFor="m-meal">
                    Minutes since meal
                  </label>
                  <input
                    id="m-meal"
                    type="number"
                    min="0"
                    max="10080"
                    className="input"
                    value={manual.minutes_since_meal}
                    onChange={(e) => setManual((m) => ({ ...m, minutes_since_meal: e.target.value }))}
                  />
                </div>
                <label className="col-span-2 flex items-center gap-2 text-[13px] text-slate-600">
                  <input
                    type="checkbox"
                    checked={manual.meal_event}
                    onChange={(e) => setManual((m) => ({ ...m, meal_event: e.target.checked }))}
                  />
                  Meal event in this interval
                </label>
              </div>
              {manualError && <ErrorBanner message={manualError} />}
              <button type="submit" className="btn-primary" disabled={manualSaving}>
                <ClipboardPlus className="h-4 w-4" /> {manualSaving ? "Saving…" : "Add reading"}
              </button>
            </form>
            <ImportResultPanel result={manualResult} />
          </Panel>

          <Panel title="CSV sensor import" subtitle="Upload a file or paste CSV text — validation is explicit">
            <div className="flex flex-wrap items-center gap-2">
              <input
                ref={fileRef}
                type="file"
                accept=".csv,text/csv"
                className="text-[13px]"
                data-testid="csv-file"
                onChange={onFile}
              />
              <button type="button" className="btn-secondary" onClick={downloadTemplate} data-testid="csv-template">
                <Download className="h-4 w-4" /> Template
              </button>
            </div>
            {csvName && (
              <p className="mt-2 text-[11px] text-slate-500">
                Selected file: {csvName}
                {csvFile ? " (uploaded as multipart/form-data)" : ""}
              </p>
            )}
            <textarea
              className="input mt-3 font-mono text-[12px]"
              rows="7"
              placeholder="Paste CSV text here (or choose a file above)"
              value={csvText}
              onChange={(e) => {
                setCsvText(e.target.value);
                setCsvFile(null);
                setCsvName("");
              }}
              aria-label="CSV text"
            />
            {csvError && (
              <div className="mt-3">
                <ErrorBanner message={csvError} />
              </div>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                className="btn-secondary"
                onClick={() => runCsv(true)}
                disabled={csvBusy}
                data-testid="csv-preview"
              >
                <FileSpreadsheet className="h-4 w-4" />{" "}
                {csvBusy ? "Validating…" : csvFile ? "Preview upload" : "Preview (validate only)"}
              </button>
              <button
                type="button"
                className="btn-primary"
                onClick={() => runCsv(false)}
                disabled={csvBusy || !csvResult || csvResult.dry_run === false}
                data-testid="csv-confirm"
              >
                <UploadCloud className="h-4 w-4" /> Confirm import
              </button>
            </div>
            <ImportResultPanel result={csvResult} />
          </Panel>

          <div className="xl:col-span-2">
            <Panel title="EHR-style record" subtitle="Appended to the patient's record history (never overwritten)">
              <form className="grid grid-cols-1 gap-3 md:grid-cols-4" onSubmit={submitEhr} noValidate>
                <div>
                  <label className="label" htmlFor="e-date">
                    Record date *
                  </label>
                  <input
                    id="e-date"
                    type="date"
                    className="input"
                    value={ehr.record_date}
                    onChange={(e) => setEhr((s) => ({ ...s, record_date: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="label" htmlFor="e-type">
                    Record type *
                  </label>
                  <input
                    id="e-type"
                    className="input"
                    placeholder="Lab panel / Consultation"
                    value={ehr.record_type}
                    onChange={(e) => setEhr((s) => ({ ...s, record_type: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="label" htmlFor="e-hba1c">
                    HbA1c (%)
                  </label>
                  <input
                    id="e-hba1c"
                    type="number"
                    step="0.1"
                    className="input"
                    value={ehr.hba1c_pct}
                    onChange={(e) => setEhr((s) => ({ ...s, hba1c_pct: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="label" htmlFor="e-ldl">
                    LDL (mg/dL)
                  </label>
                  <input
                    id="e-ldl"
                    type="number"
                    step="0.1"
                    className="input"
                    value={ehr.ldl_mg_dl}
                    onChange={(e) => setEhr((s) => ({ ...s, ldl_mg_dl: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="label" htmlFor="e-sys">
                    Systolic BP
                  </label>
                  <input
                    id="e-sys"
                    type="number"
                    className="input"
                    value={ehr.systolic_bp}
                    onChange={(e) => setEhr((s) => ({ ...s, systolic_bp: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="label" htmlFor="e-dia">
                    Diastolic BP
                  </label>
                  <input
                    id="e-dia"
                    type="number"
                    className="input"
                    value={ehr.diastolic_bp}
                    onChange={(e) => setEhr((s) => ({ ...s, diastolic_bp: e.target.value }))}
                  />
                </div>
                <div className="md:col-span-2">
                  <label className="label" htmlFor="e-note">
                    Clinician note
                  </label>
                  <input
                    id="e-note"
                    className="input"
                    value={ehr.clinician_note}
                    onChange={(e) => setEhr((s) => ({ ...s, clinician_note: e.target.value }))}
                  />
                </div>
                {ehrError && (
                  <div className="md:col-span-4">
                    <ErrorBanner message={ehrError} />
                  </div>
                )}
                {ehrResult && (
                  <div className="md:col-span-4 rounded-md border border-teal-200 bg-teal-50 px-3 py-2 text-[13px] text-teal-800">
                    Saved record {ehrResult.record_id} ({ehrResult.record_type}, {ehrResult.record_date}).
                  </div>
                )}
                <div className="md:col-span-4">
                  <button type="submit" className="btn-primary" disabled={ehrSaving}>
                    <LinkIcon className="h-4 w-4" /> {ehrSaving ? "Saving…" : "Add EHR record"}
                  </button>
                </div>
              </form>
            </Panel>
          </div>
        </div>
      )}

      {profile && (
        <p className="mt-3 text-[11px] text-slate-500">
          Data added here is demonstration data — stored alongside the synthetic dataset and clearly
          labelled in the patient profile and reports.
        </p>
      )}
    </>
  );
}
