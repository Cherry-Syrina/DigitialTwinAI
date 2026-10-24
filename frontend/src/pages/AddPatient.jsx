import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Save, TriangleAlert, UserPlus } from "lucide-react";
import { api } from "../api";
import { useApp } from "../store";
import { ErrorBanner, PageHeader, Panel, Spinner } from "../components/ui";

const SEX_OPTIONS = ["F", "M", "Other"];
const TYPE_OPTIONS = ["Type 1", "Type 2", "Gestational", "Prediabetes", "Other"];
const SMOKING_OPTIONS = ["Never", "Former", "Current", "Not recorded"];
const ACTIVITY_OPTIONS = ["Sedentary", "Light", "Moderate", "Active", "Very active", "Not recorded"];

const EMPTY_FORM = {
  patient_id: "",
  name: "",
  age: "",
  sex: "F",
  diabetes_type: "Type 2",
  years_since_diagnosis: "",
  height_cm: "",
  weight_kg: "",
  bmi: "",
  hba1c_pct: "",
  medical_history: "",
  current_medications: "",
  family_history: "",
  smoking_status: "Never",
  activity_level: "Moderate",
};

const textToList = (text) =>
  text
    .split(/[\n,]/)
    .map((s) => s.trim())
    .filter(Boolean);

function validate(form, isEdit) {
  const errors = {};
  if (!isEdit && !/^[A-Za-z0-9][A-Za-z0-9_-]{1,31}$/.test(form.patient_id.trim())) {
    errors.patient_id = "2-32 characters: letters, digits, - or _ (must start with a letter/digit)";
  }
  if (!form.name.trim()) errors.name = "Name is required";
  const checkNumber = (key, lo, hi, label, required = true) => {
    const raw = form[key];
    if (raw === "" || raw === null) {
      if (required) errors[key] = `${label} is required`;
      return;
    }
    const n = Number(raw);
    if (Number.isNaN(n)) errors[key] = `${label} must be a number`;
    else if (n < lo || n > hi) errors[key] = `${label} must be between ${lo} and ${hi}`;
  };
  checkNumber("age", 0, 120, "Age");
  checkNumber("years_since_diagnosis", 0, 100, "Years since diagnosis");
  checkNumber("height_cm", 40, 260, "Height");
  checkNumber("weight_kg", 20, 600, "Weight");
  checkNumber("bmi", 5, 120, "BMI");
  checkNumber("hba1c_pct", 2, 25, "HbA1c");
  if (!form.sex) errors.sex = "Sex is required";
  if (!form.diabetes_type) errors.diabetes_type = "Diabetes type is required";
  return errors;
}

function toForm(profile) {
  return {
    patient_id: profile.patient_id,
    name: profile.name ?? "",
    age: String(profile.age ?? ""),
    sex: profile.sex ?? "F",
    diabetes_type: profile.diabetes_type ?? "Type 2",
    years_since_diagnosis: String(profile.years_since_diagnosis ?? ""),
    height_cm: String(profile.height_cm ?? ""),
    weight_kg: String(profile.weight_kg ?? ""),
    bmi: String(profile.bmi ?? ""),
    hba1c_pct: String(profile.glucose_summaries?.[0]?.hba1c_pct ?? ""),
    medical_history: (profile.medical_history || []).join("\n"),
    current_medications: (profile.current_medications || []).join("\n"),
    family_history: profile.family_history === "n/a" ? "" : profile.family_history ?? "",
    smoking_status: profile.smoking_status === "n/a" ? "Not recorded" : profile.smoking_status ?? "Never",
    activity_level: profile.activity_level === "n/a" ? "Not recorded" : profile.activity_level ?? "Moderate",
  };
}

