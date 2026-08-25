"""Small explainable ML comparison model for the BhuSanket prototype."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from sklearn.ensemble import RandomForestClassifier

from .risk_engine import calculate_risk


FEATURES = (
    "rainfall",
    "accumulated",
    "moisture",
    "slope",
    "susceptibility",
    "history",
    "exposure",
)
FEATURE_LABELS = {
    "rainfall": "Current rainfall",
    "accumulated": "Accumulated rainfall",
    "moisture": "Soil moisture",
    "slope": "Slope",
    "susceptibility": "Terrain susceptibility",
    "history": "Historical vulnerability",
    "exposure": "Exposure",
}


def _load_training_data() -> list[dict[str, Any]]:
    path = Path(__file__).parent / "data" / "historical_training.json"
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def _train() -> RandomForestClassifier:
    rows = _load_training_data()
    model = RandomForestClassifier(n_estimators=160, max_depth=5, random_state=42, class_weight="balanced")
    model.fit([[row[field] for field in FEATURES] for row in rows], [row["risk_level"] for row in rows])
    return model


MODEL = _train()


def compare_risk(zone: Mapping[str, Any]) -> dict[str, Any]:
    """Compare the explainable baseline with the prototype historical classifier."""
    baseline = calculate_risk(zone)
    values = [[float(zone[field]) for field in FEATURES]]
    predicted_level = str(MODEL.predict(values)[0])
    probabilities = MODEL.predict_proba(values)[0]
    confidence = round(float(max(probabilities)) * 100)
    importance = dict(zip(FEATURES, MODEL.feature_importances_))
    ranked = sorted(FEATURES, key=lambda field: importance[field], reverse=True)
    drivers = [
        {
            "name": FEATURE_LABELS[field],
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
            "summary": "Model agrees with the deterministic baseline." if agreement else "Model differs from the deterministic baseline; review required.",
        },
    }
