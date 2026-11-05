"""Pydantic schemas shared by the Trip Agent tools, state, and CLI."""

from __future__ import annotations

from datetime import date as date_type, datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MISSING_FIELD_LABELS = {
    "destination": "destination",
    "start_date": "travel start date",
    "duration_days": "trip duration",
    "activities": "activities or occasions",
    "max_luggage_weight_kg": "clothing luggage limit",
}

ACTIVITY_ALIASES = {
    "formal dinner": "formal-dinner",
    "formal-dinner": "formal-dinner",
    "dinner": "formal-dinner",
    "business meeting": "business-meeting",
    "business-meeting": "business-meeting",
    "meeting": "business-meeting",
    "night out": "night-out",
    "night-out": "night-out",
    "sight seeing": "sightseeing",
    "sightseeing": "sightseeing",
    "shopping": "shopping",
    "hiking": "hiking",
    "beach": "beach",
    "museum": "museum",
    "restaurant": "restaurant",
    "walking": "walking",
    "wedding": "wedding",
    "gala": "gala",
    "conference": "conference",
    "skiing": "skiing",
    "sport": "sport",
    "workout": "workout",
}


def normalize_activity(value: str) -> str:
    text = " ".join(str(value).strip().lower().replace("_", " ").split())
    return ACTIVITY_ALIASES.get(text, text.replace(" ", "-"))


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = normalize_activity(value)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TripDetails(BaseModel):
    """Validated trip request. Optional fields make clarification possible."""

    model_config = ConfigDict(extra="ignore")

    destination: str | None = None
    country: str | None = None
    start_date: date_type | None = None
    end_date: date_type | None = None
    duration_days: int | None = Field(default=None, ge=1, le=60)
    activities: list[str] = Field(default_factory=list)
    daily_activities: dict[int, list[str]] = Field(default_factory=dict)
    occasions: list[str] = Field(default_factory=list)
    dress_code: str | None = None
    max_luggage_weight_kg: float | None = Field(default=None, gt=0, le=50)
    max_items_target: int | None = Field(default=None, ge=1, le=100)
    allow_laundry: bool = False
    allow_outfit_repeats: bool = False
    notes: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    source_text: str | None = None

    @field_validator("destination", "country", "dress_code", "notes")
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = " ".join(str(value).split())
        return stripped or None

    @field_validator("activities", "occasions")
    @classmethod
    def _normalize_lists(cls, value: list[str]) -> list[str]:
        return _dedupe(value or [])

    @field_validator("daily_activities", mode="before")
    @classmethod
    def _normalize_daily_activities(cls, value: Any) -> dict[int, list[str]]:
        if not value:
            return {}
        result: dict[int, list[str]] = {}
        for key, activities in value.items():
            try:
                day = int(key)
            except (TypeError, ValueError):
                continue
            if isinstance(activities, str):
                activities = [activities]
            result[day] = _dedupe(list(activities or []))
        return result

    @model_validator(mode="after")
    def _normalize_dates_and_missing_fields(self) -> "TripDetails":
        if self.start_date and self.duration_days:
            derived_end = self.start_date + timedelta(days=self.duration_days - 1)
            if self.end_date is None:
                self.end_date = derived_end
        if self.end_date and self.duration_days and self.start_date is None:
            self.start_date = self.end_date - timedelta(days=self.duration_days - 1)
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                self.end_date = None
            else:
                computed = (self.end_date - self.start_date).days + 1
                if self.duration_days != computed:
                    self.duration_days = computed
        if self.start_date and self.duration_days is None and self.end_date is None:
            self.duration_days = 1

        all_activities = list(self.activities)
        for day_activities in self.daily_activities.values():
            all_activities.extend(day_activities)
        all_activities.extend(self.occasions)
        if all_activities:
            self.activities = _dedupe(all_activities)

        self.missing_fields = self.compute_missing_fields()
        return self

    def compute_missing_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.destination:
            missing.append("destination")
        if not self.start_date:
            missing.append("start_date")
        if not self.duration_days:
            missing.append("duration_days")
        if not self.activities:
            missing.append("activities")
        if not self.max_luggage_weight_kg:
            missing.append("max_luggage_weight_kg")
        return missing

    @property
    def is_complete(self) -> bool:
        return not self.compute_missing_fields()

    def clarification_question(self) -> str:
        labels = [MISSING_FIELD_LABELS[f] for f in self.missing_fields]
        if not labels:
            return ""
        if len(labels) == 1:
            wanted = labels[0]
        else:
            wanted = ", ".join(labels[:-1]) + " and " + labels[-1]
        if "travel start date" in labels:
            return (
                f"I still need the {wanted}. What are your travel dates? "
                "A start date and duration, or a full date range, is enough."
            )
        return f"I still need the {wanted}. Could you provide that?"


