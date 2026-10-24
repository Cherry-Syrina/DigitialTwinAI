# GlucoTwin AI — demo script (15–20 min)

Goal: show a **live digital twin** that forecasts and flags risk, then explain *why it works* and
how it is *verified*. Keep the warm-up tight — the wow is the twin replaying and flagging.

---

## Setup checklist (before the audience arrives)

- [ ] Terminal 1: backend running → `http://localhost:8000/api/health` returns `ok, model_loaded=True`
- [ ] Terminal 2: `npm run dev` in `frontend/` → `http://localhost:5173`
- [ ] Pick **GT-003** (starts "medium hyperglycemia") and **GT-001** (stable/controlled) as the
      two demo patients.
- [ ] Open `docs/presentation/index.html` in a second monitor. Enable "Presentation" system mode.
- [ ] Smartphone/recorder ready if filming (see README §5).

## Part A — Pitch (slides, ~5 min)

1. **Cover — GlucoTwin AI.** "A predictive digital twin that turns a glucose stream into
   forecast-aware risk."
2. **Problem (01).** Readings are always in the past; decisions are reactive.
3. **Idea (02).** Per-patient twin, updated every 5 minutes; forecasts + risk flags.
4. **Architecture (03).** Data → validation → twin engine → GBM forecaster → risk → FastAPI →
   dashboard. Call out the **synthetic-data boundary** and the model registry.
5. **Twin engine (04).** Replay, windowed state, what-if, provenance.
6. **Model + results (05–06).** One validation-selected Ridge or GBM per horizon; chronological 70/15/15 train/validation/test; table of MAE vs
   persistence. Emphasize: *the gap widens with the horizon*.

## Part B — Live demo (~8 min), in the app

1. **Overview.** Show the patient selector and dashboard cards.
2. **Twin Monitor.** Press **Advance (20 min)** several times — the glucose line replays the
   morning rise. *"This is the twin living through the patient's day."*
3. **Prediction & Risk.** Stay on GT-003: the badge flips **medium → hyperglycemia** with a flag
   and a horizon. Read the flag message aloud. *"The twin warns before the threshold is hit."*
4. **What-if.** Add ~6 extra units of insulin (or change carbs) and re-run: watch the forecast
   curve bend. *"Scenario simulation on your own twin."*
5. **Model Info.** Show the metrics table vs persistence and the feature list.
6. **Doctor View.** Hit **Export report** → a `.md` consult-style summary downloads. *"Human-readable
   output for a clinician-facing workflow."*
7. **API (if time).** One `curl`/`Invoke-RestMethod` to `/api/patients/GT-003/predict` and `/docs`.
   A one-liner beats listing all files.

## Part C — Verification & credibility (~3 min)

- `pytest tests` → **90 passed** in the backend suite (plus 46 frontend Vitest tests in the current audit).
- Point at `metrics.json` improvement column; say explicitly *"synthetic-data metrics, not clinical
  claims"*.
- Floating **"Synthetic"** tags and disclaimer in the UI.

## Part D — Close (~2 min)

Roadmap slide (validation pathway), replay the 2-line message:
> *"You get the twin, the forecast, and the flag before the event — and it's verified to be leak-free
> and reproducible on synthetic data."*

## Common questions

- **Is glucose really predictable?** At these horizons a well-engineered autocorrelation model
  (GBM + lags) is a strong prior; the improvement-over-persistence column shows exactly where that
  works.
- **Why synthetic?** No patient data was available for a hackathon; a deterministic generator makes
  the pipeline auditable and the demo reproducible.
- **Real-world path?** Swap `data/synthetic` for de-identified CGM, re-train, validate, then
  clinician review — the interface and contracts do not change.

## Post-demo

- Stop servers, or leave running for judges/back-to-back slots.
- Save the demo video (README §5).