"""Trip-detail extraction with LLM structured output plus a safe fallback."""

from __future__ import annotations

import calendar
import json
import logging
import re
from datetime import date
from typing import Any

from .llm import LLMClient
from .logging_utils import log_event
from .schemas import TripDetails, normalize_activity

logger = logging.getLogger(__name__)

MONTHS = {
    name.lower(): index
    for index, name in enumerate(calendar.month_name)
    if name
}
MONTHS.update(
    {
        name.lower(): index
        for index, name in enumerate(calendar.month_abbr)
        if name
    }
)

WORD_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}

ACTIVITY_PATTERNS: list[tuple[str, str]] = [
    (r"\bformal\s+dinner\b|\bdinner\b", "formal-dinner"),
    (r"\bbusiness\s+meeting\b|\bconference\s+meeting\b", "business-meeting"),
    (r"\bnight\s*out\b|\bnightlife\b", "night-out"),
    (r"\bsight\s*seeing\b|\bsightseeing\b|\btourist(?:ing)?\b", "sightseeing"),
    (r"\bshopping\b", "shopping"),
    (r"\bhiking\b|\btrekking\b", "hiking"),
    (r"\bbeach\b", "beach"),
    (r"\bmuseum\b|\bgallery\b", "museum"),
    (r"\brestaurant\b|\bdining\b", "restaurant"),
    (r"\bwalking\b", "walking"),
    (r"\bwedding\b", "wedding"),
    (r"\bgala\b", "gala"),
    (r"\bconference\b", "conference"),
    (r"\bski(?:ing)?\b", "skiing"),
    (r"\bworkout\b|\bgym\b", "workout"),
]

OCCASION_ACTIVITIES = {"formal-dinner", "wedding", "gala", "business-meeting"}

TRIP_EXTRACTION_SYSTEM = """
You extract structured trip details for a packing optimizer.

Return exactly one JSON object. Never guess or invent missing data. If a value is
not stated, use null (or an empty list). Existing values may only be changed when
the user explicitly corrects them.

JSON fields:
- destination: string|null
- country: string|null
- start_date: YYYY-MM-DD|null
- end_date: YYYY-MM-DD|null
- duration_days: integer|null
- activities: array of short activity labels (e.g. sightseeing, shopping,
  formal-dinner, business-meeting, hiking, beach, museum, night-out)
- daily_activities: object mapping day number strings to arrays of activity labels
- occasions: array of formal occasions (e.g. wedding, gala, formal-dinner)
- dress_code: "casual"|"smart-casual"|"formal"|"sporty"|null
- max_luggage_weight_kg: number|null
- max_items_target: integer|null
- allow_laundry: boolean
- notes: string|null
- assumptions: array of strings for harmless interpretations only

Do not put a missing value in assumptions. Do not invent weather.
""".strip()


def _coerce_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    return float(match.group()) if match else None


def _coerce_int(value: Any) -> int | None:
    number = _coerce_number(value)
    return int(number) if number is not None else None


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload or {})
    data.pop("missing_fields", None)
    if "duration_days" in data:
        data["duration_days"] = _coerce_int(data["duration_days"])
    if "max_luggage_weight_kg" in data:
        data["max_luggage_weight_kg"] = _coerce_number(
            data["max_luggage_weight_kg"]
        )
    if "max_items_target" in data:
        data["max_items_target"] = _coerce_int(data["max_items_target"])
    for key in ("start_date", "end_date"):
        value = data.get(key)
        if isinstance(value, str) and value.strip().lower() in {"", "null", "none"}:
            data[key] = None
    if data.get("destination") == "":
        data["destination"] = None
    return data


