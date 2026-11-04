"""Offline end-to-end tests for the DressMe Trip Agent."""

from __future__ import annotations

import json
from datetime import date

import pytest

from packing_backend.trip_agent import TripAgent
from packing_backend.trip_agent.extraction import parse_trip_text
from packing_backend.trip_agent.llm import AssistantTurn, ToolCall
from packing_backend.trip_agent.schemas import TripDetails
from packing_backend.trip_agent.weather import fetch_weather

SAMPLE_REQUEST = (
    "I'm going to Paris for 5 days for sightseeing, shopping, and a formal "
    "dinner. My clothing luggage limit is 8 kg."
)
CLARIFICATION = "June 3-7, 2027"


def make_agent() -> TripAgent:
    return TripAgent(use_llm=False, allow_weather_network=False)


def planned_agent() -> TripAgent:
    agent = make_agent()
    first = agent.handle(SAMPLE_REQUEST)
    assert first.status == "needs_clarification"
    response = agent.handle(CLARIFICATION)
    assert response.status in {"optimized", "infeasible"}
    return agent


def test_free_text_extraction_and_missing_dates() -> None:
    agent = make_agent()
    response = agent.handle(SAMPLE_REQUEST)

    assert response.status == "needs_clarification"
    assert "start_date" in response.missing_info
    assert "date" in response.message.lower()
    assert response.trip_details is not None
    assert response.trip_details.destination == "Paris"
    assert response.trip_details.duration_days == 5
    assert response.trip_details.max_luggage_weight_kg == 8
    assert "formal-dinner" in response.trip_details.activities
    assert response.capsule is None

    # Clarification is merged into existing state, not re-parsed from scratch.
    resumed = agent.handle(CLARIFICATION)
    assert resumed.trip_details is not None
    assert resumed.trip_details.start_date == date(2027, 6, 3)
    assert resumed.trip_details.end_date == date(2027, 6, 7)
    assert resumed.missing_info == []
    assert resumed.status in {"optimized", "infeasible"}


def test_dynamic_requirements_match_optimizer_contract() -> None:
    agent = planned_agent()
    requirements = agent.state.daily_requirements

    assert len(requirements) == 5
    expected_fields = {
        "trip_id",
        "day_number",
        "date",
        "activity",
        "weather",
        "temperature_c",
        "precipitation_mm",
        "required_style",
        "needs_outerwear",
        "needs_warm_layer",
        "needs_rain_protection",
        "needs_sun_protection",
    }
    for requirement in requirements:
        payload = requirement.model_dump(mode="python")
        assert expected_fields.issubset(payload)
        assert isinstance(payload["needs_outerwear"], bool)
        assert isinstance(payload["needs_rain_protection"], bool)
        assert isinstance(payload["temperature_c"], (int, float))
        assert isinstance(payload["precipitation_mm"], (int, float))

    formal_days = [r for r in requirements if "formal-dinner" in r.activities]
    assert formal_days
    assert all(r.required_style == "formal" for r in formal_days)
    assert len(formal_days) == 1


def test_synthetic_weather_is_explicitly_labeled() -> None:
    weather = fetch_weather(
        "Paris",
        date(2030, 1, 10),
        date(2030, 1, 12),
        allow_network=False,
    )
    assert weather.source == "synthetic_fallback"
    assert weather.warning
    assert len(weather.days) == 3
    assert all(day.synthetic for day in weather.days)
    assert all(day.source == "synthetic_fallback" for day in weather.days)


def test_successful_optimization_capsule_and_checklist() -> None:
    agent = planned_agent()
    capsule = agent.state.capsule
    checklist = agent.state.checklist

    assert agent.state.status == "optimized"
    assert capsule is not None
    assert capsule.optimization_status in {"OPTIMAL", "FEASIBLE"}
    assert len(capsule.days) == 5
    assert all(day.outfit_item_ids for day in capsule.days)
    assert capsule.number_of_items == len(capsule.selected_items)
    assert capsule.total_weight_g == sum(item.weight_g for item in capsule.selected_items)
    assert capsule.total_weight_g <= 8000
    assert capsule.checklist.total_items == len(capsule.selected_items)
    assert capsule.checklist.packed_items == 0
    assert all(item.packed is False for item in capsule.checklist.items)
    assert checklist is not None
    assert checklist.total_items == capsule.checklist.total_items
    assert agent.state.weather is not None
    assert agent.state.weather.source == "synthetic_fallback"


