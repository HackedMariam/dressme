"""Tool implementations used by the custom Trip Agent loop."""

from __future__ import annotations

import json
import logging
import math
import random
from datetime import timedelta
from typing import Any, Callable

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from .. import optimizer
from .config import (
    DEFAULT_MAX_CANDIDATES_PER_DAY,
    DEFAULT_OPTIMIZER_TIME_LIMIT_SECONDS,
)
from .extraction import extract_trip_details
from .llm import LLMClient
from .logging_utils import log_event
from .optimizer_adapter import (
    build_capsule,
    compact_result,
    run_optimization,
)
from .schemas import ToolCallRecord
from .requirements import (
    build_daily_requirements,
    requirement_summary,
)
from .schemas import (
    AgentState,
    TripDetails,
    normalize_activity,
)
from .wardrobe import SyntheticWardrobeProvider, WardrobeProvider
from .weather import DestinationResolutionError, fetch_weather

logger = logging.getLogger(__name__)

TRIP_UPDATE_FIELDS = {
    "destination",
    "country",
    "start_date",
    "end_date",
    "duration_days",
    "activities",
    "daily_activities",
    "occasions",
    "dress_code",
    "max_luggage_weight_kg",
    "max_items_target",
    "allow_laundry",
    "notes",
}

ROLE_SUGGESTIONS = {
    "top": "add a top, shirt, blouse, sweater, or hoodie",
    "bottom": "add trousers, jeans, a skirt, or shorts",
    "shoes": "add shoes or sneakers",
    "onepiece": "add a dress/jumpsuit, or include a top and bottom",
    "outerwear": "add a jacket, coat, cardigan, or raincoat",
    "warm": "add a warm sweater, hoodie, or fleece",
    "rain": "add a genuinely waterproof raincoat",
    "sun": "add a sun hat or sunglasses",
}


class EmptyArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")


class GetTripDetailsArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str | None = None
    structured: dict[str, Any] | None = None


class GetWeatherArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    force_refresh: bool = False
    allow_network: bool = True


class GetWardrobeArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    category: str | None = None
    style: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class OptimizeTripArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    max_weight_g: int | None = Field(default=None, gt=0, le=50000)
    max_candidates_per_day: int = Field(
        default=DEFAULT_MAX_CANDIDATES_PER_DAY, ge=10, le=5000
    )
    time_limit_seconds: int = Field(
        default=DEFAULT_OPTIMIZER_TIME_LIMIT_SECONDS, ge=1, le=120
    )
    random_seed: int = 42


class UpdateTripArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    updates: dict[str, Any]
    reoptimize: bool = False


class UpdateChecklistArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    item_id: str
    packed: bool = True


class SuggestAlternativesArgs(BaseModel):
    model_config = ConfigDict(extra="ignore")

    diagnostic_time_limit_seconds: int = Field(default=10, ge=1, le=60)


ARGS_MODELS: dict[str, type[BaseModel]] = {
    "get_trip_details": GetTripDetailsArgs,
    "get_weather": GetWeatherArgs,
    "get_wardrobe": GetWardrobeArgs,
    "get_activity_requirements": EmptyArgs,
    "optimize_trip": OptimizeTripArgs,
    "generate_checklist": EmptyArgs,
    "suggest_alternatives": SuggestAlternativesArgs,
    "update_trip": UpdateTripArgs,
    "update_checklist": UpdateChecklistArgs,
    "check_gaps": EmptyArgs,
}