def _date_range_from_text(text: str) -> tuple[date | None, date | None]:
    lowered = text.lower()

    # ISO range: 2027-06-03 to 2027-06-07
    iso_dates = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", lowered)
    if len(iso_dates) >= 2:
        try:
            return date.fromisoformat(iso_dates[0]), date.fromisoformat(iso_dates[1])
        except ValueError:
            pass
    if len(iso_dates) == 1:
        try:
            return date.fromisoformat(iso_dates[0]), None
        except ValueError:
            pass

    month_names = "|".join(sorted(MONTHS, key=len, reverse=True))

    # June 3-7, 2027
    match = re.search(
        rf"\b({month_names})\s+(\d{{1,2}})(?:st|nd|rd|th)?\s*"
        rf"(?:-|to|through|until)\s*(\d{{1,2}})(?:st|nd|rd|th)?,?\s*(\d{{4}})",
        lowered,
    )
    if match:
        month = MONTHS[match.group(1)]
        year = int(match.group(4))
        try:
            return date(year, month, int(match.group(2))), date(year, month, int(match.group(3)))
        except ValueError:
            pass

    # June 3 to June 7, 2027  /  June 3, 2027 to June 7, 2027
    match = re.search(
        rf"\b({month_names})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s*(\d{{4}}))?\s*"
        rf"(?:-|to|through|until)\s*"
        rf"({month_names})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s*(\d{{4}}))?",
        lowered,
    )
    if match:
        start_year = int(match.group(3) or match.group(6) or date.today().year)
        end_year = int(match.group(6) or match.group(3) or date.today().year)
        try:
            return (
                date(start_year, MONTHS[match.group(1)], int(match.group(2))),
                date(end_year, MONTHS[match.group(4)], int(match.group(5))),
            )
        except ValueError:
            pass

    # 3 June to 7 June 2027
    match = re.search(
        rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_names})\s*(\d{{4}})?\s*"
        rf"(?:-|to|through|until)\s*"
        rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_names})\s*(\d{{4}})?",
        lowered,
    )
    if match:
        year = int(match.group(3) or match.group(6) or date.today().year)
        try:
            return (
                date(year, MONTHS[match.group(2)], int(match.group(1))),
                date(year, MONTHS[match.group(5)], int(match.group(4))),
            )
        except ValueError:
            pass

    # Single date: "on June 3, 2027"
    match = re.search(
        rf"\b({month_names})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s*(\d{{4}})\b",
        lowered,
    )
    if match:
        try:
            return date(
                int(match.group(3)),
                MONTHS[match.group(1)],
                int(match.group(2)),
            ), None
        except ValueError:
            pass

    return None, None


def _destination_from_text(text: str) -> str | None:
    month_names = "|".join(sorted(MONTHS, key=len, reverse=True))
    patterns = [
        r"\b(?:going|traveling|travelling|heading|flying|fly)\s+to\s+"
        r"([A-Z][A-Za-zÀ-ÿ'\-]+(?:\s+[A-Z][A-Za-zÀ-ÿ'\-]+)?)",
        r"\b(?:trip|vacation|holiday|visit)\s+(?:to|in)\s+"
        r"([A-Z][A-Za-zÀ-ÿ'\-]+(?:\s+[A-Z][A-Za-zÀ-ÿ'\-]+)?)",
        r"\b([A-Z][A-Za-zÀ-ÿ'\-]+(?:\s+[A-Z][A-Za-zÀ-ÿ'\-]+)?)\s+trip\b",
        r"\b(?:in|at)\s+([A-Z][A-Za-zÀ-ÿ'\-]+(?:\s+[A-Z][A-Za-zÀ-ÿ'\-]+)?)\b",
        r"\bto\s+([A-Z][A-Za-zÀ-ÿ'\-]+(?:\s+[A-Z][A-Za-zÀ-ÿ'\-]+)?)\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            candidate = match.group(1).strip()
            if re.fullmatch(month_names, candidate.lower()):
                continue
            if candidate.lower() in {"for", "and", "the", "my", "a", "an"}:
                continue
            return candidate
    return None


def parse_trip_text(text: str) -> dict[str, Any]:
    """Deterministic fallback extractor used when the LLM is unavailable."""
    lowered = text.lower()
    data: dict[str, Any] = {}

    destination = _destination_from_text(text)
    if destination:
        data["destination"] = destination

    start, end = _date_range_from_text(text)
    if start:
        data["start_date"] = start.isoformat()
    if end:
        data["end_date"] = end.isoformat()

    duration_match = re.search(
        r"\b(\d+|" + "|".join(WORD_NUMBERS) + r")\s*[- ]?\s*(day|days|night|nights)\b",
        lowered,
    )
    if duration_match:
        raw = duration_match.group(1)
        data["duration_days"] = int(raw) if raw.isdigit() else WORD_NUMBERS[raw]

    activity_matches: list[tuple[int, str]] = []
    for pattern, activity in ACTIVITY_PATTERNS:
        match = re.search(pattern, lowered)
        if match:
            activity_matches.append((match.start(), activity))
    activity_matches.sort(key=lambda item: item[0])

    activities: list[str] = []
    occasions: list[str] = []
    for _, activity in activity_matches:
        normalized = normalize_activity(activity)
        if normalized not in activities:
            activities.append(normalized)
        if activity in OCCASION_ACTIVITIES and normalized not in occasions:
            occasions.append(normalized)
    if activities:
        data["activities"] = activities
    if occasions:
        data["occasions"] = occasions

    dress_match = re.search(
        r"\b(?:dress\s*code|attire)\s*(?:is|:)?\s*"
        r"(casual|smart[\s-]?casual|formal|sporty)\b",
        lowered,
    )
    if dress_match:
        data["dress_code"] = dress_match.group(1).replace(" ", "-")

    kg_match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:kg|kilos?|kilograms?)\b",
        lowered,
    )
    lb_match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:lb|lbs|pounds?)\b",
        lowered,
    )
    if kg_match:
        data["max_luggage_weight_kg"] = float(kg_match.group(1))
    elif lb_match:
        data["max_luggage_weight_kg"] = round(float(lb_match.group(1)) / 2.20462, 2)

    if re.search(r"\ballow(?:ed)?\s+laundry\b|\bcan\s+do\s+laundry\b|\bwith\s+laundry\b", lowered):
        data["allow_laundry"] = True
    if re.search(r"\bno\s+laundry\b|\bwithout\s+laundry\b", lowered):
        data["allow_laundry"] = False

    data["source_text"] = text.strip()
    return data


