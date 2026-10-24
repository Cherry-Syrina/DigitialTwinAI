/**
 * Regenerates test fixtures from the RUNNING GlucoTwin AI backend.
 *
 * Usage (backend must be up):
 *   node src/test/fetch-fixtures.mjs
 *   GLUCOTWIN_API_URL=http://127.0.0.1:8000 node src/test/fetch-fixtures.mjs
 *
 * The fixtures are real API responses (synthetic demo data) captured so the
 * frontend tests assert against the actual backend response schema.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const BASE = process.env.GLUCOTWIN_API_URL || "http://127.0.0.1:8000";
const OUT = join(dirname(fileURLToPath(import.meta.url)), "fixtures");

async function get(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
  return res.json();
}

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} -> ${res.status}`);
  return res.json();
}

const id = "GT-001";
const files = {
  "health.json": await get("/api/health"),
  "patients.json": await get("/api/patients"),
  [`profile-${id}.json`]: await get(`/api/patients/${id}`),
  [`twin-${id}.json`]: await get(`/api/patients/${id}/digital-twin`),
  [`history-${id}.json`]: await get(`/api/patients/${id}/history?hours=8`),
  [`predict-${id}.json`]: await post(`/api/patients/${id}/predict`, {
    horizon_minutes: 60,
    explain: true,
  }),
  "metrics.json": await get("/api/model/metrics"),
  "thresholds.json": await get("/api/model/thresholds"),
};

mkdirSync(OUT, { recursive: true });
for (const [name, data] of Object.entries(files)) {
  writeFileSync(join(OUT, name), `${JSON.stringify(data, null, 2)}\n`);
  console.log("wrote", name);
}