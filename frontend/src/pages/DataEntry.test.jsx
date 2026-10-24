import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import DataEntry from "./DataEntry";
import { useApp } from "../store";
import { api } from "../api";

vi.mock("../store", () => ({ useApp: vi.fn() }));
vi.mock("../api", () => ({
  api: {
    importReadings: vi.fn(),
    importReadingsCsv: vi.fn(),
    uploadReadingsCsv: vi.fn(),
    addEhr: vi.fn(),
  },
}));

const refreshAll = vi.fn();

beforeEach(() => {
  useApp.mockReturnValue({
    selectedId: "GT-001",
    patients: [{ patient_id: "GT-001", name: "Synthetic Patient 01", data_label: "synthetic" }],
    profile: { patient_id: "GT-001", name: "Synthetic Patient 01" },
    refreshAll,
  });
  api.importReadings.mockReset();
  api.importReadingsCsv.mockReset();
  api.uploadReadingsCsv.mockReset();
  api.addEhr.mockReset();
  refreshAll.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("DataEntry (manual + CSV import)", () => {
  it("requires a timestamp before saving a manual reading", async () => {
    render(<DataEntry />);
    fireEvent.click(screen.getByRole("button", { name: /^Add reading$/ }));
    expect(await screen.findByText(/A timestamp is required/)).toBeTruthy();
    expect(api.importReadings).not.toHaveBeenCalled();
  });

  it("requires at least one measurement value", async () => {
    render(<DataEntry />);
    fireEvent.change(screen.getByLabelText(/Timestamp/), { target: { value: "2026-10-15T09:00" } });
    fireEvent.click(screen.getByRole("button", { name: /^Add reading$/ }));
    expect(await screen.findByText(/Enter at least one measurement/)).toBeTruthy();
    expect(api.importReadings).not.toHaveBeenCalled();
  });

  it("submits a manual reading with the canonical timestamp and refreshes data", async () => {
    api.importReadings.mockResolvedValue({
      message: "1 reading(s) stored, 0 rejected (0 duplicate).",
      accepted_count: 1,
      rejected_count: 0,
      duplicate_count: 0,
      persisted: true,
      dry_run: false,
      rows: [{ row_index: 0, timestamp: "2026-10-15 09:00:00", status: "accepted", missing: [] }],
    });
    render(<DataEntry />);
    fireEvent.change(screen.getByLabelText(/Timestamp/), { target: { value: "2026-10-15T09:00" } });
    fireEvent.change(screen.getByLabelText(/Glucose/), { target: { value: "130" } });
    fireEvent.click(screen.getByRole("button", { name: /^Add reading$/ }));

    await waitFor(() => expect(api.importReadings).toHaveBeenCalledTimes(1));
    const [id, payload] = api.importReadings.mock.calls[0];
    expect(id).toBe("GT-001");
    expect(payload.readings).toHaveLength(1);
    expect(payload.readings[0]).toMatchObject({
      timestamp: "2026-10-15 09:00:00",
      glucose_mg_dl: 130,
      meal_event: 0,
    });
    expect(refreshAll).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(/1 reading\(s\) stored/)).toBeTruthy();
  });

  it("previews a CSV import, then confirms it, reporting rejected rows", async () => {
    api.importReadingsCsv.mockImplementation((_id, { dry_run }) =>
      Promise.resolve({
        message: dry_run ? "Dry run: 1 row(s) would be stored, 1 would be rejected (0 duplicate)." : "1 reading(s) stored, 1 rejected (0 duplicate).",
        accepted_count: 1,
        rejected_count: 1,
        duplicate_count: 0,
        persisted: !dry_run,
        dry_run,
        rows: [
          { row_index: 0, timestamp: "2026-10-15 08:00:00", status: "accepted", glucose_mg_dl: 132, missing: [] },
          { row_index: 1, timestamp: "bad", status: "rejected", reason: "timestamp could not be parsed" },
        ],
      })
    );
    render(<DataEntry />);

    const confirm = screen.getByRole("button", { name: /Confirm import/ });
    expect(confirm.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("CSV text"), { target: { value: "timestamp,glucose_mg_dl\n2026-10-15 08:00:00,132\n" } });
    fireEvent.click(screen.getByRole("button", { name: /Preview/ }));

    await waitFor(() => expect(api.importReadingsCsv).toHaveBeenCalledWith("GT-001", expect.objectContaining({ dry_run: true })));
    expect(await screen.findByText(/Dry run: 1 row\(s\) would be stored/)).toBeTruthy();
    expect(screen.getByText(/timestamp could not be parsed/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Confirm import/ }).disabled).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: /Confirm import/ }));
    await waitFor(() => expect(api.importReadingsCsv).toHaveBeenCalledWith("GT-001", expect.objectContaining({ dry_run: false })));
    expect(await screen.findByText(/1 reading\(s\) stored, 1 rejected/)).toBeTruthy();
    expect(refreshAll).toHaveBeenCalled();
  });

  it("uploads a selected CSV file via the multipart endpoint, then confirms it", async () => {
    api.uploadReadingsCsv.mockImplementation((_id, _file, dryRun) =>
      Promise.resolve({
        message: dryRun
          ? "Dry run: 2 row(s) would be stored, 0 would be rejected (0 duplicate). File: readings.csv."
          : "2 reading(s) stored, 0 rejected (0 duplicate). File: readings.csv.",
        accepted_count: 2,
        rejected_count: 0,
        duplicate_count: 0,
        persisted: !dryRun,
        dry_run: dryRun,
        filename: "readings.csv",
        rows: [],
      })
    );
    render(<DataEntry />);

    const file = new File(["timestamp,glucose_mg_dl\n2026-10-15 08:00:00,132\n"], "readings.csv", {
      type: "text/csv",
    });
    fireEvent.change(screen.getByTestId("csv-file"), { target: { files: [file] } });

    // choosing a file switches the preview action to the upload path
    fireEvent.click(await screen.findByRole("button", { name: /Preview upload/ }));
    await waitFor(() =>
      expect(api.uploadReadingsCsv).toHaveBeenCalledWith("GT-001", file, true)
    );
    expect(api.importReadingsCsv).not.toHaveBeenCalled();
    expect(await screen.findByText(/File: readings.csv/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Confirm import/ }));
    await waitFor(() =>
      expect(api.uploadReadingsCsv).toHaveBeenCalledWith("GT-001", file, false)
    );
    expect(refreshAll).toHaveBeenCalled();
  });

  it("shows the backend error for a structurally invalid CSV", async () => {
    api.importReadingsCsv.mockRejectedValue(new Error("CSV must contain a 'timestamp' column (found: a, b)"));
    render(<DataEntry />);
    fireEvent.change(screen.getByLabelText("CSV text"), { target: { value: "a,b\n1,2\n" } });
    fireEvent.click(screen.getByRole("button", { name: /Preview/ }));
    expect(await screen.findByText(/CSV must contain a 'timestamp' column/)).toBeTruthy();
  });

  it("appends an EHR-style record", async () => {
    api.addEhr.mockResolvedValue({ record_id: "EHR-DB-ABC123", record_type: "Lab panel", record_date: "2026-02-10" });
    render(<DataEntry />);
    fireEvent.change(screen.getByLabelText(/Record date/), { target: { value: "2026-02-10" } });
    fireEvent.change(screen.getByLabelText(/Record type/), { target: { value: "Lab panel" } });
    fireEvent.click(screen.getByRole("button", { name: /Add EHR record/ }));

    await waitFor(() => expect(api.addEhr).toHaveBeenCalledTimes(1));
    expect(api.addEhr.mock.calls[0][0]).toBe("GT-001");
    expect(api.addEhr.mock.calls[0][1]).toMatchObject({ record_date: "2026-02-10", record_type: "Lab panel" });
    expect(await screen.findByText(/Saved record EHR-DB-ABC123/)).toBeTruthy();
  });

  it("prompts to select a patient when none is chosen", () => {
    useApp.mockReturnValue({ selectedId: null, patients: [], profile: null, refreshAll });
    render(<DataEntry />);
    expect(screen.getByText(/Choose a patient from the header/)).toBeTruthy();
  });
});