export default function AddPatient() {
  const { patient_id: editId } = useParams();
  const isEdit = Boolean(editId);
  const navigate = useNavigate();
  const { refreshAll } = useApp();

  const [form, setForm] = useState(isEdit ? { ...EMPTY_FORM, patient_id: editId } : EMPTY_FORM);
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState(null);
  const [saved, setSaved] = useState(null);
  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isEdit) return;
    let alive = true;
    setLoading(true);
    api
      .patient(editId)
      .then((profile) => {
        if (alive) setForm(toForm(profile));
      })
      .catch((err) => {
        if (alive) setServerError(err.message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [editId, isEdit]);

  useEffect(() => {
    const h = Number(form.height_cm);
    const w = Number(form.weight_kg);
    if (form.bmi === "" && h > 0 && w > 0) {
      const bmi = w / (h / 100) ** 2;
      setForm((f) => (f.bmi === "" ? { ...f, bmi: bmi.toFixed(1) } : f));
    }
  }, [form.height_cm, form.weight_kg, form.bmi]);

  const set = (key) => (e) => {
    const value = e.target.value;
    setForm((f) => ({ ...f, [key]: value }));
    setErrors((prev) => (prev[key] ? { ...prev, [key]: undefined } : prev));
  };

  const errorCount = useMemo(() => Object.values(errors).filter(Boolean).length, [errors]);

  const submit = async (e) => {
    e.preventDefault();
    const found = validate(form, isEdit);
    setErrors(found);
    if (Object.keys(found).length > 0) {
      setServerError("Please fix the highlighted fields before saving.");
      return;
    }
    const payload = {
      name: form.name.trim(),
      age: Number(form.age),
      sex: form.sex,
      diabetes_type: form.diabetes_type,
      years_since_diagnosis: Number(form.years_since_diagnosis),
      height_cm: Number(form.height_cm),
      weight_kg: Number(form.weight_kg),
      bmi: Number(form.bmi),
      hba1c_pct: Number(form.hba1c_pct),
      medical_history: textToList(form.medical_history),
      current_medications: textToList(form.current_medications),
      family_history: form.family_history.trim(),
      smoking_status: form.smoking_status,
      activity_level: form.activity_level,
    };
    if (!isEdit) payload.patient_id = form.patient_id.trim();

    setSaving(true);
    setServerError(null);
    setSaved(null);
    try {
      const result = isEdit
        ? await api.updatePatient(editId, payload)
        : await api.createPatient(payload);
      await refreshAll();
      setSaved(
        isEdit
          ? `Saved changes for ${result.name} (${result.patient_id}).`
          : `Registered ${result.name} (${result.patient_id}). The patient is now available everywhere.`
      );
      if (!isEdit) setForm(EMPTY_FORM);
      else navigate("/patients");
    } catch (err) {
      setServerError(
        err.status === 409
          ? `${err.message} Duplicate IDs are not allowed.`
          : err.message || "Could not save the patient."
      );
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <Spinner label="Loading patient…" />;

  const err = (key) => (errors[key] ? <p className="mt-1 text-[11px] text-red-600">{errors[key]}</p> : null);
  const inputClass = (key) => `input ${errors[key] ? "border-red-400" : ""}`;

  return (
    <>
      <PageHeader
        title={isEdit ? "Edit Patient" : "Add Patient"}
        breadcrumb="Cohort"
        subtitle={
          isEdit
            ? "Update demographic and clinical details. Changes are persisted to the local database."
            : "Register a new demonstration patient for data entry, the digital twin and reports."
        }
        actions={
          <Link className="btn-secondary" to="/patients">
            <ArrowLeft className="h-4 w-4" /> Back to patients
          </Link>
        }
      />

      {serverError && <ErrorBanner message={serverError} />}
      {saved && (
        <div className="mb-4 rounded-md border border-teal-200 bg-teal-50 px-3 py-2 text-[13px] text-teal-800">
          {saved}
        </div>
      )}

      <form className="space-y-4" onSubmit={submit} noValidate>
        <Panel title="Identity">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <div>
              <label className="label" htmlFor="patient_id">
                Patient ID *
              </label>
              <input
                id="patient_id"
                className={inputClass("patient_id")}
                value={form.patient_id}
                onChange={set("patient_id")}
                disabled={isEdit}
                placeholder="DOC-001"
              />
              <p className="mt-1 text-[11px] text-slate-500">The patient ID cannot be changed.</p>
              {err("patient_id")}
            </div>
            <div>
              <label className="label" htmlFor="name">
                Full name *
              </label>
              <input id="name" className={inputClass("name")} value={form.name} onChange={set("name")} />
              {err("name")}
            </div>
            <div>
              <label className="label" htmlFor="sex">
                Sex *
              </label>
              <select id="sex" className={inputClass("sex")} value={form.sex} onChange={set("sex")}>
                {SEX_OPTIONS.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
              {err("sex")}
            </div>
          </div>
        </Panel>

        <Panel title="Diabetes profile">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <div>
              <label className="label" htmlFor="diabetes_type">
                Diabetes type *
              </label>
              <select
                id="diabetes_type"
                className={inputClass("diabetes_type")}
                value={form.diabetes_type}
                onChange={set("diabetes_type")}
              >
                {TYPE_OPTIONS.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
              {err("diabetes_type")}
            </div>
            <div>
              <label className="label" htmlFor="years_since_diagnosis">
                Years since diagnosis *
              </label>
              <input
                id="years_since_diagnosis"
                type="number"
                min="0"
                max="100"
                className={inputClass("years_since_diagnosis")}
                value={form.years_since_diagnosis}
                onChange={set("years_since_diagnosis")}
              />
              {err("years_since_diagnosis")}
            </div>
            <div>
              <label className="label" htmlFor="hba1c_pct">
                Latest HbA1c (%) *
              </label>
              <input
                id="hba1c_pct"
                type="number"
                step="0.1"
                min="2"
                max="25"
                className={inputClass("hba1c_pct")}
                value={form.hba1c_pct}
                onChange={set("hba1c_pct")}
              />
              {err("hba1c_pct")}
            </div>
          </div>
        </Panel>

        <Panel title="Measurements">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
            <div>
              <label className="label" htmlFor="age">
                Age *
              </label>
              <input
                id="age"
                type="number"
                min="0"
                max="120"
                className={inputClass("age")}
                value={form.age}
                onChange={set("age")}
              />
              {err("age")}
            </div>
            <div>
              <label className="label" htmlFor="height_cm">
                Height (cm) *
              </label>
              <input
                id="height_cm"
                type="number"
                step="0.1"
                className={inputClass("height_cm")}
                value={form.height_cm}
                onChange={set("height_cm")}
              />
              {err("height_cm")}
            </div>
            <div>
              <label className="label" htmlFor="weight_kg">
                Weight (kg) *
              </label>
              <input
                id="weight_kg"
                type="number"
                step="0.1"
                className={inputClass("weight_kg")}
                value={form.weight_kg}
                onChange={set("weight_kg")}
              />
              {err("weight_kg")}
            </div>
            <div>
              <label className="label" htmlFor="bmi">
                BMI *
              </label>
              <input
                id="bmi"
                type="number"
                step="0.1"
                className={inputClass("bmi")}
                value={form.bmi}
                onChange={set("bmi")}
              />
              <p className="mt-1 text-[11px] text-slate-500">Auto-calculated from height/weight.</p>
              {err("bmi")}
            </div>
          </div>
        </Panel>

        <Panel title="History & lifestyle">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div>
              <label className="label" htmlFor="medical_history">
                Relevant medical history
              </label>
              <textarea
                id="medical_history"
                rows="3"
                className="input"
                value={form.medical_history}
                onChange={set("medical_history")}
                placeholder="One condition per line (or comma separated)"
              />
            </div>
            <div>
              <label className="label" htmlFor="current_medications">
                Current medications
              </label>
              <textarea
                id="current_medications"
                rows="3"
                className="input"
                value={form.current_medications}
                onChange={set("current_medications")}
                placeholder="One medication per line (or comma separated)"
              />
            </div>
            <div>
              <label className="label" htmlFor="family_history">
                Family history
              </label>
              <input id="family_history" className="input" value={form.family_history} onChange={set("family_history")} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label" htmlFor="smoking_status">
                  Smoking status
                </label>
                <select id="smoking_status" className="input" value={form.smoking_status} onChange={set("smoking_status")}>
                  {SMOKING_OPTIONS.map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="label" htmlFor="activity_level">
                  Activity level
                </label>
                <select id="activity_level" className="input" value={form.activity_level} onChange={set("activity_level")}>
                  {ACTIVITY_OPTIONS.map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        </Panel>

        <div className="flex flex-wrap items-center gap-3">
          <button type="submit" className="btn-primary" disabled={saving}>
            {isEdit ? <Save className="h-4 w-4" /> : <UserPlus className="h-4 w-4" />}
            {saving ? "Saving…" : isEdit ? "Save changes" : "Register patient"}
          </button>
          <Link className="btn-secondary" to="/patients">
            Cancel
          </Link>
          {errorCount > 0 && (
            <span className="inline-flex items-center gap-1 text-[12px] text-red-600">
              <TriangleAlert className="h-3.5 w-3.5" /> {errorCount} field error(s)
            </span>
          )}
          <span className="text-[11px] text-slate-500">* required field</span>
        </div>
      </form>
    </>
  );
}
