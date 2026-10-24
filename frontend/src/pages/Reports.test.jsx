import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Reports from "./Reports";
import { useApp } from "../store";
import { api } from "../api";

vi.mock("../store", () => ({ useApp: vi.fn() }));
vi.mock("../api", () => ({ api: { report: vi.fn(), reportPdf: vi.fn() } }));

const MARKDOWN = [
  "# Synthetic Patient Report - Synthetic Patient 01 (GT-001)",
  "",
  "> **DATA LABEL:** synthetic demonstration data only.",
  "",
  "## 1. Data source and provenance",
  "",
  "- Profile label: **synthetic**",
  "",
  "| Threshold | Value |",
  "|-----------|-------|",
  "| Hypo low | 70 mg/dL |",
  "",
  "### Configured risk thresholds",
  "",
].join("\n");

beforeEach(() => {
  useApp.mockReturnValue({
    selectedId: "GT-001",
    patients: [{ patient_id: "GT-001", name: "Synthetic Patient 01", data_label: "synthetic" }],
    profile: { name: "Synthetic Patient 01" },
  });
  api.report.mockReset();
  api.reportPdf.mockReset();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Reports", () => {
  it("shows an empty state until a report is generated", () => {
    render(<Reports />);
    expect(screen.getByText(/No report generated yet/)).toBeTruthy();
  });

  it("generates a report and renders markdown headings, lists and tables", async () => {
    api.report.mockResolvedValue({
      patient_id: "GT-001",
      generated_at: "2026-10-18T10:00:00+00:00",
      data_label: "synthetic",
      content_markdown: MARKDOWN,
    });
    render(<Reports />);

    fireEvent.click(screen.getByRole("button", { name: /Generate report/ }));

    expect(await screen.findByText(/Synthetic Patient Report - Synthetic Patient 01/)).toBeTruthy();
    expect(screen.getByText(/1\. Data source and provenance/)).toBeTruthy();
    // table rendered as a real <table> with its cells
    expect(screen.getByText("Hypo low")).toBeTruthy();
    expect(screen.getByText("70 mg/dL")).toBeTruthy();
    // **bold** rendered as a <strong>
    expect(screen.getByText("synthetic").tagName).toBe("STRONG");
    expect(screen.getByText(/Configured risk thresholds/)).toBeTruthy();
  });

  it("surfaces an API error instead of a stale report", async () => {
    api.report.mockRejectedValue(new Error("HTTP 503 Model artifacts unavailable"));
    render(<Reports />);
    fireEvent.click(screen.getByRole("button", { name: /Generate report/ }));
    expect(await screen.findByText(/HTTP 503 Model artifacts unavailable/)).toBeTruthy();
  });

  it("downloads the markdown via a Blob URL", async () => {
    api.report.mockResolvedValue({
      patient_id: "GT-001",
      generated_at: "2026-10-18T10:00:00+00:00",
      data_label: "synthetic",
      content_markdown: MARKDOWN,
    });
    const createObjectURL = vi.fn(() => "blob:report");
    const revokeObjectURL = vi.fn();
    class FakeURL extends URL {}
    FakeURL.createObjectURL = createObjectURL;
    FakeURL.revokeObjectURL = revokeObjectURL;
    vi.stubGlobal("URL", FakeURL);
    render(<Reports />);

    fireEvent.click(screen.getByRole("button", { name: /Generate report/ }));
    await screen.findByText(/Synthetic Patient Report/);

    fireEvent.click(screen.getByRole("button", { name: /Download \.md/ }));
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(createObjectURL.mock.calls[0][0]).toBeInstanceOf(Blob);
  });

  it("downloads the server-generated PDF via a Blob URL", async () => {
    api.reportPdf.mockResolvedValue(new Blob(["%PDF-1.4"], { type: "application/pdf" }));
    const createObjectURL = vi.fn(() => "blob:pdf");
    const revokeObjectURL = vi.fn();
    class FakeURL extends URL {}
    FakeURL.createObjectURL = createObjectURL;
    FakeURL.revokeObjectURL = revokeObjectURL;
    vi.stubGlobal("URL", FakeURL);
    render(<Reports />);

    fireEvent.click(screen.getByTestId("download-pdf"));
    await waitFor(() => expect(api.reportPdf).toHaveBeenCalledWith("GT-001"));
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(createObjectURL.mock.calls[0][0]).toBeInstanceOf(Blob);
  });

  it("surfaces a PDF download error", async () => {
    api.reportPdf.mockRejectedValue(new Error("HTTP 500 pdf failed"));
    render(<Reports />);
    fireEvent.click(screen.getByTestId("download-pdf"));
    expect(await screen.findByText(/HTTP 500 pdf failed/)).toBeTruthy();
  });

  it("offers a print/PDF action that calls window.print", async () => {
    api.report.mockResolvedValue({
      patient_id: "GT-001",
      generated_at: "2026-10-18T10:00:00+00:00",
      data_label: "synthetic",
      content_markdown: MARKDOWN,
    });
    const print = vi.fn();
    vi.stubGlobal("print", print);
    render(<Reports />);
    fireEvent.click(screen.getByRole("button", { name: /Generate report/ }));
    await screen.findByText(/Synthetic Patient Report/);
    fireEvent.click(screen.getByRole("button", { name: /Print \/ PDF/ }));
    expect(print).toHaveBeenCalledTimes(1);
  });
});
