"""Risk assessment against configurable glucose thresholds."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .. import config

_LEVEL_ORDER = {"none": 0, "medium": 1, "high": 2, "critical": 3}

_LEVEL_LABELS = {
    "none": "In expected range",
    "medium": "Elevated glucose predicted",
    "high": "Threshold violation predicted",
    "critical": "Severe threshold violation predicted",
}


@dataclass(frozen=True)
class Thresholds:
    unit: str
    hypo_low: float
    hypo_critical: float
    hyper_high: float
    hyper_critical: float
    disclaimer: str

    def as_dict(self) -> dict:
        return {
            "unit": self.unit,
            "hypo_low_mg_dl": self.hypo_low,
            "hypo_critical_mg_dl": self.hypo_critical,
            "hyper_high_mg_dl": self.hyper_high,
            "hyper_critical_mg_dl": self.hyper_critical,
            "disclaimer": self.disclaimer,
        }


def load_thresholds(path: Path | str | None = None) -> Thresholds:
    path = Path(path or config.THRESHOLDS_JSON)
    if not path.exists():
        return Thresholds(
            unit="mg/dL",
            hypo_low=70.0,
            hypo_critical=54.0,
            hyper_high=180.0,
            hyper_critical=250.0,
            disclaimer="Default demonstration thresholds; not clinically validated.",
        )
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return Thresholds(
        unit=raw.get("unit", "mg/dL"),
        hypo_low=float(raw["hypo"]["low_mg_dl"]),
        hypo_critical=float(raw["hypo"]["critical_mg_dl"]),
        hyper_high=float(raw["hyper"]["high_mg_dl"]),
        hyper_critical=float(raw["hyper"]["critical_mg_dl"]),
        disclaimer=raw.get("disclaimer", ""),
    )


def assess(
    points: list[dict],
    thresholds: Thresholds | None = None,
    current_glucose: float | None = None,
) -> dict:
    """Assess predicted trajectory points against configured thresholds.

    ``points`` entries need ``predicted_glucose`` and ``timestamp``.
    Returns overall level, human label, and individual triggered flags.
    """
    th = thresholds or load_thresholds()
    values = [float(p["predicted_glucose"]) for p in points]
    if current_glucose is not None:
        values = values + [float(current_glucose)]
    if not values:
        return {
            "level": "none",
            "label": _LEVEL_LABELS["none"],
            "flags": [],
            "thresholds": th.as_dict(),
            "assessed_values_count": 0,
        }

    flags: list[dict] = []

    def first_point(predicate) -> dict | None:
        for p in points:
            if predicate(float(p["predicted_glucose"])):
                return p
        return None

    critical_low = first_point(lambda v: v < th.hypo_critical)
    if critical_low:
        flags.append(
            {
                "type": "hypoglycemia_critical",
                "severity": "critical",
                "threshold": th.hypo_critical,
                "unit": th.unit,
                "predicted_glucose": critical_low["predicted_glucose"],
                "at_timestamp": critical_low["timestamp"],
                "message": f"Predicted glucose below {th.hypo_critical} {th.unit}",
            }
        )

    low = first_point(lambda v: v < th.hypo_low)
    if low:
        flags.append(
            {
                "type": "hypoglycemia",
                "severity": "high",
                "threshold": th.hypo_low,
                "unit": th.unit,
                "predicted_glucose": low["predicted_glucose"],
                "at_timestamp": low["timestamp"],
                "message": f"Predicted glucose below {th.hypo_low} {th.unit}",
            }
        )

    critical_high = first_point(lambda v: v > th.hyper_critical)
    if critical_high:
        flags.append(
            {
                "type": "hyperglycemia_critical",
                "severity": "critical",
                "threshold": th.hyper_critical,
                "unit": th.unit,
                "predicted_glucose": critical_high["predicted_glucose"],
                "at_timestamp": critical_high["timestamp"],
                "message": f"Predicted glucose above {th.hyper_critical} {th.unit}",
            }
        )

    high = first_point(lambda v: v > th.hyper_high)
    if high:
        flags.append(
            {
                "type": "hyperglycemia",
                "severity": "medium",
                "threshold": th.hyper_high,
                "unit": th.unit,
                "predicted_glucose": high["predicted_glucose"],
                "at_timestamp": high["timestamp"],
                "message": f"Predicted glucose above {th.hyper_high} {th.unit}",
            }
        )

    level = "none"
    for flag in flags:
        if _LEVEL_ORDER[flag["severity"]] > _LEVEL_ORDER[level]:
            level = flag["severity"]

    return {
        "level": level,
        "label": _LEVEL_LABELS[level],
        "flags": flags,
        "thresholds": th.as_dict(),
        "assessed_values_count": len(values),
        "predicted_min_mg_dl": round(min(values), 1),
        "predicted_max_mg_dl": round(max(values), 1),
    }
