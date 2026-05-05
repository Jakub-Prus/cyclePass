from __future__ import annotations

from typing import Any

SPEED_LIMIT_LOW_STRESS_KPH = 30
SPEED_LIMIT_HIGH_RISK_KPH = 50
DEFAULT_SCORE = 50
PROTECTED_SCORE_BONUS = 35
LOW_STRESS_SCORE_BONUS = 18
SHARED_PATH_SCORE_BONUS = 8
HIGH_SPEED_PENALTY = 30
NO_BICYCLE_PENALTY = 70
TRUNK_PENALTY = 45
SIDEWALK_BONUS = 8
SURFACE_PENALTY = 15
MAX_SCORE = 100
MIN_SCORE = 0

HIGH_RISK_HIGHWAYS = {"motorway", "motorway_link", "trunk", "trunk_link"}
LOW_STRESS_HIGHWAYS = {"living_street", "residential", "service", "unclassified"}
SHARED_PATH_HIGHWAYS = {"path", "footway", "pedestrian", "track"}
ROUGH_SURFACES = {"ground", "gravel", "dirt", "mud", "sand"}
RIDEABLE_PATH_SURFACES = {"asphalt", "concrete", "compacted", "fine_gravel", "paved", "paving_stones"}
PROTECTED_CYCLEWAY_VALUES = {"track", "opposite_track", "separate"}
PAINTED_CYCLEWAY_VALUES = {"lane", "opposite_lane", "shared_lane"}
POSITIVE_BICYCLE_VALUES = {"yes", "designated", "permissive", "destination"}
NEGATIVE_BICYCLE_VALUES = {"no", "private"}
DISMOUNT_BICYCLE_VALUES = {"dismount"}

CLASS_LABELS = {
    "protected": "Protected / dedicated bike infrastructure",
    "low-stress": "Low-stress mixed street",
    "shared": "Sidewalk/shared path usable by bike",
    "not-suitable": "Not suitable for cycling",
}


def parse_maxspeed_to_kph(raw_value: Any) -> int | None:
    if raw_value is None or raw_value == "":
        return None

    if isinstance(raw_value, bool):
        return None

    if isinstance(raw_value, (int, float)):
        return round(float(raw_value))

    text = str(raw_value).strip().lower()
    numeric_text = text.replace("mph", "").strip()

    try:
        numeric_value = float(numeric_text)
    except ValueError:
        return None

    if "mph" in text:
        return round(numeric_value * 1.60934)

    return round(numeric_value)


def _clamp_score(score: int) -> int:
    return max(MIN_SCORE, min(MAX_SCORE, score))


def _normalize_tags(tags: dict[str, Any] | None = None) -> dict[str, Any]:
    tags = tags or {}
    return {
        "highway": _normalize_text_value(tags.get("highway")),
        "bicycle": _normalize_access_value(tags.get("bicycle")),
        "cycleway": _normalize_text_value(tags.get("cycleway")),
        "cycleway_left": _normalize_text_value(tags.get("cycleway:left")),
        "cycleway_right": _normalize_text_value(tags.get("cycleway:right")),
        "sidewalk": _normalize_text_value(tags.get("sidewalk")),
        "footway": _normalize_text_value(tags.get("footway")),
        "segregated": _normalize_text_value(tags.get("segregated")),
        "maxspeed": parse_maxspeed_to_kph(tags.get("maxspeed")),
        "surface": _normalize_text_value(tags.get("surface")),
        "bike_priority": _normalize_float_value(tags.get("cyclepass:bike_priority")),
        "name": tags.get("name") or tags.get("ref") or "Unnamed segment",
    }


def _normalize_text_value(raw_value: Any) -> str:
    if raw_value is None:
        return ""

    normalized = str(raw_value).strip().lower()
    if normalized in {"", "missing"}:
        return ""

    return normalized.replace(" ", "_")


def _normalize_access_value(raw_value: Any) -> str:
    if raw_value is True:
        return "yes"
    if raw_value is False:
        return "no"
    return _normalize_text_value(raw_value)


