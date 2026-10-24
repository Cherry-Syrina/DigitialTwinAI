const BASE = import.meta.env.VITE_API_URL || "";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, options = {}) {
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  const headers = { ...(options.headers || {}) };
  if (!isFormData && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  let resp;
  try {
    resp = await fetch(`${BASE}${path}`, { ...options, headers });
  } catch (err) {
    throw new ApiError(
      "Cannot reach the GlucoTwin AI backend. Is it running on http://127.0.0.1:8000 ?",
      0
    );
  }
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const body = await resp.json();
      if (body?.detail) detail = formatDetail(body.detail);
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, resp.status);
  }
  return resp.json();
}

/** Like ``request`` but for binary downloads (returns a Blob). */
async function requestBlob(path, options = {}) {
  let resp;
  try {
    resp = await fetch(`${BASE}${path}`, options);
  } catch (err) {
    throw new ApiError(
      "Cannot reach the GlucoTwin AI backend. Is it running on http://127.0.0.1:8000 ?",
      0
    );
  }
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const body = await resp.json();
      if (body?.detail) detail = formatDetail(body.detail);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, resp.status);
  }
  return resp.blob();
}

/** Turn FastAPI error payloads (string, or list of validation errors) into readable text. */
export function formatDetail(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((e) => {
        const loc = Array.isArray(e?.loc) ? e.loc.filter((p) => p !== "body" && typeof p !== "number").join(".") : "";
        const msg = e?.msg || "invalid value";
        return loc ? `${loc}: ${msg}` : msg;
      })
      .join("; ");
  }
  try {
    return JSON.stringify(detail);
  } catch {
    return String(detail);
  }
}

export const api = {
  health: () => request("/api/health"),
  patients: () => request("/api/patients"),
  patient: (id) => request(`/api/patients/${id}`),
  history: (id, params = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    });
    const str = qs.toString();
    return request(`/api/patients/${id}/history${str ? `?${str}` : ""}`);
  },
  twin: (id) => request(`/api/patients/${id}/digital-twin`),
  predict: (id, payload) => request(`/api/patients/${id}/predict`, { method: "POST", body: JSON.stringify(payload) }),
  whatIf: (id, payload) => request(`/api/patients/${id}/what-if`, { method: "POST", body: JSON.stringify(payload) }),
  advanceDemo: (payload = {}) => request("/api/demo/advance", { method: "POST", body: JSON.stringify(payload) }),
  metrics: () => request("/api/model/metrics"),
  thresholds: () => request("/api/model/thresholds"),
  report: (id) => request(`/api/patients/${id}/report`),

  // doctor write workflows (persisted in the backend SQLite overlay)
  createPatient: (payload) =>
    request("/api/patients", { method: "POST", body: JSON.stringify(payload) }),
  updatePatient: (id, payload) =>
    request(`/api/patients/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  addEhr: (id, payload) =>
    request(`/api/patients/${id}/ehr`, { method: "POST", body: JSON.stringify(payload) }),
  importReadings: (id, payload) =>
    request(`/api/patients/${id}/readings`, { method: "POST", body: JSON.stringify(payload) }),
  importReadingsCsv: (id, payload) =>
    request(`/api/patients/${id}/readings/csv`, { method: "POST", body: JSON.stringify(payload) }),
  uploadReadingsCsv: (id, file, dryRun = false) => {
    const form = new FormData();
    form.append("file", file);
    form.append("dry_run", dryRun ? "true" : "false");
    return request(`/api/patients/${id}/readings/csv/upload`, { method: "POST", body: form });
  },
  reportPdf: (id) => requestBlob(`/api/patients/${id}/report.pdf`),
};