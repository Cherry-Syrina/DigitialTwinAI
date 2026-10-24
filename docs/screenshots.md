# Screenshot guide

For README.md, submission slides, or the poster. Take PNGs at 1920×1080 (or retina).
All screenshots should visibly include the **"Synthetic"** tag so the demo is honest.

## Suggested shots

1. **Overview** — `/overview`, patient **GT-003** selected. KPI cards + risk badge + glucose chart.
2. **Twin Monitor** — after a few **Advance (20 min)** clicks, chart replayed ~2 h.
3. **Prediction & Risk** — forecast bands and the **medium** hyperglycemia flag with target time.
4. **What-if** — override panel open with a changed insulin value and the comparison curve.
5. **Model Info** — the MAE/RMSE vs persistence table.
6. **Doctor View** — patient card + risk flags + the report preview box.
7. **API docs** — `/docs` open at `/api/patients/{id}/digital-twin`.

## Arms-length rules so nothing leaks

- No real patient info can appear (data is fictional), but keep on-screen PII minimal anyway.
- Keep the tab showing `localhost:5173` / `localhost:8000/docs` — never internal tools, tokens,
  or file explorers with your username.
- Add the *"synthetic data"* disclaimer text caption under each shared image.

## Where to save

`docs/screenshots/` → e.g. `overview.png`, `twin-monitor.png`, `prediction-risk.png`,
`what-if.png`, `model-info.png`, `doctor-view.png`, `api-docs.png`. (Folder is gitignored only if
you prefer; by default commit the images so the README can link them.)