import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppProvider } from "./store";
import Layout from "./components/Layout";
import Overview from "./pages/Overview";
import Profile from "./pages/Profile";
import TwinMonitor from "./pages/TwinMonitor";
import PredictionRisk from "./pages/PredictionRisk";
import WhatIf from "./pages/WhatIf";
import Doctor from "./pages/Doctor";
import Patients from "./pages/Patients";
import AddPatient from "./pages/AddPatient";
import DataEntry from "./pages/DataEntry";
import Reports from "./pages/Reports";

export default function App() {
  return (
    <AppProvider>
      <HashRouter
        future={{
          // Opt in early to v7 relative splat-path resolution (safe here: all our
          // NavLinks and redirects use absolute paths, no relative links inside splat routes).
          v7_relativeSplatPath: true,
          // Explicitly keep current (non-startTransition) state updates — identical
          // behaviour to leaving it undefined, silences the sibling deprecation warning.
          v7_startTransition: false,
        }}
      >
        <Routes>
          <Route element={<Layout />}>
            <Route path="/overview" element={<Overview />} />
            <Route path="/patients" element={<Patients />} />
            <Route path="/patients/new" element={<AddPatient />} />
            <Route path="/patients/:patient_id/edit" element={<AddPatient />} />
            <Route path="/data-entry" element={<DataEntry />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/twin" element={<TwinMonitor />} />
            <Route path="/prediction" element={<PredictionRisk />} />
            <Route path="/whatif" element={<WhatIf />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/doctor" element={<Doctor />} />
            <Route path="/" element={<Navigate to="/overview" replace />} />
            <Route path="*" element={<Navigate to="/overview" replace />} />
          </Route>
        </Routes>
      </HashRouter>
    </AppProvider>
  );
}