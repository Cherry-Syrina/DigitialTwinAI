import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { api } from "./api";
import patientsFixture from "./test/fixtures/patients.json";
import profileFixture from "./test/fixtures/profile-GT-001.json";
import twinFixture from "./test/fixtures/twin-GT-001.json";
import historyFixture from "./test/fixtures/history-GT-001.json";
import predictFixture from "./test/fixtures/predict-GT-001.json";
import metricsFixture from "./test/fixtures/metrics.json";
import thresholdsFixture from "./test/fixtures/thresholds.json";
import healthFixture from "./test/fixtures/health.json";

vi.mock("./api", () => ({
  api: {
    health: vi.fn(),
    patients: vi.fn(),
    patient: vi.fn(),
    history: vi.fn(),
    twin: vi.fn(),
    predict: vi.fn(),
    whatIf: vi.fn(),
    advanceDemo: vi.fn(),
    metrics: vi.fn(),
    thresholds: vi.fn(),
    report: vi.fn(),
    reportPdf: vi.fn(),
    createPatient: vi.fn(),
    updatePatient: vi.fn(),
    addEhr: vi.fn(),
    importReadings: vi.fn(),
    importReadingsCsv: vi.fn(),
    uploadReadingsCsv: vi.fn(),
  },
}));

const ROUTES = [
  ["#/overview", "Overview"],
  ["#/patients", "Patients"],
  ["#/patients/new", "Add Patient"],
  ["#/data-entry", "Medical Data"],
  ["#/profile", profileFixture.name],
  ["#/twin", "Digital Twin Monitor"],
  ["#/prediction", "Prediction & Risk Analysis"],
  ["#/whatif", "What-if Simulation"],
  ["#/reports", "Reports"],
  ["#/doctor", "Doctor View"],
];

let warnSpy;

beforeEach(() => {
  api.health.mockResolvedValue(healthFixture);
  api.patients.mockResolvedValue(patientsFixture);
  api.patient.mockResolvedValue(profileFixture);
  api.history.mockResolvedValue(historyFixture);
  api.twin.mockResolvedValue(twinFixture);
  api.predict.mockResolvedValue(predictFixture);
  api.whatIf.mockResolvedValue(predictFixture);
  api.advanceDemo.mockResolvedValue({ advanced: [] });
  api.metrics.mockResolvedValue(metricsFixture);
  api.thresholds.mockResolvedValue(thresholdsFixture);
  api.report.mockResolvedValue({ content_markdown: "# report", generated_at: null });
  warnSpy = vi.spyOn(console, "warn");
});

afterEach(() => {
  cleanup();
  warnSpy.mockRestore();
});

function expectNoRouterFutureWarnings() {
  const messages = warnSpy.mock.calls.map(String).join("\n");
  expect(messages).not.toMatch(/Future Flag Warning|Relative route resolution/);
}

describe("App routes (react-router v7 future flags)", () => {
  it.each(ROUTES)("renders %s with its heading and no future-flag warnings", async (hash, heading) => {
    window.location.hash = hash;
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeTruthy();
    expectNoRouterFutureWarnings();
  });

  it("redirects the root path to /overview", async () => {
    window.location.hash = "#/";
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: "Overview" })).toBeTruthy();
    expectNoRouterFutureWarnings();
  });

  it("redirects unknown paths to /overview (catch-all)", async () => {
    window.location.hash = "#/definitely-not-a-page";
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: "Overview" })).toBeTruthy();
    expectNoRouterFutureWarnings();
  });

  it("renders navigation links for every route", async () => {
    window.location.hash = "#/overview";
    render(<App />);
    const sidebar = await screen.findByRole("navigation");
    for (const label of [
      "Overview",
      "Patients",
      "Add Patient",
      "Medical Data",
      "Digital Twin",
      "Predictions & Risk",
      "What-if Simulation",
      "Reports",
      "Doctor View",
    ]) {
      expect(sidebar.textContent).toContain(label);
    }
    expectNoRouterFutureWarnings();
  });
});