def test_structured_input_supported() -> None:
    agent = make_agent()
    response = agent.handle_structured(
        {
            "destination": "Rome",
            "start_date": "2027-05-10",
            "end_date": "2027-05-12",
            "activities": ["sightseeing", "shopping"],
            "max_luggage_weight_kg": 8,
        }
    )

    assert response.trip_details is not None
    assert response.trip_details.duration_days == 3
    assert response.status in {"optimized", "infeasible"}
    assert response.missing_info == []


def test_infeasible_optimization_returns_recovery_suggestions() -> None:
    agent = planned_agent()
    runs_before = agent.state.optimization_runs

    response = agent.update_trip(
        {"max_luggage_weight_kg": 0.3},
        reoptimize=True,
    )

    assert response.status == "infeasible"
    assert agent.state.optimization_runs > runs_before
    assert agent.state.capsule is None
    assert response.suggestions
    text = " ".join(response.suggestions).lower()
    assert "limit" in text or "kg" in text
    assert agent.state.optimization_result is not None
    assert agent.state.optimization_result["status"] == "INFEASIBLE"


def test_update_trip_and_reoptimize() -> None:
    agent = planned_agent()
    runs_before = agent.state.optimization_runs

    response = agent.update_trip(
        {
            "activities": ["sightseeing", "shopping"],
            "max_luggage_weight_kg": 10,
        },
        reoptimize=True,
    )

    assert response.trip_details is not None
    assert response.trip_details.max_luggage_weight_kg == 10
    assert "formal-dinner" not in response.trip_details.activities
    assert response.status in {"optimized", "infeasible"}
    assert agent.state.optimization_runs > runs_before
    assert all(
        "formal-dinner" not in requirement.activities
        for requirement in agent.state.daily_requirements
    )
    if response.capsule:
        assert response.capsule.trip.max_luggage_weight_kg == 10


def test_checklist_updates_without_rerunning_optimizer() -> None:
    agent = planned_agent()
    assert agent.state.checklist is not None
    first = agent.state.checklist.items[0]
    runs_before = agent.state.optimization_runs

    response = agent.mark_packed(first.item_id, True)

    assert response.checklist is not None
    assert response.checklist.packed_items == 1
    assert response.checklist.items[0].packed is True
    assert agent.state.optimization_runs == runs_before
    assert agent.state.capsule is not None
    assert agent.state.capsule.checklist.packed_items == 1

    unpacked = agent.mark_packed(first.item_id, False)
    assert unpacked.checklist is not None
    assert unpacked.checklist.packed_items == 0
    assert agent.state.optimization_runs == runs_before


def test_tool_argument_validation_and_gap_placeholder() -> None:
    agent = make_agent()

    invalid = agent.tools.execute("get_wardrobe", {"limit": 0})
    assert invalid["ok"] is False
    assert "error" in invalid

    unknown = agent.tools.execute("does_not_exist", {})
    assert unknown["ok"] is False

    weather_too_early = agent.tools.execute("get_weather", {})
    assert weather_too_early["ok"] is False

    gap = agent.tools.execute("check_gaps", {})
    assert gap["ok"] is False

    planned = planned_agent()
    gap_ready = planned.tools.execute("check_gaps", {})
    assert gap_ready["ok"] is True
    assert gap_ready["available"] is False


def test_weather_cache_avoids_repeated_call() -> None:
    agent = planned_agent()
    first = agent.tools.execute("get_weather", {})
    second = agent.tools.execute("get_weather", {})

    assert first["ok"] is True
    assert second["ok"] is True
    assert second["cached"] is True
    assert second["source"] == agent.state.weather.source


