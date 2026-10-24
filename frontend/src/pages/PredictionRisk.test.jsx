import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import PredictionRisk from "./PredictionRisk";
import { useApp } from "../store";
import { api } from "../api";
import twinFixture from "../test/fixtures/twin-GT-001.json";
import predictFixture from "../test/fixtures/predict-GT-001.json";
import metricsFixture from "../test/fixtures/metrics.json";
import thresholdsFixture from "../test/fixtures/thresholds.json";

vi.mock("../store", () => ({ useApp: vi.fn() }));
vi.mock("../api", () => ({ api: { predict: vi.fn() } }));

const pending = () => new Promise(() => {});

function ctx(overrides = {}) {
  return {
    selectedId: "GT-001",
    twin: null,
    metrics: null,
    thresholds: thresholdsFixture,
    busy: false,
    ...overrides,
  };
}

beforeEach(() => {
  api.predict.mockReset();
  useApp.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("PredictionRisk", () => {
  it("does not crash when the twin is the only source of a prediction (risk is a sibling field, not nested)", async () => {
    // Regression for: "Uncaught TypeError: Cannot read properties of undefined (reading 'level')".
    // GET /digital-twin returns prediction WITHOUT a nested `risk` key — risk is a top-level sibling.
    expect(twinFixture.prediction).toBeTruthy();
    expect("risk" in twinFixture.prediction).toBe(false);
    expect(twinFixture.risk?.level).toBeTruthy();

    const errSpy = vi.spyOn(console, "error");
    useApp.mockReturnValue(ctx({ twin: twinFixture }));
    api.predict.mockReturnValue(pending()); // /predict has not resolved yet

    render(<PredictionRisk />);

    expect(await screen.findByRole("heading", { level: 1, name: "Prediction & Risk Analysis" })).toBeTruthy();
    // Risk badge rendered from the twin's SIBLING risk field:
    expect(await screen.findByText(twinFixture.risk.level.toUpperCase())).toBeTruthy();
    expect(screen.getByText(/Forecast at \+60 min/)).toBeTruthy();

    expect(errSpy.mock.calls.map(String).join(" ")).not.toMatch(/Cannot read properties/);
    errSpy.mockRestore();
  });

  it("shows N/A and hides the range when no risk data is available at all", async () => {
    const errSpy = vi.spyOn(console, "error");
    useApp.mockReturnValue(ctx({ twin: { ...twinFixture, risk: null } }));
    api.predict.mockReturnValue(pending());

    render(<PredictionRisk />);

    expect(await screen.findByRole("heading", { level: 1, name: "Prediction & Risk Analysis" })).toBeTruthy();
    expect(await screen.findByText("N/A")).toBeTruthy();
    expect(screen.queryByText(/Predicted range over horizon/)).toBeNull();

    expect(errSpy.mock.calls.map(String).join(" ")).not.toMatch(/Cannot read properties/);
    errSpy.mockRestore();
  });

  it("uses the risk nested inside a successful /predict response", async () => {
    useApp.mockReturnValue(ctx({ twin: null }));
    api.predict.mockResolvedValue(predictFixture);

    render(<PredictionRisk />);

    expect(await screen.findByText(predictFixture.risk.level.toUpperCase())).toBeTruthy();
    const range = await screen.findByText(/Predicted range over horizon/);
    expect(range.textContent).toContain(String(predictFixture.risk.predicted_min_mg_dl));
    expect(range.textContent).toContain(String(predictFixture.risk.predicted_max_mg_dl));
  });

  it("shows the API error and an empty state when /predict fails", async () => {
    useApp.mockReturnValue(ctx({ twin: null }));
    api.predict.mockRejectedValue(new Error("HTTP 503 Model artifacts unavailable"));

    render(<PredictionRisk />);

    expect(await screen.findByText(/HTTP 503 Model artifacts unavailable/)).toBeTruthy();
    expect(await screen.findByText(/No prediction data available/)).toBeTruthy();
  });

  it("shows the loading spinner while the prediction request is in flight", async () => {
    useApp.mockReturnValue(ctx({ twin: null }));
    api.predict.mockReturnValue(pending());

    render(<PredictionRisk />);

    expect(await screen.findByText("Loading…")).toBeTruthy();
  });

  it("renders 'n/a' for a missing improvement metric instead of undefined", async () => {
    const partialMetrics = {
      horizons: {
        "60": {
          selected_model: "gradient_boosting",
          rows_test: 3188,
          metrics: { mae: 5.306, rmse: 6.94 },
          baselines: { persistence: { mae: 10.654 } },
          // mae_improvement_over_persistence intentionally missing
        },
      },
    };
    useApp.mockReturnValue(ctx({ metrics: partialMetrics }));
    api.predict.mockResolvedValue(predictFixture);

    render(<PredictionRisk />);

    const label = await screen.findByText("Improvement vs baseline");
    expect(within(label.parentElement).getByText("n/a")).toBeTruthy();
  });

  it("still renders the metrics card from the real metrics fixture", async () => {
    useApp.mockReturnValue(ctx({ metrics: metricsFixture }));
    api.predict.mockResolvedValue(predictFixture);

    render(<PredictionRisk />);

    expect(await screen.findByText(/Model metrics @ \+60m/)).toBeTruthy();
    expect(screen.getByText("gradient_boosting")).toBeTruthy();
  });
});
