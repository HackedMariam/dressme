"""Tests de bout en bout AUTONOMES contre le vrai orchestrateur, le vrai Stylist, le vrai BO1 (Supabase) et le vrai
Purchase Redundancy, avec le compte de test de orchestrator/.env.test.

    python orchestrator/tests_e2e/run_e2e.py [--env-file CHEMIN_DU_.env] [--no-browser] [--unseed] [--skip-seed]

Prérequis : BO1 (8000) et Purchase Redundancy (8040) démarrés (start_all.ps1) ; le script démarre lui-même ses propres
Stylist et orchestrateur (ports 8161/8170 et 8162/8171, sans LLM, avec leurs propres fichiers de goûts et de mémoire)
pour ne pas toucher à vos services ni à vos goûts. Il crée la garde-robe de test (15 pièces, tag e2e-test) dans le
compte de test, joue les scénarios a à i, puis le scénario du navigateur (Playwright, voir run_browser.py).
À la fin : goûts et conversations du compte de test remis à zéro. Aucun secret n'est affiché.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import wardrobe  # noqa: E402
from common import (BO1_URL, PURCHASE_URL, Orchestrator, Report, Stack, expect, http,  # noqa: E402
                    load_config, scrub)

FORBIDDEN, SILK, JACKETS = wardrobe.FORBIDDEN_NAMES, wardrobe.SILK_NAME, wardrobe.JACKETS
INTERVIEW = "J'ai un entretien demain, que porter ?"
NOTHING_TO_NOTE_OUTFIT = "Il n'y a pas de tenue à noter dans ma dernière réponse."


def outfit_lines(response: str) -> list[list[str]]:
    """Vêtements de chaque tenue d'une réponse du Stylist (« 1. A (top) + B (pants) - score … »)."""
    outfits = []
    for line in response.splitlines():
        match = re.match(r"^\d+\. (.*?) - score ", line)
        if match:
            outfits.append([re.sub(r"\s*\([a-z_]+\)$", "", part) for part in match.group(1).split(" + ")])
    return outfits


def no_forbidden(outfits: list[list[str]]) -> None:
    bad = {name for outfit in outfits for name in outfit if name in FORBIDDEN}
    expect(not bad, f"pièce(s) interdite(s) proposée(s) : {sorted(bad)}")


