"""Runnable CLI demo for the DressMe Trip Agent.

Run from the repository root:
    python -m packing_backend.trip_agent.cli --demo
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

if __package__ in {None, ""}:  # allow direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    from .agent import TripAgent
    from .logging_utils import configure_logging
    from .schemas import AgentResponse
except ImportError:  # pragma: no cover - direct execution fallback
    from packing_backend.trip_agent.agent import TripAgent
    from packing_backend.trip_agent.logging_utils import configure_logging
    from packing_backend.trip_agent.schemas import AgentResponse

DEFAULT_REQUEST = (
    "I'm going to Paris for 5 days for sightseeing, shopping, and a formal "
    "dinner. My clothing luggage limit is 8 kg."
)


def print_response(response: AgentResponse, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(response.to_json_dict(), indent=2, ensure_ascii=False))
        return

    print(response.message)
    if response.status == "needs_clarification" and response.missing_info:
        print(f"Missing fields: {', '.join(response.missing_info)}")
    if response.status == "optimized" and response.capsule:
        capsule = response.capsule
        print(
            f"Days/outfits: {len(capsule.days)} | "
            f"Items: {capsule.number_of_items} | "
            f"Weight: {capsule.total_weight_g / 1000:.2f} kg | "
            f"Weather: {capsule.trip.weather_source}"
        )
        for day in capsule.days:
            items = ", ".join(item.name for item in day.outfit_items)
            print(
                f"  Day {day.day_number} ({day.date.isoformat()}, {day.activity}, "
                f"{day.weather}, {day.temperature_c:g}C, {day.required_style}): {items}"
            )
        print("Checklist:")
        for item in capsule.checklist.items:
            mark = "x" if item.packed else " "
            print(
                f"  [{mark}] {item.item_id} {item.name} "
                f"({item.category}, {item.weight_g} g)"
            )
    if response.suggestions and not all(
        suggestion in response.message for suggestion in response.suggestions
    ):
        print("Suggestions:")
        for suggestion in response.suggestions:
            print(f"  - {suggestion}")
    if response.errors:
        print("Errors:")
        for error in response.errors[-5:]:
            print(f"  - {error}")


def demo_dates() -> str:
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=4)
    return f"{start.isoformat()} to {end.isoformat()}"


def run_demo(args: argparse.Namespace) -> int:
    agent = TripAgent(
        use_llm=not args.no_llm,
        allow_weather_network=not args.no_weather_network,
    )
    request = args.request or DEFAULT_REQUEST
    dates = args.dates or demo_dates()

    print("=== 1. Free-text request (missing dates) ===")
    response = agent.handle(request)
    print_response(response, args.json)

    if response.status == "needs_clarification":
        print("\n=== 2. Clarification and end-to-end planning ===")
        response = agent.handle(dates)
        print_response(response, args.json)

    if args.structured:
        return 0

    print("\n=== 3. Infeasible limit + recovery suggestions ===")
    infeasible = agent.update_trip(
        {"max_luggage_weight_kg": 0.3},
        reoptimize=True,
    )
    print_response(infeasible, args.json)

    print("\n=== 4. Update the trip and reoptimize ===")
    updated = agent.update_trip(
        {"max_luggage_weight_kg": 8.0},
        reoptimize=True,
    )
    print_response(updated, args.json)

    if updated.checklist and updated.checklist.items:
        first = updated.checklist.items[0]
        print("\n=== 5. Update checklist without rerunning optimizer ===")
        packed = agent.mark_packed(first.item_id, True)
        print_response(packed, args.json)
        print(f"Optimization runs so far: {agent.state.optimization_runs}")

    if not args.json:
        print("\n=== Capsule JSON ===")
        print(json.dumps(agent.state_json(), indent=2, ensure_ascii=False))
    return 0


def run_interactive(args: argparse.Namespace) -> int:
    agent = TripAgent(
        use_llm=not args.no_llm,
        allow_weather_network=not args.no_weather_network,
    )
    print("DressMe Trip Agent. Type /quit to exit. Commands: /update JSON, /pack ID, /unpack ID, /json")
    while True:
        try:
            text = input("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not text:
            continue
        if text in {"/quit", "/exit"}:
            return 0
        if text == "/json":
            print(json.dumps(agent.state_json(), indent=2, ensure_ascii=False))
            continue
        if text.startswith("/update "):
            payload = text[len("/update "):].strip()
            try:
                updates = json.loads(payload)
            except json.JSONDecodeError as exc:
                print(f"Invalid JSON: {exc}")
                continue
            print_response(agent.update_trip(updates, reoptimize=True), args.json)
            continue
        if text.startswith("/pack ") or text.startswith("/unpack "):
            command, item_id = text.split(maxsplit=1)
            print_response(agent.mark_packed(item_id, command == "/pack"), args.json)
            continue
        print_response(agent.handle(text), args.json)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DressMe Trip Agent CLI")
    parser.add_argument("--demo", action="store_true", help="Run the full end-to-end demo")
    parser.add_argument("--interactive", action="store_true", help="Start an interactive session")
    parser.add_argument("--request", help="Free-text trip request")
    parser.add_argument("--structured", help="Structured trip JSON instead of free text")
    parser.add_argument("--dates", help="Clarification text containing dates")
    parser.add_argument("--update", help="Trip update JSON; implies reoptimization")
    parser.add_argument("--mark-packed", help="Checklist item_id to mark packed")
    parser.add_argument("--no-llm", action="store_true", help="Use deterministic extraction only")
    parser.add_argument(
        "--no-weather-network",
        action="store_true",
        help="Skip Open-Meteo and use labeled synthetic weather",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON responses")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.verbose)

    if args.demo:
        return run_demo(args)
    if args.interactive:
        return run_interactive(args)

    structured = None
    if args.structured:
        try:
            structured = json.loads(args.structured)
        except json.JSONDecodeError as exc:
            parser.error(f"--structured is not valid JSON: {exc}")

    agent = TripAgent(
        use_llm=not args.no_llm,
        allow_weather_network=not args.no_weather_network,
    )

    if structured:
        response = agent.handle_structured(structured)
        print_response(response, args.json)
    elif args.request:
        response = agent.handle(args.request)
        if response.status == "needs_clarification" and args.dates:
            response = agent.handle(args.dates)
        print_response(response, args.json)
    else:
        parser.print_help()
        return 2

    if args.update:
        try:
            updates = json.loads(args.update)
        except json.JSONDecodeError as exc:
            parser.error(f"--update is not valid JSON: {exc}")
        response = agent.update_trip(updates, reoptimize=True)
        print_response(response, args.json)

    if args.mark_packed:
        response = agent.mark_packed(args.mark_packed, True)
        print_response(response, args.json)

    return 1 if agent.state.status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