def test_fallback_parser_handles_date_variants_and_updates() -> None:
    parsed = parse_trip_text(
        "We are flying to Lisbon from 3 June to 7 June 2027 for sightseeing. "
        "Luggage limit 10 kg, dress code smart casual, no laundry."
    )
    assert parsed["destination"] == "Lisbon"
    assert parsed["start_date"] == "2027-06-03"
    assert parsed["end_date"] == "2027-06-07"
    assert "sightseeing" in parsed["activities"]
    assert parsed["max_luggage_weight_kg"] == 10.0
    assert parsed["dress_code"] == "smart-casual"
    assert parsed["allow_laundry"] is False

    details = TripDetails.model_validate(parsed)
    assert details.duration_days == 5
    assert details.is_complete


@pytest.mark.parametrize(
    "updates",
    [
        {"duration_days": 6},
        {"start_date": "2027-07-01"},
    ],
)
def test_date_updates_do_not_keep_stale_ranges(updates: dict) -> None:
    agent = planned_agent()
    response = agent.update_trip(updates, reoptimize=False)
    details = response.trip_details
    assert details is not None
    expected_duration = updates.get("duration_days", 5)
    assert details.duration_days == expected_duration
    assert (details.end_date - details.start_date).days + 1 == expected_duration


class ScriptedLLM:
    """Duck-typed LLM that exercises the real custom tool-calling loop."""

    available = True

    def __init__(self) -> None:
        self.turns = [
            ("get_trip_details", {}),
            ("get_weather", {}),
            ("get_wardrobe", {}),
            ("get_activity_requirements", {}),
            ("optimize_trip", {}),
            ("generate_checklist", {}),
            ("__final__", {}),
        ]
        self.index = 0
        self.tool_calls_made: list[str] = []

    def extract_json(self, system_prompt: str, user_prompt: str) -> dict:
        return {
            "destination": "Paris",
            "start_date": "2027-06-03",
            "end_date": "2027-06-07",
            "duration_days": 5,
            "activities": ["sightseeing", "shopping", "formal-dinner"],
            "max_luggage_weight_kg": 8,
        }

    def chat(self, messages, tools=None, tool_choice="auto") -> AssistantTurn:
        if self.index >= len(self.turns):
            return AssistantTurn(content="Scripted LLM final response.")
        name, arguments = self.turns[self.index]
        self.index += 1
        if name == "__final__":
            return AssistantTurn(content="Scripted LLM final response.")
        self.tool_calls_made.append(name)
        return AssistantTurn(
            tool_calls=[
                ToolCall(
                    id=f"call-{self.index}",
                    name=name,
                    arguments=arguments,
                    raw_arguments=json.dumps(arguments),
                )
            ]
        )


def test_custom_llm_tool_loop_executes_scripted_tools() -> None:
    fake_llm = ScriptedLLM()
    agent = TripAgent(
        llm=fake_llm,
        allow_weather_network=False,
    )

    response = agent.handle(
        "Plan a 5-day Paris trip from 2027-06-03 to 2027-06-07 with "
        "sightseeing, shopping and a formal dinner; 8 kg clothing limit."
    )

    assert fake_llm.tool_calls_made == [
        "get_trip_details",
        "get_weather",
        "get_wardrobe",
        "get_activity_requirements",
        "optimize_trip",
        "generate_checklist",
    ]
    assert response.status == "optimized"
    assert response.capsule is not None
    assert agent.state.optimization_runs == 1
    assert "Scripted LLM final response." in response.message
    assert response.errors == []


def test_weather_needs_the_wardrobe_cannot_fill_are_reported_instead_of_blocking_the_trip() -> None:
    import pandas as pd

    from packing_backend import optimizer

    shirt = {"item_id": "a", "name": "Shirt", "category": "top", "item_type": "t-shirt"}
    raincoat = {"item_id": "b", "name": "Raincoat", "category": "outerwear", "item_type": "raincoat"}
    day = {"day_number": 1, "weather": "rainy", "needs_rain_protection": True, "needs_warm_layer": False,
           "temperature_c": 15}
    trips = pd.DataFrame([day])

    no_rain_gear = pd.DataFrame([shirt])
    available = optimizer.available_roles(optimizer.build_item_roles(no_rain_gear))
    assert "rain" in optimizer.required_roles_for_day(day)                     # the weather asks for it...
    assert "rain" not in optimizer.required_roles_for_day(day, available)      # ...but it cannot be required
    assert optimizer.unmet_roles(no_rain_gear, trips) == {"rain": [1]}         # ...and the user is told

    assert optimizer.unmet_roles(pd.DataFrame([shirt, raincoat]), trips) == {}