def tool_specs() -> list[dict[str, Any]]:
    """Native function-calling schemas exposed to the LLM."""
    return [
        {
            "type": "function",
            "function": {
                "name": "get_trip_details",
                "description": (
                    "Extract and validate destination, dates, duration, activities, "
                    "occasions and luggage limits from the user's text, or accept a "
                    "structured object. Merges with existing state and reports missing "
                    "mandatory fields. Call this first for a new or clarified trip."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "The user's trip request or clarification.",
                        },
                        "structured": {
                            "type": "object",
                            "description": "Optional structured trip fields instead of text.",
                        },
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": (
                    "Retrieve daily weather for the validated destination and dates "
                    "using Open-Meteo. Falls back to explicitly labeled synthetic "
                    "weather when forecasts are unavailable. Requires complete dates."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "force_refresh": {"type": "boolean", "default": False},
                        "allow_network": {"type": "boolean", "default": True},
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_wardrobe",
                "description": (
                    "Retrieve the synthetic wardrobe available to the optimizer. "
                    "Optionally filter by category or style. Call at most once unless "
                    "the user asks about different items."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "style": {"type": "string"},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_activity_requirements",
                "description": (
                    "Convert trip activities, occasions, and retrieved weather into "
                    "optimizer-compatible daily requirements. Requires validated trip "
                    "details and weather."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "optimize_trip",
                "description": (
                    "Run the existing deterministic OR-Tools CP-SAT optimizer on the "
                    "generated daily requirements. Returns status, outfits, selected "
                    "items, and total clothing weight. Do not invent results."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "max_weight_g": {
                            "type": "integer",
                            "description": "Optional override; otherwise the trip limit is used.",
                        },
                        "max_candidates_per_day": {
                            "type": "integer",
                            "minimum": 10,
                            "maximum": 5000,
                        },
                        "time_limit_seconds": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 120,
                        },
                        "random_seed": {"type": "integer"},
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_checklist",
                "description": (
                    "Generate the packing checklist from the unique items selected by "
                    "a successful optimization. Every item starts with packed=false."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "suggest_alternatives",
                "description": (
                    "Analyze an INFEASIBLE optimization and propose concrete recovery "
                    "options. Never silently relax hard constraints."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "diagnostic_time_limit_seconds": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 60,
                        }
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_trip",
                "description": (
                    "Modify validated trip details and invalidate stale downstream "
                    "state. Set reoptimize=true to fetch/refresh weather, regenerate "
                    "requirements, optimize, and generate the checklist automatically."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "updates": {
                            "type": "object",
                            "description": (
                                "Fields to change, such as destination, start_date, "
                                "end_date, duration_days, activities, dress_code, or "
                                "max_luggage_weight_kg."
                            ),
                        },
                        "reoptimize": {"type": "boolean", "default": False},
                    },
                    "required": ["updates"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_checklist",
                "description": (
                    "Mark one packing checklist item as packed or unpacked. This does "
                    "not rerun the optimizer."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "item_id": {"type": "string"},
                        "packed": {"type": "boolean", "default": True},
                    },
                    "required": ["item_id"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_gaps",
                "description": (
                    "Optional interface for a future Gap Agent. Returns unavailable "
                    "unless a gap checker has been injected."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        },
    ]


class TripTools:
    """Executes tools, validates arguments, and keeps AgentState consistent."""

    def __init__(
        self,
        state: AgentState,
        llm: LLMClient | None = None,
        wardrobe_provider: WardrobeProvider | None = None,
        gap_checker: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        allow_weather_network: bool = True,
    ) -> None:
        self.state = state
        self.llm = llm
        self.wardrobe_provider = wardrobe_provider or SyntheticWardrobeProvider()
        self.gap_checker = gap_checker
        self.allow_weather_network = allow_weather_network

    # ------------------------------------------------------------------
    # Dispatcher / validation
    # ------------------------------------------------------------------
    def execute(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        arguments = arguments or {}
        if "_invalid_json" in arguments or "_invalid_arguments" in arguments:
            result = {
                "ok": False,
                "error": "Tool arguments were not a valid JSON object.",
            }
            self._record(name, arguments, result)
            return result

        model = ARGS_MODELS.get(name)
        if model is None:
            result = {"ok": False, "error": f"Unknown tool: {name}"}
            self._record(name, arguments, result)
            return result

        try:
            validated = model.model_validate(arguments)
            result = self._dispatch(name, validated)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            log_event(logger, "tool_failed", tool=name, error=error, level=logging.ERROR)
            self.state.errors.append(f"{name}: {error}")
            result = {"ok": False, "tool": name, "error": error}

        self._record(name, arguments, result)
        self.state.touch()
        return result

    def _dispatch(self, name: str, args: BaseModel) -> dict[str, Any]:
        handlers = {
            "get_trip_details": self._get_trip_details,
            "get_weather": self._get_weather,
            "get_wardrobe": self._get_wardrobe,
            "get_activity_requirements": self._get_activity_requirements,
            "optimize_trip": self._optimize_trip,
            "generate_checklist": self._generate_checklist,
            "suggest_alternatives": self._suggest_alternatives,
            "update_trip": self._update_trip,
            "update_checklist": self._update_checklist,
            "check_gaps": self._check_gaps,
        }
        handler = handlers[name]
        result = handler(args)
        result.setdefault("ok", True)
        result.setdefault("tool", name)
        log_event(
            logger,
            "tool_executed",
            tool=name,
            ok=result.get("ok"),
            status=self.state.status,
        )
        return result

    def _record(
        self,
        name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        summary = json.dumps(result, default=str, ensure_ascii=False)[:500]
        self.state.tool_history.append(
            ToolCallRecord(
                name=name,
                arguments=arguments,
                ok=bool(result.get("ok")),
                summary=summary,
            )
        )

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------
    def _load_wardrobe(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        wardrobe, compatibility = self.wardrobe_provider.load()
        if not self.state.wardrobe_items:
            self.state.wardrobe_items = json.loads(
                wardrobe.to_json(orient="records")
            )
            self.state.compatibility_data = json.loads(
                compatibility.to_json(orient="records")
            )
        return wardrobe, compatibility

    def _latest_user_text(self) -> str:
        for message in reversed(self.state.messages):
            if message.role == "user":
                return message.content
        return self.state.user_request

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------
    def _get_trip_details(self, args: GetTripDetailsArgs) -> dict[str, Any]:
        meta: dict[str, Any]
        if args.structured:
            existing = (
                self.state.trip_details.model_dump(mode="json")
                if self.state.trip_details
                else {}
            )
            payload = {**existing, **args.structured}
            details = TripDetails.model_validate(payload)
            meta = {"extractor": "structured_input", "warning": None}
        else:
            text = args.text or self._latest_user_text() or self.state.user_request
            details, meta = extract_trip_details(
                text=text,
                existing=self.state.trip_details,
                llm=self.llm,
            )

        old_details = self.state.trip_details
        critical_fields = (
            "destination",
            "country",
            "start_date",
            "end_date",
            "duration_days",
            "activities",
            "daily_activities",
            "occasions",
            "dress_code",
            "max_luggage_weight_kg",
        )
        details_changed = old_details is None or any(
            old_details.model_dump(mode="json").get(field)
            != details.model_dump(mode="json").get(field)
            for field in critical_fields
        )

        self.state.trip_details = details
        self.state.missing_info = details.compute_missing_fields()
        self.state.needs_clarification = bool(self.state.missing_info)

        if details_changed:
            # New or corrected details invalidate everything downstream.
            self.state.weather = None
            self.state.daily_requirements = []
            self.state.optimization_result = None
            self.state.capsule = None
            self.state.checklist = None
            self.state.suggestions = []

        if self.state.needs_clarification:
            self.state.status = "needs_clarification"
            question = details.clarification_question()
            self.state.clarification_question = question
            return {
                "ok": True,
                "trip_details": details.model_dump(mode="json"),
                "missing_fields": self.state.missing_info,
                "needs_clarification": True,
                "question": question,
                "extractor": meta.get("extractor"),
                "warning": meta.get("warning"),
                "next_action": "ask_user",
            }

        self.state.clarification_question = None
        if details_changed or self.state.status in {
            "collecting_details",
            "needs_clarification",
        }:
            self.state.status = "ready"
        return {
            "ok": True,
            "trip_details": details.model_dump(mode="json"),
            "missing_fields": [],
            "needs_clarification": False,
            "extractor": meta.get("extractor"),
            "warning": meta.get("warning"),
            "next_action": "get_weather",
        }

    def _get_weather(self, args: GetWeatherArgs) -> dict[str, Any]:
        details = self.state.trip_details
        if details is None:
            return {"ok": False, "error": "Trip details are not available yet."}
        if details.start_date is None:
            return {
                "ok": False,
                "error": "Travel start date is required for weather retrieval.",
                "missing_fields": details.compute_missing_fields(),
            }

        end = details.end_date
        if end is None and details.duration_days:
            end = details.start_date + timedelta(days=details.duration_days - 1)
        if end is None:
            return {
                "ok": False,
                "error": "Travel end date or duration is required for weather retrieval.",
            }
        destination = details.destination or "Unknown destination"

        cached = self.state.weather
        if (
            cached
            and not args.force_refresh
            and cached.destination == destination
            and cached.days
            and cached.days[0].date == details.start_date
            and cached.days[-1].date == end
        ):
            return {
                "ok": True,
                "cached": True,
                "source": cached.source,
                "warning": cached.warning,
                "days": cached.summary(),
                "next_action": "get_activity_requirements",
            }

        try:
            weather = fetch_weather(
                destination=destination,
                start=details.start_date,
                end=end,
                allow_network=args.allow_network and self.allow_weather_network,
            )
        except DestinationResolutionError as exc:
            # Do not keep planning against a fictional or ambiguous place.
            self.state.trip_details = TripDetails.model_validate(
                {
                    **details.model_dump(mode="json"),
                    "destination": None,
                }
            )
            self.state.weather = None
            self.state.daily_requirements = []
            self.state.optimization_result = None
            self.state.capsule = None
            self.state.checklist = None
            self.state.suggestions = []
            self.state.missing_info = self.state.trip_details.compute_missing_fields()
            self.state.needs_clarification = True
            self.state.status = "needs_clarification"
            self.state.errors.append(str(exc))
            question = (
                f"I couldn't verify '{destination}' as a real city or country. "
                "What destination should I use? You can also include the country, "
                "for example 'Atlantis, South Africa'."
            )
            self.state.clarification_question = question
            return {
                "ok": False,
                "error": str(exc),
                "destination_unresolved": True,
                "needs_clarification": True,
                "question": question,
                "missing_fields": self.state.missing_info,
                "next_action": "ask_user",
            }

        self.state.weather = weather
        self.state.daily_requirements = []
        self.state.optimization_result = None
        self.state.capsule = None
        self.state.checklist = None
        self.state.suggestions = []
        self.state.needs_clarification = False
        self.state.clarification_question = None
        self.state.status = "ready"

        return {
            "ok": True,
            "cached": False,
            "source": weather.source,
            "synthetic": weather.source == "synthetic_fallback",
            "warning": weather.warning,
            "days": weather.summary(),
            "next_action": "get_activity_requirements",
        }

    def _get_wardrobe(self, args: GetWardrobeArgs) -> dict[str, Any]:
        was_loaded = bool(self.state.wardrobe_items)
        self._load_wardrobe()
        payload = self.wardrobe_provider.items_payload(
            category=args.category,
            style=args.style,
            limit=args.limit,
        )
        return {
            "ok": True,
            "cached": was_loaded,
            **payload,
            "next_action": "get_activity_requirements",
        }

    def _get_activity_requirements(self, _args: EmptyArgs) -> dict[str, Any]:
        details = self.state.trip_details
        if details is None:
            return {"ok": False, "error": "Trip details are required."}
        if details.compute_missing_fields():
            return {
                "ok": False,
                "error": "Trip details are incomplete.",
                "missing_fields": details.compute_missing_fields(),
            }
        if self.state.weather is None:
            return {
                "ok": False,
                "error": "Weather is required before generating requirements.",
                "dependency_missing": "get_weather",
            }

        requirements = build_daily_requirements(details, self.state.weather)
        self.state.daily_requirements = requirements
        self.state.optimization_result = None
        self.state.capsule = None
        self.state.checklist = None
        self.state.suggestions = []
        self.state.status = "ready"

        return {
            "ok": True,
            "requirements": requirement_summary(requirements),
            "optimizer_fields": [
                requirement.model_dump(mode="json") for requirement in requirements
            ],
            "next_action": "optimize_trip",
        }

    def _optimize_trip(self, args: OptimizeTripArgs) -> dict[str, Any]:
        details = self.state.trip_details
        if details is None or not details.is_complete:
            return {"ok": False, "error": "Complete trip details are required."}
        if not self.state.daily_requirements:
            return {
                "ok": False,
                "error": "Daily requirements are required before optimization.",
                "dependency_missing": "get_activity_requirements",
            }

        weight_g = args.max_weight_g
        if weight_g is None:
            weight_g = int(round(float(details.max_luggage_weight_kg or 0) * 1000))
        if weight_g <= 0:
            return {"ok": False, "error": "A positive luggage weight limit is required."}

        if args.max_weight_g is not None:
            updated = TripDetails.model_validate(
                {
                    **details.model_dump(mode="json"),
                    "max_luggage_weight_kg": weight_g / 1000.0,
                }
            )
            self.state.trip_details = updated
            details = updated

        wardrobe, compatibility = self._load_wardrobe()
        self.state.optimization_result = None
        self.state.capsule = None
        self.state.checklist = None
        self.state.suggestions = []
        self.state.status = "optimizing"

        result = run_optimization(
            wardrobe=wardrobe,
            compatibility=compatibility,
            requirements=self.state.daily_requirements,
            max_weight_g=weight_g,
            max_candidates_per_day=args.max_candidates_per_day,
            time_limit_seconds=args.time_limit_seconds,
            random_seed=args.random_seed,
        )
        self.state.optimization_result = compact_result(result)
        self.state.optimization_runs += 1

        if result.get("status") in {"OPTIMAL", "FEASIBLE"}:
            capsule = build_capsule(
                trip=details,
                weather=self.state.weather,
                requirements=self.state.daily_requirements,
                wardrobe=wardrobe,
                result=result,
            )
            capsule.metadata["optimizer_time_limit_seconds"] = args.time_limit_seconds
            self.state.capsule = capsule
            # The checklist is activated by generate_checklist; the capsule
            # already carries the deterministic item list for that tool.
            self.state.checklist = None
            self.state.status = "optimized"
            return {
                "ok": True,
                "status": result.get("status"),
                "weight_limit_g": weight_g,
                "total_weight_g": result.get("total_weight_g"),
                "number_of_items": result.get("number_of_items"),
                "number_of_outfits": result.get("number_of_outfits"),
                "daily_outfits": self.state.optimization_result["daily_outfits"],
                "selected_items": self.state.optimization_result["selected_items"],
                "capsule_ready": True,
                "next_action": "generate_checklist",
            }

        self.state.status = "infeasible"
        return {
            "ok": True,
            "status": result.get("status"),
            "reason": result.get("reason")
            or "No packing solution satisfies all hard constraints.",
            "weight_limit_g": weight_g,
            "total_weight_g": result.get("total_weight_g"),
            "number_of_items": result.get("number_of_items"),
            "capsule_ready": False,
            "next_action": "suggest_alternatives",
        }

    def _generate_checklist(self, _args: EmptyArgs) -> dict[str, Any]:
        capsule = self.state.capsule
        if capsule is None:
            return {
                "ok": False,
                "error": "A successful optimization/capsule is required first.",
                "dependency_missing": "optimize_trip",
            }

        if self.state.checklist is None:
            self.state.checklist = capsule.checklist
        capsule.checklist = self.state.checklist
        self.state.status = "optimized"
        return {
            "ok": True,
            "checklist": self.state.checklist.summary(),
            "total_weight_g": capsule.total_weight_g,
            "next_action": "done",
        }

    def _suggest_alternatives(self, args: SuggestAlternativesArgs) -> dict[str, Any]:
        details = self.state.trip_details
        requirements = self.state.daily_requirements
        if details is None or not requirements:
            return {
                "ok": False,
                "error": "Requirements and an infeasible optimization are needed first.",
            }

        wardrobe, compatibility = self._load_wardrobe()
        item_roles = optimizer.build_item_roles(wardrobe)
        role_pools: dict[str, list[str]] = {role: [] for role in optimizer.ROLES}
        for item_id, roles in item_roles.items():
            for role in roles:
                role_pools.setdefault(role, []).append(item_id)

        suggestions: list[str] = []
        missing_role_days: dict[str, list[int]] = {}
        no_candidate_days: list[int] = []
        compatibility_map = optimizer.build_compatibility_map(compatibility)
        rng = random.Random(42)

        for requirement in requirements:
            trip_row = requirement.model_dump(mode="python")
            required_roles = optimizer.required_roles_for_day(trip_row)
            for role in sorted(required_roles):
                if not role_pools.get(role):
                    missing_role_days.setdefault(role, []).append(requirement.day_number)

            candidates = optimizer.generate_outfits(
                wardrobe,
                pd.Series(trip_row),
                compatibility_map,
                item_roles,
                max_candidates=50,
                rng=rng,
            )
            if not candidates:
                no_candidate_days.append(requirement.day_number)

        for role, days in sorted(missing_role_days.items()):
            suggestion = ROLE_SUGGESTIONS.get(role, f"add an item for the '{role}' role")
            suggestions.append(
                f"Day(s) {sorted(set(days))} require the '{role}' role, but the "
                f"synthetic wardrobe has no item for it. To keep all hard constraints, "
                f"{suggestion} in the wardrobe, or choose different dates/activities."
            )

        if no_candidate_days:
            suggestions.append(
                "No outfit can satisfy every hard activity/style/weather constraint on "
                f"day(s) {sorted(set(no_candidate_days))}. Consider changing those "
                "activities, dress code, or dates; the agent will not relax the "
                "constraints silently."
            )

        current_weight_g = None
        if self.state.optimization_result:
            current_weight_g = int(
                round(float(details.max_luggage_weight_kg or 0) * 1000)
            )
        result_status = (
            self.state.optimization_result.get("status")
            if self.state.optimization_result
            else None
        )

        suggested_weight_kg = None
        if result_status == "INFEASIBLE" and not missing_role_days and not no_candidate_days:
            total_wardrobe_weight = int(wardrobe["weight_g"].sum())
            diagnostic_limit = max(
                total_wardrobe_weight,
                current_weight_g or 0,
                sum(int(row["weight_g"]) for _, row in wardrobe.iterrows()),
            )
            try:
                diagnostic = run_optimization(
                    wardrobe=wardrobe,
                    compatibility=compatibility,
                    requirements=requirements,
                    max_weight_g=diagnostic_limit,
                    max_candidates_per_day=200,
                    time_limit_seconds=args.diagnostic_time_limit_seconds,
                    random_seed=42,
                )
                if diagnostic.get("status") in {"OPTIMAL", "FEASIBLE"}:
                    needed_g = int(diagnostic.get("total_weight_g") or 0)
                    suggested_weight_kg = math.ceil(needed_g / 500.0) / 2.0
                    if current_weight_g and needed_g > current_weight_g:
                        suggestions.append(
                            "The current clothing limit is the blocking constraint. A "
                            f"diagnostic run with the same hard constraints packed "
                            f"{needed_g / 1000:.2f} kg. Consider explicitly raising the "
                            f"limit to at least {suggested_weight_kg:.1f} kg, or allow "
                            "laundry / remove an activity."
                        )
                    else:
                        suggestions.append(
                            "The solver can find a packing solution under the same hard "
                            "constraints with more capacity; the current weight limit is "
                            "the likely blocker."
                        )
                elif diagnostic.get("status") == "INFEASIBLE":
                    suggestions.append(
                        "The optimizer is still infeasible even with a large weight "
                        "limit, so the blocking issue is not luggage capacity."
                    )
                else:
                    suggestions.append(
                        "The weight diagnostic did not finish within its time limit, "
                        "so it could not confirm whether luggage capacity is the "
                        "blocking constraint. The constraints were not relaxed."
                    )
            except Exception as exc:
                suggestions.append(
                    f"Weight diagnostics failed ({type(exc).__name__}); inspect the "
                    "daily hard constraints instead."
                )

        if self.state.weather and self.state.weather.source == "synthetic_fallback":
            suggestions.append(
                "Weather currently comes from an explicitly labeled synthetic fallback. "
                "If you can choose dates inside the Open-Meteo forecast window, refresh "
                "the weather to plan against a real forecast."
            )

        if not suggestions:
            suggestions.append(
                "No single obvious blocker was found. Review the daily requirements and "
                "consider changing activity, dress code, or dates; hard constraints were "
                "not relaxed."
            )

        self.state.suggestions = suggestions
        return {
            "ok": True,
            "status": result_status,
            "suggestions": suggestions,
            "suggested_weight_limit_kg": suggested_weight_kg,
            "hard_constraints_relaxed": False,
            "missing_roles_by_day": {
                role: sorted(set(days)) for role, days in missing_role_days.items()
            },
            "no_candidate_days": sorted(set(no_candidate_days)),
        }

    def _update_trip(self, args: UpdateTripArgs) -> dict[str, Any]:
        if self.state.trip_details is None:
            return {"ok": False, "error": "There is no trip to update yet."}

        unknown = set(args.updates) - TRIP_UPDATE_FIELDS
        if unknown:
            return {
                "ok": False,
                "error": f"Unknown trip fields: {sorted(unknown)}",
            }

        old = self.state.trip_details
        payload = old.model_dump(mode="json")
        payload.update(args.updates)

        if "activities" in args.updates:
            new_activity_set = {
                normalize_activity(activity)
                for activity in args.updates.get("activities") or []
            }
            if "occasions" not in args.updates:
                payload["occasions"] = [
                    occasion
                    for occasion in (old.occasions or [])
                    if occasion in new_activity_set
                ]
            if "daily_activities" not in args.updates:
                payload["daily_activities"] = {}

        # A duration-only or start-date-only change must not keep a stale end date.
        if "duration_days" in args.updates and "end_date" not in args.updates:
            payload["end_date"] = None
        if (
            "start_date" in args.updates
            and "duration_days" in args.updates
            and "end_date" not in args.updates
        ):
            payload["end_date"] = None
        if "start_date" in args.updates and "end_date" not in args.updates:
            if payload.get("duration_days"):
                payload["end_date"] = None

        new_details = TripDetails.model_validate(payload)
        self.state.trip_details = new_details
        self.state.missing_info = new_details.compute_missing_fields()
        self.state.needs_clarification = bool(self.state.missing_info)
        self.state.clarification_question = (
            new_details.clarification_question()
            if self.state.needs_clarification
            else None
        )

        detail_fields = {
            "destination",
            "start_date",
            "end_date",
            "duration_days",
            "activities",
            "daily_activities",
            "occasions",
            "dress_code",
        }
        changed = {
            key
            for key, value in args.updates.items()
            if old.model_dump(mode="json").get(key) != new_details.model_dump(mode="json").get(key)
        }

        if changed & {"destination", "start_date", "end_date", "duration_days"}:
            self.state.weather = None
        if changed & detail_fields:
            self.state.daily_requirements = []
        self.state.optimization_result = None
        self.state.capsule = None
        self.state.checklist = None
        self.state.suggestions = []
        self.state.status = (
            "needs_clarification" if self.state.needs_clarification else "ready"
        )

        response: dict[str, Any] = {
            "ok": True,
            "trip_details": new_details.model_dump(mode="json"),
            "changed_fields": sorted(changed),
            "missing_fields": self.state.missing_info,
            "needs_clarification": self.state.needs_clarification,
            "reoptimized": False,
        }

        if self.state.needs_clarification:
            response["question"] = new_details.clarification_question()
            response["next_action"] = "ask_user"
            return response

        if not args.reoptimize:
            if self.state.weather is None:
                next_action = "get_weather"
            elif not self.state.daily_requirements:
                next_action = "get_activity_requirements"
            else:
                next_action = "optimize_trip"
            response["next_action"] = next_action
            return response

        if self.state.weather is None:
            weather_result = self._get_weather(GetWeatherArgs())
            if not weather_result.get("ok"):
                response["error"] = weather_result.get("error")
                response["next_action"] = "get_weather"
                return response
        if not self.state.daily_requirements:
            requirements_result = self._get_activity_requirements(EmptyArgs())
            if not requirements_result.get("ok"):
                response["error"] = requirements_result.get("error")
                response["next_action"] = "get_activity_requirements"
                return response

        optimization = self._optimize_trip(OptimizeTripArgs())
        response["reoptimized"] = True
        response["optimization"] = optimization
        if optimization.get("status") in {"OPTIMAL", "FEASIBLE"}:
            checklist = self._generate_checklist(EmptyArgs())
            response["checklist"] = checklist.get("checklist")
            response["next_action"] = "done"
        else:
            alternatives = self._suggest_alternatives(SuggestAlternativesArgs())
            response["suggestions"] = alternatives.get("suggestions", [])
            response["next_action"] = "ask_user"
        return response

    def _update_checklist(self, args: UpdateChecklistArgs) -> dict[str, Any]:
        if self.state.checklist is None:
            return {"ok": False, "error": "No checklist exists yet."}
        try:
            item = self.state.checklist.mark_packed(args.item_id, args.packed)
        except KeyError as exc:
            return {"ok": False, "error": str(exc)}
        if self.state.capsule is not None:
            self.state.capsule.checklist = self.state.checklist
        return {
            "ok": True,
            "item": item.model_dump(mode="json"),
            "checklist": self.state.checklist.summary(),
            "optimizer_rerun": False,
            "next_action": "done",
        }

    def _check_gaps(self, _args: EmptyArgs) -> dict[str, Any]:
        if self.state.capsule is None:
            return {
                "ok": False,
                "error": "A trip capsule is required before checking wardrobe gaps.",
            }
        if self.gap_checker is None:
            return {
                "ok": True,
                "available": False,
                "integration": "GapAgent",
                "message": (
                    "Gap Agent is not configured. Inject a callable gap_checker into "
                    "TripAgent to enable this interface."
                ),
                "capsule_contract": {
                    "selected_item_ids": [
                        item.item_id for item in self.state.capsule.selected_items
                    ],
                    "activities": self.state.capsule.trip.activities,
                    "days": len(self.state.capsule.days),
                },
            }
        try:
            findings = self.gap_checker(self.state.capsule.model_dump(mode="json"))
            return {"ok": True, "available": True, "findings": findings}
        except Exception as exc:
            return {
                "ok": False,
                "error": f"Gap Agent failed: {type(exc).__name__}: {exc}",
            }