def _normalize_float_value(raw_value: Any) -> float | None:
    if raw_value is None or raw_value == "":
        return None

    if isinstance(raw_value, bool):
        return None

    if isinstance(raw_value, (int, float)):
        return float(raw_value)

    try:
        return float(str(raw_value).strip())
    except ValueError:
        return None


def _has_positive_bicycle_access(tags: dict[str, Any]) -> bool:
    return tags["bicycle"] in POSITIVE_BICYCLE_VALUES


def _has_negative_bicycle_access(tags: dict[str, Any]) -> bool:
    return tags["bicycle"] in NEGATIVE_BICYCLE_VALUES


def _requires_dismount(tags: dict[str, Any]) -> bool:
    return tags["bicycle"] in DISMOUNT_BICYCLE_VALUES


def _has_protected_cycleway(tags: dict[str, Any]) -> bool:
    return (
        tags["cycleway"] in PROTECTED_CYCLEWAY_VALUES
        or tags["cycleway_left"] in PROTECTED_CYCLEWAY_VALUES
        or tags["cycleway_right"] in PROTECTED_CYCLEWAY_VALUES
        or tags["highway"] == "cycleway"
    )


def _has_painted_cycleway(tags: dict[str, Any]) -> bool:
    return (
        tags["cycleway"] in PAINTED_CYCLEWAY_VALUES
        or tags["cycleway_left"] in PAINTED_CYCLEWAY_VALUES
        or tags["cycleway_right"] in PAINTED_CYCLEWAY_VALUES
    )


def _has_rideable_shared_path(tags: dict[str, Any]) -> bool:
    shared_path_highway = tags["highway"] in SHARED_PATH_HIGHWAYS
    sidewalk_present = tags["sidewalk"] in {"yes", "both", "left", "right", "separate"}
    explicitly_rideable = _has_positive_bicycle_access(tags)
    return (
        (shared_path_highway and explicitly_rideable)
        or (sidewalk_present and explicitly_rideable)
        or (tags["footway"] == "sidewalk" and explicitly_rideable)
    )


def _is_likely_rideable_unmapped_path(tags: dict[str, Any]) -> bool:
    if tags["highway"] not in SHARED_PATH_HIGHWAYS:
        return False

    if _has_negative_bicycle_access(tags) or _requires_dismount(tags):
        return False

    if tags["highway"] == "pedestrian":
        return False

    if tags["footway"] == "sidewalk":
        return True

    if tags["surface"]:
        return tags["surface"] in RIDEABLE_PATH_SURFACES

    return tags["highway"] in {"path", "track"}


def _build_allowed_state(tags: dict[str, Any]) -> str:
    if _has_negative_bicycle_access(tags):
        return "no"

    if _requires_dismount(tags):
        return "uncertain"

    if _has_positive_bicycle_access(tags) or _has_protected_cycleway(tags) or _has_painted_cycleway(tags):
        return "yes"

    if tags["highway"] in HIGH_RISK_HIGHWAYS:
        return "no"

    return "uncertain"


def _choose_class_name(tags: dict[str, Any], comfort_score: int) -> str:
    if _has_protected_cycleway(tags):
        return "protected"

    if _has_rideable_shared_path(tags) and tags["highway"] not in LOW_STRESS_HIGHWAYS:
        return "shared"

    if _is_likely_rideable_unmapped_path(tags):
        return "shared"

    if (
        tags["highway"] in LOW_STRESS_HIGHWAYS
        and (tags["maxspeed"] is None or tags["maxspeed"] <= SPEED_LIMIT_LOW_STRESS_KPH)
        and not _has_negative_bicycle_access(tags)
    ):
        return "low-stress"

    if (
        tags["bike_priority"] is not None
        and tags["bike_priority"] >= 0.85
        and tags["highway"] not in HIGH_RISK_HIGHWAYS
        and not _has_negative_bicycle_access(tags)
    ):
        return "low-stress"

    if comfort_score >= 55 and _has_painted_cycleway(tags):
        return "low-stress"

    if comfort_score >= 50 and _has_rideable_shared_path(tags):
        return "shared"

    return "not-suitable"