def run_scenarios_a_to_i(report: Report, config: dict, session: dict, login_again) -> None:
    stack = Stack("sans-meteo", 8161, 8170, "none", config)
    try:
        stack.start()
        api = Orchestrator(stack.orchestrator_url, stack.stylist_url, session["access_token"])
        threads: dict[str, str] = {}
        last: dict[str, dict] = {}

        with report.scenario("a", "entretien : 3 tenues, sans pièce interdite (O3, O4)"):
            api.reset_taste()
            first = api.chat(INTERVIEW)
            threads["a"] = first["thread_id"]
            outfits = outfit_lines(first["response"])
            expect(first["route"] == "stylist", f"route {first['route']} au lieu de stylist")
            expect(len(outfits) == 3, f"{len(outfits)} tenue(s) au lieu de 3")
            no_forbidden(outfits)
            expect("Écarté pour ce dress code : Beige Off-Shoulder Sweater" in first["response"]
                   and "Plaid Wool Mini Skirt" in first["response"], "pièces écartées non annoncées")
            expect(first["history"]["saved"] is True, f"historique non enregistré : {first['history']}")

        with report.scenario("b", "« j'aime pas » ×4 : jamais de pièce interdite, puis plus aucune tenue + blazer"):
            counts, final = [], None
            for _ in range(6):
                reply = api.chat("j'aime pas", threads["a"])
                outfits = outfit_lines(reply["response"])
                counts.append(len(outfits))
                no_forbidden(outfits)
                if not outfits:
                    final = reply
                    break
            expect(final is not None, f"encore des tenues après 6 « j'aime pas » : {counts}")
            expect(len(counts) == 4, f"épuisé après {len(counts)} « j'aime pas » au lieu de 4 : {counts}")
            text = final["response"]
            expect("Tu as écarté toutes les tenues conformes" in text and "Pièce à ajouter : un blazer" in text,
                   f"message final inattendu : {text[-220:]}")
            expect("plus proches" not in text, "ancien repli « les plus proches » encore présent")

        with report.scenario("c", "« j'aime pas la 2 » : 👎 sur la tenue 2 uniquement"):
            api.reset_taste()
            first = api.chat(INTERVIEW)
            threads["c"] = first["thread_id"]
            outfits = outfit_lines(first["response"])
            expect(len(outfits) == 3, f"{len(outfits)} tenue(s) avant le retour")
            reply = api.chat("j'aime pas la 2", threads["c"])
            expect(reply["response"].startswith("C'est noté : tu n'aimes pas la tenue 2"), reply["response"][:100])
            expect(all(name in reply["response"].splitlines()[0] for name in outfits[1]),
                   "la tenue notée n'est pas la tenue 2")
            taste = api.taste()
            expect(taste["dislikes"] == 1 and taste["likes"] == 0, f"profil : {taste['likes']} 👍 {taste['dislikes']} 👎")
            expect(set(taste["disliked_items"]) == set(outfits[1]), "les 👎 ne portent pas sur les pièces de la tenue 2")

        with report.scenario("d", "« j'aime pas la 5 » : pas de tenue n° 5, aucune recommandation"):
            reply = api.chat("j'aime pas la 5", threads["c"])
            expect(reply["response"] == "Je ne trouve pas de tenue n° 5 dans mes dernières propositions.",
                   f"réponse : {reply['response'][:120]}")
            expect(reply["result"]["details"]["outfits"] == [], "une recommandation a été renvoyée")
            expect(api.taste()["dislikes"] == 1, "un 👎 a été enregistré")

        with report.scenario("e", "« top » après une clarification : rien à noter"):
            first = api.chat("Que penses-tu de tout ça ?")
            threads["e"] = first["thread_id"]
            expect(first["route"] == "clarify" and "Réponds par" in first["response"], "pas de clarification")
            reply = api.chat("top", threads["e"])
            expect(reply["response"] == "Il n'y a rien à noter dans ma dernière réponse.", reply["response"][:120])
            expect(api.taste()["likes"] == 0, "un 👍 a été enregistré")

        with report.scenario("f", "achat blazer noir (Purchase), puis « j'aime pas » : réponse courte"):
            first = api.chat("Est-ce que je devrais acheter un blazer noir ?")
            threads["f"] = first["thread_id"]
            expect(first["route"] == "purchase" and first["result"]["ok"] is True,
                   f"route {first['route']}, ok={first['result'].get('ok')} : {first['response'][:100]}")
            expect(first["response"].startswith("Avis de Purchase Redundancy sur « blazer noir »"), first["response"][:100])
            expect("15 pièces" in first["response"], "la garde-robe de test n'a pas été envoyée à Purchase")
            reply = last["f"] = api.chat("j'aime pas", threads["f"])
            expect(reply["route"] == "purchase" and reply["route_source"] == "réaction à la réponse précédente",
                   f"routage : {reply['route']} / {reply['route_source']}")
            expect(reply["response"] == "Noté. Tu veux que je compare avec une autre pièce, ou que je te propose des "
                                        "tenues avec « blazer noir » ?", reply["response"][:140])
            expect(any("réponse sans rappeler" in line for line in reply["trace"])
                   and not any("/analyze" in line for line in reply["trace"]), "Purchase a été rappelé")

        with report.scenario("g", "historique : conversation listée, puis relue après une nouvelle connexion"):
            listed = {t["id"]: t["title"] for t in api.history()}
            for key in ("a", "c", "e", "f"):
                expect(threads[key] in listed, f"conversation {key} absente de la liste")
            expect(listed[threads["f"]].startswith("Est-ce que je devrais acheter"), "titre inattendu")
            before = api.thread(threads["f"])
            expect([m["role"] for m in before] == ["user", "assistant", "user", "assistant"], "messages inattendus")
            expect(before[-1]["content"] == last["f"]["response"], "la dernière réponse enregistrée diffère")
            other = Orchestrator(stack.orchestrator_url, stack.stylist_url, login_again()["access_token"])
            expect(other.token != api.token, "la nouvelle connexion a renvoyé le même jeton")
            expect({t["id"] for t in other.history()} >= {threads[k] for k in ("a", "c", "e", "f")},
                   "conversations absentes après la nouvelle connexion")
            expect(other.thread(threads["f"]) == before, "conversation relue différente après la nouvelle connexion")

        with report.scenario("i", "réinitialisation des goûts : plus aucun malus"):
            api.reset_taste()
            thread = api.chat(INTERVIEW)["thread_id"]
            for _ in range(4):
                api.chat("j'aime pas", thread)
            malus = api.chat(INTERVIEW)
            expect("selon tes goûts" in malus["response"] and "le moins rejetées" in malus["response"],
                   "pas de malus avant la réinitialisation (précondition)")
            no_forbidden(outfit_lines(malus["response"]))
            removed = api.reset_taste()
            expect(removed >= 6, f"{removed} retour(s) supprimé(s)")
            taste = api.taste()
            expect(taste["likes"] == taste["dislikes"] == 0 and not taste["disliked_items"], f"profil : {taste}")
            after = api.chat(INTERVIEW)
            expect("selon tes goûts" not in after["response"] and "Tu as écarté" not in after["response"],
                   "malus ou repli encore présents après la réinitialisation")
            expect(len(outfit_lines(after["response"])) == 3, "pas 3 tenues après la réinitialisation")

        if report.browser_enabled:
            run_browser(report, stack, config)
        api.clear_history(reset_profile=True)               # nettoyage : conversations et goûts du compte de test
    finally:
        stack.stop()