def test_a_known_category_is_not_overridden_by_words_in_the_description() -> None:
    import pandas as pd

    from packing_backend import optimizer

    # "low-top" in the description must not turn a pair of shoes into a top (two pairs of shoes in one outfit).
    sneakers = {"item_id": "s", "name": "White Sneakers", "category": "shoes", "item_type": "sneakers",
                "description": "Clean low-top leather sneakers"}
    roles = optimizer.build_item_roles(pd.DataFrame([sneakers]))["s"]
    assert roles == {"shoes"}
    # Without a structured category the free text is still used.
    assert "top" in optimizer.roles_of({"name": "Cotton shirt", "category": "", "item_type": ""})


def test_outfits_have_no_redundant_layer_and_one_outer_layer() -> None:
    import pandas as pd

    from packing_backend import optimizer

    def piece(item_id, category, item_type, **extra):
        return {"item_id": item_id, "name": item_id, "category": category, "item_type": item_type,
                "style": "casual", "formality_level": 2, "versatility": 3, "warmth_level": 3,
                "water_resistance": 0, "weight_g": 300, **extra}

    wardrobe = pd.DataFrame([
        piece("tee", "top", "t-shirt"), piece("jeans", "bottom", "jeans"), piece("shoes", "shoes", "sneakers"),
        piece("hoodie", "outerwear", "hoodie"), piece("cardi", "top", "cardigan"), piece("coat", "outerwear", "coat"),
    ])
    day = pd.Series({"day_number": 1, "weather": "cloudy", "activity": "sightseeing", "required_style": "casual",
                     "temperature_c": 8, "needs_outerwear": True, "needs_warm_layer": True,
                     "needs_rain_protection": False, "needs_sun_protection": False, "precipitation_mm": 0})
    roles = optimizer.build_item_roles(wardrobe)
    outfits = optimizer.generate_outfits(wardrobe, day, {}, roles, max_candidates=200)
    assert outfits
    for outfit in outfits:
        cats = [wardrobe.set_index("item_id").loc[i, "category"] for i in outfit["item_ids"]]
        assert cats.count("outerwear") <= 1                                  # one outer layer
        assert not ("hoodie" in outfit["item_ids"] and "cardi" in outfit["item_ids"])   # no stacking for nothing


def test_formal_days_avoid_casual_pieces_when_a_dressy_outfit_exists() -> None:
    import pandas as pd

    from packing_backend import optimizer

    def piece(item_id, category, item_type, formality):
        return {"item_id": item_id, "name": item_id, "category": category, "item_type": item_type,
                "style": "formal", "formality_level": formality, "versatility": 3, "warmth_level": 2,
                "water_resistance": 0, "weight_g": 300}

    wardrobe = pd.DataFrame([
        piece("blouse", "top", "blouse", 4), piece("trousers", "bottom", "trousers", 4),
        piece("jeans", "bottom", "jeans", 1), piece("heels", "shoes", "heels", 4),
        piece("sneakers", "shoes", "sneakers", 1),
    ])
    day = pd.Series({"day_number": 1, "weather": "sunny", "activity": "formal-dinner", "required_style": "formal",
                     "temperature_c": 22, "needs_outerwear": False, "needs_warm_layer": False,
                     "needs_rain_protection": False, "needs_sun_protection": False, "precipitation_mm": 0})
    roles = optimizer.build_item_roles(wardrobe)
    outfits = optimizer.generate_outfits(wardrobe, day, {}, roles, max_candidates=200)
    assert outfits
    for outfit in outfits:
        assert not {"jeans", "sneakers"} & set(outfit["item_ids"])
