"""Discovers the DressMe agents over A2A and, with a session token, asks them something.

    python scripts/a2a_discover.py                       # reads the four Agent Cards (public)
    A2A_TOKEN=<supabase access token> python scripts/a2a_discover.py --ask   # also sends a task to each agent
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from a2a_protocol import A2AClient, A2AError  # noqa: E402

AGENTS = {
    "AI Stylist": ("http://127.0.0.1:8000/a2a/stylist", "What should I wear tomorrow?", {"city": "Tunis", "country": "Tunisia"}),
    "Outfit Builder": ("http://127.0.0.1:8000/a2a/outfit", "Outfits for work this autumn", {"city": "Tunis", "country": "Tunisia"}),
    "Trip Agent": ("http://127.0.0.1:8020/a2a/trip", "A weekend in Paris, sightseeing, 8 kg of clothes", {}),
    "Gap Agent": ("http://127.0.0.1:8001/a2a/gap", "", {"goal": "winter_work"}),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ask", action="store_true", help="send a task to every agent (needs A2A_TOKEN)")
    args = parser.parse_args()
    token = os.getenv("A2A_TOKEN")
    status = 0
    for label, (url, text, data) in AGENTS.items():
        client = A2AClient(url, token=token, timeout=120)
        try:
            card = client.card()
        except A2AError as error:
            print(f"[x] {label:15} {url}  ->  {error}")
            status = 1
            continue
        skills = ", ".join(skill["id"] for skill in card["skills"])
        print(f"[ok] {label:15} {card['name']} v{card['version']}  protocol {card['protocolVersion']}  skills: {skills}")
        if args.ask:
            if not token:
                print("      set A2A_TOKEN to ask")
                continue
            try:
                task = client.send(text, data)
                print(f"      state={client.state_of(task)}  {client.text_of(task)[:160]!r}")
            except A2AError as error:
                print(f"      refused or failed: {error}")
                status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