def _estimate_confidence(tags: dict[str, Any]) -> float:
    confidence = 0.45

    if tags["highway"]:
        confidence += 0.15
    if tags["maxspeed"] is not None:
        confidence += 0.10
    if tags["bicycle"] or tags["cycleway"] or tags["cycleway_left"] or tags["cycleway_right"]:
        confidence += 0.15
    if tags["sidewalk"] or tags["surface"]:
        confidence += 0.10

    return min(0.95, round(confidence, 2))


def classify_way(raw_tags: dict[str, Any] | None = None) -> dict[str, Any]:
    tags = _normalize_tags(raw_tags)
    reasons: list[str] = []
    score = DEFAULT_SCORE

    if _has_negative_bicycle_access(tags):
        score -= NO_BICYCLE_PENALTY
        reasons.append("OSM bicycle access explicitly forbids riding here.")

    if _requires_dismount(tags):
        score -= HIGH_SPEED_PENALTY
        reasons.append("OSM marks this segment as bicycle=dismount, so riding is restricted.")

    if _has_protected_cycleway(tags):
        score += PROTECTED_SCORE_BONUS
        reasons.append("Protected or dedicated cycleway tags were found.")
    elif _has_painted_cycleway(tags):
        score += LOW_STRESS_SCORE_BONUS
        reasons.append("A painted or shared cycle lane is mapped.")

    if tags["highway"] in LOW_STRESS_HIGHWAYS and tags["maxspeed"] is not None and tags["maxspeed"] <= SPEED_LIMIT_LOW_STRESS_KPH:
        score += LOW_STRESS_SCORE_BONUS
        reasons.append("The road class and low speed limit suggest calmer mixed traffic.")

    if _has_rideable_shared_path(tags):
        score += SHARED_PATH_SCORE_BONUS
        reasons.append("This path or sidewalk appears bike-usable from OSM access tags.")
    elif _is_likely_rideable_unmapped_path(tags):
        score += SHARED_PATH_SCORE_BONUS
        reasons.append(
            "This off-road path looks physically rideable from its highway type and surface, but bicycle access is not explicitly mapped."
        )

    if tags["sidewalk"] in {"yes", "both", "left", "right", "separate"}:
        score += SIDEWALK_BONUS
        reasons.append("Sidewalk presence improves fallback comfort, but it does not guarantee legal riding.")

    if tags["bike_priority"] is not None and tags["bike_priority"] >= 0.85:
        score += LOW_STRESS_SCORE_BONUS
        reasons.append("The self-hosted router marks this segment as strongly bike-preferred.")

    if tags["maxspeed"] is not None and tags["maxspeed"] >= SPEED_LIMIT_HIGH_RISK_KPH and not _has_protected_cycleway(tags):
        score -= HIGH_SPEED_PENALTY
        reasons.append("Higher speed traffic without protected infrastructure reduces cycling comfort.")

    if tags["highway"] in HIGH_RISK_HIGHWAYS and not _has_protected_cycleway(tags):
        score -= TRUNK_PENALTY
        reasons.append("This road class is usually hostile for cycling unless dedicated infrastructure exists.")

    if tags["surface"] in ROUGH_SURFACES:
        score -= SURFACE_PENALTY
        reasons.append("Surface quality looks rough from OSM tags.")

    comfort_score = _clamp_score(score)
    class_name = _choose_class_name(tags, comfort_score)

    return {
        "bike_allowed": _build_allowed_state(tags),
        "bike_comfort": comfort_score,
        "bike_crossable_class": class_name,
        "bike_crossable_label": CLASS_LABELS[class_name],
        "confidence": _estimate_confidence(tags),
        "reasons": reasons,
        "normalized_tags": tags,
    }


def summarize_segments(scored_segments: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "total": len(scored_segments),
        "protected": 0,
        "low-stress": 0,
        "shared": 0,
        "not-suitable": 0,
    }

    for segment in scored_segments:
        summary[segment["score"]["bike_crossable_class"]] += 1

    return summary