class WeatherDay(BaseModel):
    model_config = ConfigDict(extra="ignore")

    date: date_type | None = None
    weather: str
    temperature_c: float
    temperature_min_c: float | None = None
    temperature_max_c: float | None = None
    precipitation_mm: float = 0.0
    precipitation_probability: float | None = None
    wind_speed_kmh: float | None = None
    uv_index: float | None = None
    source: str = "open-meteo"
    synthetic: bool = False

    @property
    def needs_outerwear(self) -> bool:
        return (
            self.temperature_c <= 17
            or self.weather in {"rainy", "windy", "cold"}
            or (self.wind_speed_kmh or 0) >= 30
        )

    @property
    def needs_warm_layer(self) -> bool:
        return self.temperature_c <= 12 or (self.temperature_min_c or 99) <= 8

    @property
    def needs_rain_protection(self) -> bool:
        return self.weather == "rainy" or self.precipitation_mm >= 1.0

    @property
    def needs_sun_protection(self) -> bool:
        return (
            self.weather in {"sunny", "hot"}
            or (self.uv_index or 0) >= 6
            or (self.weather == "sunny" and self.temperature_c >= 20)
        )


class WeatherData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    destination: str
    latitude: float | None = None
    longitude: float | None = None
    days: list[WeatherDay] = Field(default_factory=list)
    source: Literal["open-meteo", "synthetic_fallback"] = "open-meteo"
    warning: str | None = None
    resolved_name: str | None = None
    resolved_country: str | None = None
    requested_country: bool = False
    geocoding_note: str | None = None
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def day_for(self, target_date: date_type, index: int) -> WeatherDay:
        for day in self.days:
            if day.date == target_date:
                return day
        if self.days:
            return self.days[min(index, len(self.days) - 1)]
        raise ValueError("Weather data contains no days")

    def summary(self) -> list[dict[str, Any]]:
        return [
            {
                "date": day.date.isoformat() if day.date else None,
                "weather": day.weather,
                "temperature_c": day.temperature_c,
                "precipitation_mm": day.precipitation_mm,
                "source": day.source,
            }
            for day in self.days
        ]


class DailyRequirement(BaseModel):
    """Exact, optimizer-compatible daily requirement fields."""

    model_config = ConfigDict(extra="ignore")

    trip_id: str = "AGENT_TRIP"
    day_number: int = Field(ge=1)
    date: date_type
    activity: str
    weather: str
    temperature_c: float
    precipitation_mm: float
    required_style: str
    needs_outerwear: bool
    needs_warm_layer: bool
    needs_rain_protection: bool
    needs_sun_protection: bool
    activities: list[str] = Field(default_factory=list)
    weather_source: str | None = None


class OutfitItem(BaseModel):
    item_id: str
    name: str
    category: str
    item_type: str | None = None
    weight_g: int
    style: str | None = None
    color: str | None = None
    image_url: str | None = None
    weight_estimated: bool = False


class CapsuleDay(BaseModel):
    day_number: int
    date: date_type
    activity: str
    activities: list[str] = Field(default_factory=list)
    weather: str
    temperature_c: float
    precipitation_mm: float
    required_style: str
    outfit_item_ids: list[str]
    outfit_items: list[OutfitItem]
    compatibility: float | None = None
    quality: int | None = None


class CapsuleTripInfo(BaseModel):
    destination: str
    country: str | None = None
    start_date: date_type
    end_date: date_type
    duration_days: int
    activities: list[str]
    dress_code: str | None = None
    max_luggage_weight_kg: float
    weather_source: str


class ChecklistItem(BaseModel):
    item_id: str
    name: str
    category: str
    item_type: str | None = None
    weight_g: int
    quantity: int = 1
    packed: bool = False
    image_url: str | None = None
    weight_estimated: bool = False

    def mark(self, packed: bool) -> "ChecklistItem":
        self.packed = packed
        return self


