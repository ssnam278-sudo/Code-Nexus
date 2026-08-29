"""Second-opinion risk model for the "AI vs baseline" card.

Primary: a small Random Forest trained on ``data/historical_training.json``
(needs scikit-learn). Fallback (no dependency): a logistic surrogate over the
same four factors as the risk engine, with fixed coefficients. Either way
``compare_risk`` always returns a real number and the same response shape, so
the card is never a broken stub.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

from .risk_engine import calculate_risk, normalised_factors, _validate_zone


_RF_FEATURES = ("rainfall", "accumulated", "moisture", "slope", "susceptibility", "history", "exposure")
_RF_LABELS = {
    "rainfall": "Current rainfall",
    "accumulated": "Accumulated rainfall",
    "moisture": "Soil moisture",
    "slope": "Slope",
    "susceptibility": "Terrain susceptibility",
    "history": "Historical vulnerability",
    "exposure": "Exposure",
}

# logistic surrogate — coefficients ~ proportional to the engine weights, on
# factor inputs scaled to 0..1. Tuned so the decision points line up with the
# 35 / 55 / 75 bands.
_SURROGATE = {
    "bias": -4.15,
    "Rainfall pressure": 4.0,
    "Soil saturation": 2.7,
    "Terrain susceptibility": 2.5,
    "Historical susceptibility": 1.3,
}

_rf_model = None
_rf_error: str | None = None


def _load_training_data() -> list[dict[str, Any]]:
    path = Path(__file__).parent / "data" / "historical_training.json"
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def _get_rf_model():
    """Lazily train the RF model; cache the failure so we only try once."""
    global _rf_model, _rf_error
    if _rf_model is not None or _rf_error is not None:
        return _rf_model
    try:
        from sklearn.ensemble import RandomForestClassifier

        rows = _load_training_data()
        model = RandomForestClassifier(
            n_estimators=160, max_depth=5, random_state=42, class_weight="balanced"
        )
        model.fit(
            [[row[field] for field in _RF_FEATURES] for row in rows],
            [row["risk_level"] for row in rows],
        )
        _rf_model = model
    except Exception as exc:  # ImportError, data issues, etc.
        _rf_error = str(exc)
    return _rf_model


def _level_from_probability(p: float) -> str:
    if p >= 0.80:
        return "Critical"
    if p >= 0.58:
        return "High"
    if p >= 0.34:
        return "Advisory"
    return "Monitoring"


def _fallback_compare(zone: Mapping[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    values = _validate_zone(zone)
    factors = normalised_factors(values)  # each 0..100
    terms = {name: _SURROGATE[name] * (factors[name] / 100.0) for name in factors}
    z = _SURROGATE["bias"] + sum(terms.values())
    probability = 1.0 / (1.0 + math.exp(-z))
    level = _level_from_probability(probability)
    confidence = round(55 + abs(probability - 0.5) * 2 * 40)  # 55..95
    drivers = [
        {"name": name, "value": round(factors[name], 1), "importance": round(term / (sum(abs(t) for t in terms.values()) or 1) * 100, 1)}
        for name, term in sorted(terms.items(), key=lambda kv: kv[1], reverse=True)[:3]
    ]
    agreement = level == baseline["risk_level"]
    explanation = (
        f"Logistic surrogate model predicts {level.lower()} risk "
        f"({round(probability * 100)}% failure probability, {confidence}% confidence). "
        f"Strongest terms: {', '.join(d['name'].lower() for d in drivers[:2])}."
    )
    return {
        "baseline": baseline,
        "model": {
            "name": "Logistic surrogate",
            "prediction": level,
            "confidence": confidence,
            "probability_pct": round(probability * 100),
            "explanation": explanation,
            "top_drivers": drivers,
        },
        "comparison": {
            "agrees": agreement,
            "summary": "Surrogate agrees with the risk engine."
            if agreement
            else "Surrogate differs from the risk engine; review required.",
        },
    }


def compare_risk(zone: Mapping[str, Any]) -> dict[str, Any]:
    """Compare the risk engine with a learned second opinion.

    Uses the Random Forest when scikit-learn is present, otherwise a
    dependency-free logistic surrogate. Same shape either way.
    """
    baseline = calculate_risk(zone)
    model = _get_rf_model()
    if model is None:
        return _fallback_compare(zone, baseline)

    values = [[float(zone[field]) for field in _RF_FEATURES]]
    predicted_level = str(model.predict(values)[0])
    probabilities = model.predict_proba(values)[0]
    confidence = round(float(max(probabilities)) * 100)
    importance = dict(zip(_RF_FEATURES, model.feature_importances_))
    ranked = sorted(_RF_FEATURES, key=lambda field: importance[field], reverse=True)
    drivers = [
        {
            "name": _RF_LABELS[field],
            "value": zone[field],
            "importance": round(float(importance[field]) * 100, 1),
        }
        for field in ranked[:3]
    ]
    agreement = predicted_level == baseline["risk_level"]
    explanation = (
        f"The historical classifier predicts {predicted_level.lower()} risk with {confidence}% confidence. "
        f"Its strongest learned drivers are {', '.join(driver['name'].lower() for driver in drivers[:2])}."
    )
    return {
        "baseline": baseline,
        "model": {
            "name": "Random Forest prototype",
            "prediction": predicted_level,
            "confidence": confidence,
            "explanation": explanation,
            "top_drivers": drivers,
        },
        "comparison": {
            "agrees": agreement,
            "summary": "Model agrees with the deterministic baseline."
            if agreement
            else "Model differs from the deterministic baseline; review required.",
        },
    }
