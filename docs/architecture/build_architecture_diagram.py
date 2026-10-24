"""Builds the GlucoTwin AI architecture diagram.

Outputs (into docs/architecture/):
  architecture.png / .svg / .pdf

Source-of-truth diagram: docs/architecture/architecture.mmd (Mermaid).

Run:  python -m docs.architecture.build_architecture_diagram
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent

NAVY = "#0f2a43"
TEAL = "#0d9488"
TEAL_LIGHT = "#e6f7f5"
AMBER = "#b45309"
SLATE = "#475569"
GRAY = "#94a3b8"


def box(ax, x, y, w, h, title, subtitle="", face=NAVY):
    """Solid box with two-line centered text."""
    patch = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.02",
        linewidth=1.0, edgecolor=face, facecolor=face, zorder=3,
    )
    ax.add_patch(patch)
    cy = y + h / 2 + (0.07 if subtitle else 0.0)
    ax.text(x + w / 2, cy, title, ha="center", va="center", fontsize=10,
            fontweight="bold", color="white", zorder=4)
    if subtitle:
        ax.text(x + w / 2, y + h / 2 - 0.09, subtitle, ha="center", va="center",
                fontsize=7.5, color="white", alpha=0.9, zorder=4)


def tbox(ax, x, y, w, h, title, subtitle="", edge=TEAL, face=TEAL_LIGHT):
    patch = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.02",
        linewidth=1.4, edgecolor=edge, facecolor=face, zorder=3,
    )
    ax.add_patch(patch)
    cy = y + h / 2 + (0.07 if subtitle else 0.0)
    ax.text(x + w / 2, cy, title, ha="center", va="center", fontsize=10,
            fontweight="bold", color=NAVY, zorder=4)
    if subtitle:
        ax.text(x + w / 2, y + h / 2 - 0.09, subtitle, ha="center", va="center",
                fontsize=7.5, color=SLATE, zorder=4)


def arrow(ax, p1, p2, color=TEAL, dashed=False, lw=2.2):
    a = FancyArrowPatch(
        p1, p2, arrowstyle="-|>", mutation_scale=16, linewidth=lw,
        color=color, linestyle=(0, (4, 3)) if dashed else "-",
        zorder=5, shrinkA=3, shrinkB=3,
    )
    ax.add_patch(a)


def label(ax, x, y, text, size=7.5, color=SLATE):
    ax.text(x, y, text, ha="center", va="center", fontsize=size, color=color, zorder=4)


def build() -> None:
    fig, ax = plt.subplots(figsize=(13.5, 9.2), dpi=160)
    ax.set_xlim(0, 13.5)
    ax.set_ylim(0, 9.2)
    ax.axis("off")

    ax.text(6.75, 8.9, "GlucoTwin AI — System Architecture", ha="center", fontsize=18,
            fontweight="bold", color=NAVY)
    ax.text(6.75, 8.58, "Predictive Digital Twin for Personalized Diabetes Risk Monitoring (synthetic demonstration data)",
            ha="center", fontsize=9.5, color=SLATE)

    # --------------------------------------------------------------- inputs
    tbox(ax, 0.45, 6.8, 2.55, 0.9, "Synthetic EHR Data", "profiles · EHR-like records\nprevious glucose summaries")
    tbox(ax, 3.35, 6.8, 2.6, 0.9, "Synthetic CGM / Wearables", "5-min glucose time-series\nsteps · sleep · meals · heart rate")
    box(ax, 6.35, 6.8, 2.6, 0.9, "Data Validation &\nPreprocessing", "schema checks · gaps\nfeature construction")
    box(ax, 9.5, 6.8, 3.0, 0.9, "Storage", "data/synthetic/*.csv\nmodels/model_h*.joblib\nmodels/metrics.json")

    arrow(ax, (3.0, 7.25), (6.35, 7.25))
    arrow(ax, (5.95, 7.25), (6.35, 7.25))
    arrow(ax, (8.95, 7.25), (9.5, 7.25), color=SLATE, dashed=True)
    label(ax, 9.22, 7.45, "artifacts", size=7)

    # ------------------------------------------------------------ twin engine
    box(ax, 6.35, 5.35, 2.6, 0.95, "Digital Twin Engine", "per-patient state\nreplay sensor feed · window")
    arrow(ax, (7.65, 6.8), (7.65, 6.3))

    # -------------------------------------------------------- training branch
    box(ax, 3.35, 4.1, 2.6, 0.9, "Training & Evaluation", "time-ordered 70/15/15 split\nvalidation selection · embargoed test\npersistence · Ridge · GBM", face=SLATE)
    arrow(ax, (8.95, 7.5), (5.95, 4.7), color=SLATE, dashed=True)
    label(ax, 7.3, 6.35, "trained artifacts (joblib)", size=7, color=SLATE)
    box(ax, 9.5, 4.1, 3.0, 0.9, "Model Registry", "per-horizon artifact + metadata\nversion · features · median stats", face=SLATE)
    arrow(ax, (5.95, 4.55), (9.5, 4.55), color=SLATE, dashed=True)
    label(ax, 7.75, 4.28, "persist / load", size=7, color=SLATE)

    # ------------------------------------------------------------- inference
    box(ax, 3.35, 2.7, 2.6, 0.9, "Forecasting Model", "validation-selected Ridge / GBM per horizon\npast-only features · glucose(t + 30/60/90/120m)", face=TEAL)
    arrow(ax, (7.65, 5.35), (4.65, 3.6))
    label(ax, 6.2, 4.55, "latest valid window", size=7)
    arrow(ax, (9.5, 4.6), (5.95, 3.4), color=SLATE, dashed=True)
    label(ax, 7.85, 4.0, "load artifacts", size=7)

    box(ax, 3.35, 1.35, 2.6, 0.9, "Risk Assessment & Alerts", "configurable thresholds\nhyper/hypo flags · levels", face=AMBER)
    arrow(ax, (4.65, 2.7), (4.65, 2.25))

    # ---------------------------------------------------------------- serving
    box(ax, 0.9, 0.0, 3.1, 0.9, "FastAPI Backend Services", "/api/patients/{id}/predict\n/api/demo/advance · OpenAPI /docs")
    arrow(ax, (4.65, 1.35), (3.0, 0.9))
    arrow(ax, (5.95, 1.35), (8.9, 1.2), color=AMBER, dashed=True)
    label(ax, 7.6, 1.55, "risk flags", size=7, color=AMBER)

    box(ax, 8.9, 0.0, 3.4, 0.9, "React Dashboard", "10 views · Recharts · Tailwind · Lucide", face=TEAL)
    arrow(ax, (4.0, 0.45), (8.9, 0.45), lw=3.0)
    label(ax, 6.45, 0.7, "REST JSON", size=7.5)

    # ------------------------------------------------------ synthetic boundary
    border = FancyBboxPatch(
        (0.18, 2.7), 13.14, 5.95, boxstyle="round,pad=0.01,rounding_size=0.02",
        linewidth=1.6, edgecolor=AMBER, facecolor="none", linestyle=(0, (5, 3)), zorder=2,
    )
    ax.add_patch(border)
    ax.text(6.75, 8.35, "S Y N T H E T I C - D A T A   B O U N D A R Y   —   educational prototype only · not clinically validated",
            ha="center", va="center", fontsize=8.5, fontweight="bold", color=AMBER, zorder=4)

    # ---------------------------------------------------------------- legend
    ly = 0.18
    ax.text(0.45, ly + 0.06, "Legend:", fontsize=8, fontweight="bold", color=SLATE)
    for i, (label_text, color, dashed) in enumerate(
        [
            ("inference / data flow", TEAL, False),
            ("training / model artifacts", SLATE, True),
            ("risk / serving", NAVY, False),
        ]
    ):
        yy = ly - i * 0.24
        ax.plot([0.45, 0.8], [yy, yy], color=color, lw=2.4, linestyle=(0, (4, 3)) if dashed else "-")
        ax.text(0.92, yy, label_text, fontsize=8, color=SLATE, va="center")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg", "pdf"):
        fig.savefig(OUT_DIR / f"architecture.{ext}", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("Wrote architecture.png / architecture.svg / architecture.pdf into", OUT_DIR)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    build()