def _merge_payload(
    existing: TripDetails | None,
    incoming: dict[str, Any],
    parsed: dict[str, Any],
) -> dict[str, Any]:
    merged: dict[str, Any] = existing.model_dump(mode="json") if existing else {}
    merged.pop("missing_fields", None)

    # A duration/start correction without a new end date must invalidate the old
    # end date so the model can derive the correct range.
    new_duration = incoming.get("duration_days") or parsed.get("duration_days")
    new_start = incoming.get("start_date") or parsed.get("start_date")
    new_end = incoming.get("end_date") or parsed.get("end_date")
    if (new_duration or new_start) and not new_end:
        merged["end_date"] = None

    for source in (incoming, parsed):
        for key, value in source.items():
            if value is None:
                continue
            if key in {"activities", "occasions", "daily_activities"} and not value:
                continue
            if key == "assumptions" and not value:
                continue
            merged[key] = value
    return merged


def extract_trip_details(
    text: str,
    existing: TripDetails | None = None,
    llm: LLMClient | None = None,
) -> tuple[TripDetails, dict[str, Any]]:
    """Extract and validate trip details, merging into existing state."""
    incoming: dict[str, Any] = {}
    meta: dict[str, Any] = {"extractor": "fallback_regex", "warning": None}

    if llm is not None and llm.available:
        existing_json = (
            json.dumps(existing.model_dump(mode="json"), ensure_ascii=False)
            if existing
            else "null"
        )
        prompt = (
            f"Existing trip details (JSON): {existing_json}\n\n"
            f"User message: {text}\n\n"
            "Return the complete merged JSON object. Keep existing values unless "
            "the user corrects them. Do not invent missing values."
        )
        try:
            incoming = _sanitize_payload(
                llm.extract_json(TRIP_EXTRACTION_SYSTEM, prompt)
            )
            meta = {"extractor": "llm_structured_output", "warning": None}
        except Exception as exc:
            meta["warning"] = f"LLM extraction unavailable; used fallback parser: {exc}"
            log_event(logger, "trip_extraction_fallback", error=str(exc))
            incoming = {}

    parsed = parse_trip_text(text)
    payload = _merge_payload(existing, incoming, parsed)

    try:
        details = TripDetails.model_validate(payload)
    except Exception as exc:
        log_event(logger, "trip_validation_failed", error=str(exc))
        details = TripDetails(
            source_text=text,
            assumptions=[f"Some extracted values were discarded: {exc}"],
        )
        meta["warning"] = f"Trip details failed validation: {exc}"

    if not details.source_text:
        details.source_text = text.strip()
    return details, meta