class PackingChecklist(BaseModel):
    items: list[ChecklistItem] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def total_items(self) -> int:
        return len(self.items)

    @property
    def packed_items(self) -> int:
        return sum(item.packed for item in self.items)

    def mark_packed(self, item_id: str, packed: bool = True) -> ChecklistItem:
        for item in self.items:
            if item.item_id == item_id:
                item.mark(packed)
                self.updated_at = datetime.now(timezone.utc)
                return item
        raise KeyError(f"Checklist item not found: {item_id}")

    def mark_all(self, packed: bool = True) -> None:
        for item in self.items:
            item.mark(packed)
        self.updated_at = datetime.now(timezone.utc)

    def summary(self) -> dict[str, Any]:
        return {
            "total_items": self.total_items,
            "packed_items": self.packed_items,
            "unpacked_items": self.total_items - self.packed_items,
            "items": [item.model_dump(mode="json") for item in self.items],
        }


class TripCapsule(BaseModel):
    trip: CapsuleTripInfo
    days: list[CapsuleDay]
    selected_items: list[OutfitItem]
    total_weight_g: int
    optimization_status: str
    number_of_items: int
    checklist: PackingChecklist = Field(default_factory=PackingChecklist)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCallRecord(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    ok: bool
    summary: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MissingItemRecommendation(BaseModel):
    key: str
    title: str
    examples: list[str]
    days: list[int]
    covers: list[str]
    note: str | None = None


class AgentState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str
    user_id: str = "local"
    user_request: str = ""
    messages: list[ConversationMessage] = Field(default_factory=list)
    trip_details: TripDetails | None = None
    weather: WeatherData | None = None
    wardrobe_items: list[dict[str, Any]] = Field(default_factory=list)
    compatibility_data: list[dict[str, Any]] = Field(default_factory=list)
    daily_requirements: list[DailyRequirement] = Field(default_factory=list)
    optimization_result: dict[str, Any] | None = None
    optimization_runs: int = 0
    capsule: TripCapsule | None = None
    checklist: PackingChecklist | None = None
    missing_info: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str | None = None
    suggestions: list[str] = Field(default_factory=list)
    missing_items: list[MissingItemRecommendation] = Field(default_factory=list)
    can_repeat_outfits: bool = False
    errors: list[str] = Field(default_factory=list)
    tool_history: list[ToolCallRecord] = Field(default_factory=list)
    status: Literal[
        "collecting_details",
        "needs_clarification",
        "ready",
        "optimizing",
        "optimized",
        "infeasible",
        "failed",
    ] = "collecting_details"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def add_user_message(self, text: str) -> None:
        self.messages.append(ConversationMessage(role="user", content=text))
        if not self.user_request:
            self.user_request = text
        self.touch()

    def add_assistant_message(self, text: str) -> None:
        self.messages.append(ConversationMessage(role="assistant", content=text))
        self.touch()

    def context_summary(self) -> dict[str, Any]:
        details = self.trip_details.model_dump(mode="json") if self.trip_details else None
        return {
            "status": self.status,
            "trip_details": details,
            "missing_info": self.missing_info,
            "needs_clarification": self.needs_clarification,
            "clarification_question": self.clarification_question,
            "weather_source": self.weather.source if self.weather else None,
            "weather_days": len(self.weather.days) if self.weather else 0,
            "daily_requirements_generated": len(self.daily_requirements),
            "optimization_status": (
                self.optimization_result.get("status")
                if self.optimization_result
                else None
            ),
            "optimization_runs": self.optimization_runs,
            "capsule_ready": self.capsule is not None,
            "checklist_items": self.checklist.total_items if self.checklist else 0,
            "suggestions": self.suggestions,
            "errors": self.errors[-5:],
            "wardrobe_loaded": len(self.wardrobe_items),
        }


class AgentResponse(BaseModel):
    message: str
    status: str
    trip_details: TripDetails | None = None
    weather_source: str | None = None
    weather_summary: list[dict[str, Any]] = Field(default_factory=list)
    daily_requirements: list[DailyRequirement] = Field(default_factory=list)
    capsule: TripCapsule | None = None
    checklist: PackingChecklist | None = None
    missing_info: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    missing_items: list[MissingItemRecommendation] = Field(default_factory=list)
    can_repeat_outfits: bool = False
    errors: list[str] = Field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