def run_scenario_h(report: Report, config: dict, session: dict) -> None:
    stack = Stack("pluie", 8162, 8171, "offline", config)
    try:
        stack.start()
        api = Orchestrator(stack.orchestrator_url, stack.stylist_url, session["access_token"])
        with report.scenario("h", "météo hors ligne : pluie, une veste dans chaque tenue, soie écartée"):
            api.reset_taste()
            reply = api.chat(INTERVIEW)
            outfits = outfit_lines(reply["response"])
            expect(len(outfits) >= 1, "aucune tenue sous la pluie")
            no_forbidden(outfits)
            expect(all(set(outfit) & JACKETS for outfit in outfits), f"tenue sans veste : {outfits}")
            expect(not any(SILK in outfit for outfit in outfits), "le chemisier en soie est proposé sous la pluie")
            text = reply["response"]
            expect("Pluie probable (63 %)" in text and f"Écarté à cause de la pluie (daim, soie) : {SILK}." in text,
                   "contrainte de pluie non annoncée")
            expect("11 à 17 °C" in text, "la prévision enregistrée n'est pas celle utilisée")
            expect(any("prévision enregistrée (démo hors ligne)" in line for line in reply["trace"]),
                   "la source météo n'est pas indiquée dans les coulisses")
        api.clear_history(reset_profile=True)
    finally:
        stack.stop()


def run_browser(report: Report, stack: Stack, config: dict) -> None:
    launcher = shutil.which("py")
    if not launcher:
        report.add("nav", "page dans un navigateur (Playwright)", "ÉCHEC", "lanceur « py » introuvable")
        return
    env = {"TEST_EMAIL": config["TEST_EMAIL"], "TEST_PASSWORD": config["TEST_PASSWORD"], "PYTHONIOENCODING": "utf-8"}
    import os
    process = subprocess.run([launcher, "-X", "utf8", str(HERE / "run_browser.py"), "--base-url",
                              stack.orchestrator_url], env={**os.environ, **env}, capture_output=True, text=True,
                             encoding="utf-8", timeout=600)
    results = [line.split("\t", 3) for line in process.stdout.splitlines() if line.startswith("RESULT\t")]
    if not results:
        report.add("nav", "page dans un navigateur (Playwright)", "ERREUR",
                   scrub((process.stderr or process.stdout)[-300:]))
    for _, key, status, detail in ((r + [""])[:4] for r in results):
        report.add(key, detail.split(" :: ")[0], "OK" if status == "PASS" else "ÉCHEC",
                   "" if status == "PASS" else (detail.split(" :: ", 1) + [""])[1])


def main() -> int:
    parser = argparse.ArgumentParser(description="Tests de bout en bout DressMe (compte de test)")
    parser.add_argument("--env-file", help="fichier .env contenant SUPABASE_URL et SUPABASE_ANON_KEY")
    parser.add_argument("--no-browser", action="store_true", help="ne pas lancer le scénario Playwright")
    parser.add_argument("--unseed", action="store_true", help="supprimer la garde-robe de test à la fin")
    parser.add_argument("--skip-seed", action="store_true", help="ne pas recréer la garde-robe de test")
    args = parser.parse_args()
    try:
        config = load_config(args.env_file)
    except RuntimeError as exc:
        print(exc)
        return 2
    for label, url in (("BO1", f"{BO1_URL}/api/health"), ("Purchase Redundancy", f"{PURCHASE_URL}/health")):
        if http("GET", url, timeout=5)[0] != 200:
            print(f"{label} ne répond pas ({url}) : lancer start_all.ps1 d'abord.")
            return 2

    report = Report()
    report.browser_enabled = not args.no_browser
    login_args = (config["SUPABASE_URL"], config["SUPABASE_ANON_KEY"], config["TEST_EMAIL"], config["TEST_PASSWORD"])

    def login_again():
        return wardrobe.login(*login_args)

    session = login_again()
    try:
        with report.scenario("0", "garde-robe de test : 15 pièces créées dans le compte de test"):
            if not args.skip_seed:
                created = wardrobe.seed(config["SUPABASE_URL"], config["SUPABASE_ANON_KEY"], session)
                expect(created == len(wardrobe.PIECES), f"{created} pièce(s) créée(s)")
            status, items = http("GET", f"{BO1_URL}/api/items", session["access_token"])
            expect(status == 200 and isinstance(items, list), f"BO1 /api/items : HTTP {status}")
            expect(len(items) == len(wardrobe.PIECES), f"BO1 voit {len(items)} pièce(s)")
            expect(not any(i["name"] == "Navy Blazer" or i["category"] == "blazer" for i in items), "un blazer est présent")
        if report.rows[-1][2] == "OK":
            run_scenarios_a_to_i(report, config, session, login_again)
            run_scenario_h(report, config, session)
    finally:
        if args.unseed:
            removed = wardrobe.unseed(config["SUPABASE_URL"], config["SUPABASE_ANON_KEY"], login_again())
            print(f"garde-robe de test supprimée ({removed} pièce(s))")
    report.print()
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
