import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AddPatient from "./AddPatient";
import { useApp } from "../store";
import { api } from "../api";

vi.mock("../store", () => ({ useApp: vi.fn() }));
vi.mock("../api", () => ({
  api: { createPatient: vi.fn(), updatePatient: vi.fn(), patient: vi.fn() },
}));

const refreshAll = vi.fn();

function renderNew() {
  return render(
    <MemoryRouter initialEntries={["/patients/new"]}>
      <Routes>
        <Route path="/patients/new" element={<AddPatient />} />
      </Routes>
    </MemoryRouter>
  );
}

function fillRequired() {
  fireEvent.change(screen.getByLabelText(/Patient ID/), { target: { value: "DOC-100" } });
  fireEvent.change(screen.getByLabelText(/Full name/), { target: { value: "Jane Demo" } });
  fireEvent.change(screen.getByLabelText(/Age/), { target: { value: "55" } });
  fireEvent.change(screen.getByLabelText(/Years since diagnosis/), { target: { value: "9" } });
  fireEvent.change(screen.getByLabelText(/Height \(cm\)/), { target: { value: "165" } });
  fireEvent.change(screen.getByLabelText(/Weight \(kg\)/), { target: { value: "70" } });
  fireEvent.change(screen.getByLabelText(/^BMI/), { target: { value: "25.7" } });
  fireEvent.change(screen.getByLabelText(/Latest HbA1c/), { target: { value: "7.2" } });
  fireEvent.change(screen.getByLabelText(/Relevant medical history/), { target: { value: "Hypertension" } });
}

beforeEach(() => {
  useApp.mockReturnValue({ refreshAll, patients: [], selectedId: null });
  api.createPatient.mockReset();
  api.updatePatient.mockReset();
  refreshAll.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("AddPatient (registration)", () => {
  it("blocks submission and shows field errors when required data is missing", async () => {
    renderNew();
    fireEvent.click(screen.getByRole("button", { name: /Register patient/ }));

    expect(await screen.findByText(/Patient ID is required|2-32 characters/)).toBeTruthy();
    expect(screen.getByText("Name is required")).toBeTruthy();
    expect(screen.getByText(/Age is required/)).toBeTruthy();
    expect(screen.getByText(/field error/)).toBeTruthy();
    expect(api.createPatient).not.toHaveBeenCalled();
  });

  it("rejects an out-of-range value client-side", async () => {
    renderNew();
    fillRequired();
    fireEvent.change(screen.getByLabelText(/^BMI/), { target: { value: "900" } });
    fireEvent.click(screen.getByRole("button", { name: /Register patient/ }));

    expect(await screen.findByText(/BMI must be between 5 and 120/)).toBeTruthy();
    expect(api.createPatient).not.toHaveBeenCalled();
  });

  it("submits a valid patient, refreshes app data and confirms success", async () => {
    api.createPatient.mockResolvedValue({ patient_id: "DOC-100", name: "Jane Demo" });
    renderNew();
    fillRequired();
    fireEvent.click(screen.getByRole("button", { name: /Register patient/ }));

    await waitFor(() => expect(api.createPatient).toHaveBeenCalledTimes(1));
    const payload = api.createPatient.mock.calls[0][0];
    expect(payload).toMatchObject({
      patient_id: "DOC-100",
      name: "Jane Demo",
      age: 55,
      years_since_diagnosis: 9,
      height_cm: 165,
      weight_kg: 70,
      hba1c_pct: 7.2,
      medical_history: ["Hypertension"],
    });
    expect(refreshAll).toHaveBeenCalledTimes(1);
    expect(await screen.findByText(/Registered Jane Demo \(DOC-100\)/)).toBeTruthy();
  });

  it("surfaces a duplicate-ID conflict (409) from the server", async () => {
    const conflict = new Error("Patient ID 'DOC-100' already exists. Choose a different, unique ID.");
    conflict.status = 409;
    api.createPatient.mockRejectedValue(conflict);
    renderNew();
    fillRequired();
    fireEvent.click(screen.getByRole("button", { name: /Register patient/ }));

    expect(await screen.findByText(/already exists/)).toBeTruthy();
    expect(screen.getByText(/Duplicate IDs are not allowed/)).toBeTruthy();
  });
});
