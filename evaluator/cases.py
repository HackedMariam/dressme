"""Jeu de test : evaluator/cases/*.yaml, un fichier par agent.

    agent: stylist
    cases:
      - id: stylist-interview-fr
        lang: fr
        watch_changes: false          # compare la garde-robe avant/après chaque pas (agent Wardrobe)
        steps:
          - input: {text: "...", data: {...}, service_down: false}
            expect: {state, route, rules: [...], required_fields: [...], max_latency_s, cold, rain, min_items}
            judge: "ce qu'une bonne réponse doit faire"
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import config


@dataclass
class Step:
    text: str = ""
    data: dict = field(default_factory=dict)
    service_down: bool = False
    expect: dict = field(default_factory=dict)
    judge: str = ""


@dataclass
class Case:
    id: str
    agent: str
    lang: str
    steps: list[Step]
    watch_changes: bool = False
    note: str = ""


class CaseError(ValueError):
    pass


def parse_case(agent: str, raw: dict) -> Case:
    if not isinstance(raw, dict) or not raw.get("id"):
        raise CaseError(f"cas sans identifiant dans le fichier de {agent}")
    steps_raw = raw.get("steps") or []
    if not steps_raw:
        raise CaseError(f"{raw['id']} : aucun pas")
    steps = []
    for number, step in enumerate(steps_raw, 1):
        source = step.get("input") or {}
        if not (source.get("text") or source.get("data")):
            raise CaseError(f"{raw['id']} pas {number} : ni texte ni données")
        steps.append(Step(text=str(source.get("text") or ""), data=dict(source.get("data") or {}),
                          service_down=bool(source.get("service_down")), expect=dict(step.get("expect") or {}),
                          judge=str(step.get("judge") or "")))
    return Case(id=str(raw["id"]), agent=agent, lang=str(raw.get("lang", "fr")), steps=steps,
                watch_changes=bool(raw.get("watch_changes")), note=str(raw.get("note", "")))


def load_cases(agents: list[str] | None = None, directory: Path | None = None) -> list[Case]:
    import yaml

    cases: list[Case] = []
    for path in sorted((directory or config.CASES_DIR).glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        agent = document.get("agent") or path.stem
        if agents and agent not in agents:
            continue
        for raw in document.get("cases") or []:
            cases.append(parse_case(agent, raw))
    ids = [c.id for c in cases]
    duplicated = {i for i in ids if ids.count(i) > 1}
    if duplicated:
        raise CaseError("identifiants de cas en double : " + ", ".join(sorted(duplicated)))
    return cases
