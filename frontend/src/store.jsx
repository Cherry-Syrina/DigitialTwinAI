import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./api";

const AppContext = createContext(null);

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside <AppProvider>");
  return ctx;
}

const HISTORY_HOURS = 8;

export function AppProvider({ children }) {
  const [patients, setPatients] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [profile, setProfile] = useState(null);
  const [history, setHistory] = useState([]);
  const [twin, setTwin] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [thresholds, setThresholds] = useState(null);
  const [health, setHealth] = useState(null);

  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [loaded, setLoaded] = useState(false);

  const loadPatients = useCallback(async () => {
    const list = await api.patients();
    setPatients(list);
    setSelectedId((cur) => cur || list[0]?.patient_id || null);
    return list;
  }, []);

  const selectPatient = useCallback((id) => {
    setSelectedId(id);
    setTwin(null);
    setProfile(null);
    setError(null);
  }, []);

  const loadHealth = useCallback(async () => {
    try {
      setHealth(await api.health());
    } catch (err) {
      setHealth({ status: "degraded", error: err.message });
    }
  }, []);

  const loadPatientData = useCallback(async (id = selectedId) => {
    if (!id) return null;
    setBusy(true);
    setError(null);
    try {
      const tw = await api.twin(id);
      setTwin(tw);
      const [prof, hist] = await Promise.all([
        api.patient(id),
        api.history(id, { hours: HISTORY_HOURS }),
      ]);
      setProfile(prof);
      setHistory(hist.readings || []);
      setBusy(false);
      setLoaded(true);
      return tw;
    } catch (err) {
      setError(err.message);
      setBusy(false);
      return null;
    }
  }, [selectedId]);

  const advanceDemo = useCallback(async (steps = 12, id = selectedId) => {
    if (!id) return null;
    setBusy(true);
    try {
      const res = await api.advanceDemo({ patient_id: id, steps });
      const tw = await api.twin(id);
      setTwin(tw);
      const hist = await api.history(id, { hours: HISTORY_HOURS });
      setHistory(hist.readings || []);
      setBusy(false);
      return res;
    } catch (err) {
      setError(err.message);
      setBusy(false);
      return null;
    }
  }, [selectedId]);

  const refreshTwin = useCallback(async () => {
    if (!selectedId) return null;
    try {
      const tw = await api.twin(selectedId);
      setTwin(tw);
      const hist = await api.history(selectedId, { hours: HISTORY_HOURS });
      setHistory(hist.readings || []);
      return tw;
    } catch (err) {
      setError(err.message);
      return null;
    }
  }, [selectedId]);

  const refreshAll = useCallback(async () => {
    // Reload the patient list AND the selected patient's twin/profile/history.
    // Used after registration, edits or data imports so every page is current.
    const list = await loadPatients();
    await loadPatientData(selectedId);
    return list;
  }, [loadPatients, loadPatientData, selectedId]);

  const runPrediction = useCallback(
    async (payload = {}) => {
      if (!selectedId) {
        setError("No patient selected");
        return null;
      }
      setBusy(true);
      try {
        const pred = await api.predict(selectedId, payload);
        await refreshTwin();
        setBusy(false);
        return pred;
      } catch (err) {
        setError(err.message);
        setBusy(false);
        return null;
      }
    },
    [selectedId, refreshTwin]
  );

  const initialLoad = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([loadHealth(), api.metrics().then(setMetrics), api.thresholds().then(setThresholds)]);
      const list = await api.patients();
      setPatients(list);
      const first = list[0]?.patient_id || null;
      setSelectedId((cur) => cur || first);
      setLoading(false);
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  }, [loadHealth]);

  useEffect(() => {
    if (!loading && !loaded && selectedId) {
      loadPatientData(selectedId);
    }
  }, [loading, loaded, selectedId, loadPatientData]);

  useEffect(() => {
    initialLoad();
  }, [initialLoad]);

  const value = useMemo(
    () => ({
      patients,
      selectedId,
      profile,
      history,
      twin,
      metrics,
      thresholds,
      health,
      loading,
      busy,
      error,
      setError,
      selectPatient,
      loadHealth,
      initialLoad,
      loadPatients,
      loadPatientData,
      refreshTwin,
      refreshAll,
      advanceDemo,
      runPrediction,
    }),
    [
      patients, selectedId, profile, history, twin, metrics, thresholds, health,
      loading, busy, error, selectPatient, loadHealth, initialLoad, loadPatients,
      loadPatientData, refreshTwin, refreshAll, advanceDemo, runPrediction,
    ]
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}