"""Test de la page de l'orchestrateur dans un vrai navigateur (Playwright, Chromium) avec le compte de test.

    py run_browser.py --base-url http://127.0.0.1:8170

Lancé par run_e2e.py (Python 3.14 avec Playwright ; le Chromium est dans %LOCALAPPDATA%\\ms-playwright). Identifiants :
variables d'environnement TEST_EMAIL / TEST_PASSWORD, sinon orchestrator/.env.test. Rien de secret n'est affiché ni
photographié : le formulaire de connexion n'est photographié que vide, et l'adresse e-mail affichée est masquée.
Captures dans tests_e2e/screenshots/ (ignoré par git). Sortie : une ligne « RESULT<TAB>clé<TAB>PASS|FAIL<TAB>détail »
par vérification ; code de sortie 1 si une vérification échoue.
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
SHOTS = HERE / "screenshots"
QUESTION = "J'ai un entretien demain, que porter ?"


def read_env(path: Path) -> dict[str, str]:
    values = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key and not key.startswith("#"):
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


class Run:
    def __init__(self):
        self.failed = False

    def check(self, key: str, title: str, action) -> None:
        try:
            detail = action() or ""
            print(f"RESULT\t{key}\tPASS\t{title} :: {detail}", flush=True)
        except Exception as exc:  # noqa: BLE001 - toute erreur est un échec de la vérification
            self.failed = True
            message = str(exc).strip().splitlines()[0][:200] if str(exc).strip() else type(exc).__name__
            print(f"RESULT\t{key}\tFAIL\t{title} :: {message}", flush=True)
            traceback.print_exc(limit=1, file=sys.stderr)


def need(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    test = read_env(HERE.parent / ".env.test")
    email = os.environ.get("TEST_EMAIL") or test.get("TEST_EMAIL", "")
    password = os.environ.get("TEST_PASSWORD") or test.get("TEST_PASSWORD", "")
    if not email or not password:
        print("RESULT\tnav\tFAIL\tidentifiants :: TEST_EMAIL / TEST_PASSWORD absents")
        return 1
    SHOTS.mkdir(exist_ok=True)
    run, js_errors = Run(), []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1300, "height": 900})
        page.set_default_timeout(45000)
        page.on("pageerror", lambda error: js_errors.append(str(error)[:160]))
        # Retard réglable de la lecture des messages d'une conversation (window.__delayHistory, en ms) : sert à rejouer
        # la course « réouverture lente de la dernière conversation » sans bloquer le navigateur.
        page.add_init_script(r"""(() => { const original = window.fetch.bind(window);
          window.fetch = async (input, init) => {
            const url = typeof input === "string" ? input : input.url;
            if (window.__delayHistory && /\/api\/history\/[^/?]+$/.test(url))
              await new Promise((resolve) => setTimeout(resolve, window.__delayHistory));
            return original(input, init); }; })();""")

        def shot(name: str) -> None:
            page.screenshot(path=str(SHOTS / name), mask=[page.locator("#email")])

        def visible(selector: str) -> bool:
            return page.locator(selector).is_visible()

        def log_users() -> int:
            return page.locator("#log .msg.user").count()

        def login() -> None:
            if not page.locator("#overlay.open").count():
                page.click("#open-login")
            page.wait_for_selector("#overlay.open")
            page.fill("#login-email", email)
            page.fill("#login-password", password)
            page.click("#do-login")
            page.wait_for_selector("#who:not([hidden])")

        def ask(text: str) -> None:
            before = log_users()
            page.fill("#q", text)
            page.click("#send")
            page.wait_for_function("(n) => document.querySelectorAll('#log .msg.user').length > n "
                                   "&& !document.querySelector('#send').disabled", arg=before)

        # ---- 1. page déconnectée
        page.goto(args.base_url, wait_until="domcontentloaded")
        page.wait_for_function("typeof window.supabase !== 'undefined'")
        page.wait_for_selector("#overlay.open")

        def logged_out_hidden():
            need(not visible("#history"), "le panneau « Mes conversations » est visible hors connexion")
            need(not visible("#confirm-clear"), "la confirmation d'effacement est visible hors connexion")
            need(not visible("#clear-history"), "le bouton Effacer est visible hors connexion")
            shot("01-deconnecte.png")                      # formulaire vide : aucun identifiant à l'écran
            return "panneau, bouton et confirmation cachés"
        run.check("n1", "page déconnectée : historique et confirmation cachés", logged_out_hidden)

        # ---- 2. connexion
        def connect():
            login()
            need(visible("#history") and visible("#new-thread"), "le panneau d'historique n'apparaît pas")
            need(not visible("#overlay.open"), "le formulaire de connexion reste ouvert")
            shot("02-connecte.png")
            return "connecté, panneau visible"
        run.check("n2", "connexion : panneau d'historique visible", connect)

        # ---- 3. bouton Effacer éloigné
        def clear_is_far():
            new, clear = page.locator("#new-thread").bounding_box(), page.locator("#clear-history").bounding_box()
            lst = page.locator("#threads").bounding_box()
            need(clear["y"] >= lst["y"] + lst["height"] - 1, "« Effacer » n'est pas sous la liste des conversations")
            gap = clear["y"] - (new["y"] + new["height"])
            need(gap >= 20, f"« Effacer » à seulement {gap:.0f} px de « Nouvelle conversation »")
            return f"{gap:.0f} px sous « Nouvelle conversation », sous la liste"
        run.check("n3", "bouton « Effacer mon historique » éloigné de « Nouvelle conversation »", clear_is_far)

        # ---- 4. confirmation cachée tant qu'on n'a pas cliqué
        def confirmation():
            need(not visible("#confirm-clear"), "la confirmation est affichée avant tout clic")
            page.click("#clear-history")
            need(visible("#confirm-clear") and visible("#reset-profile"), "la confirmation n'apparaît pas au clic")
            need(not page.locator("#reset-profile").is_checked(), "la case des goûts est cochée par défaut")
            shot("03-confirmation.png")
            page.click("#cancel-clear")
            need(not visible("#confirm-clear"), "la confirmation reste affichée après « Annuler »")
            return "cachée, visible au clic, recachée après « Annuler » (case décochée)"
        run.check("n4", "confirmation d'effacement cachée tant qu'on n'a pas cliqué", confirmation)

        # ---- 5. nouvelle conversation : le bandeau disparaît au premier message
        def new_conversation():
            page.click("#new-thread")
            need("Nouvelle conversation" in page.locator("#log").inner_text(), "le bandeau n'apparaît pas")
            ask(QUESTION)
            need("elle sera enregistrée" not in page.locator("#log").inner_text(), "le bandeau reste affiché")
            need(page.locator("#log .msg.card .body").last.inner_text().strip() != "", "réponse vide")
            return "bandeau affiché puis retiré au premier message"
        run.check("n5", "« Nouvelle conversation » : bandeau retiré au premier message", new_conversation)

        # ---- 6. liste des conversations
        def conversation_list():
            page.wait_for_selector("#threads .thread.active")          # la liste est rafraîchie après l'envoi
            titles = page.locator("#threads .thread").all_inner_texts()
            need(any(t.startswith("J'ai un entretien demain") for t in titles), f"{len(titles)} titre(s), aucun ne convient")
            active = page.locator("#threads .thread.active")
            need(active.count() == 1 and active.inner_text().startswith("J'ai un entretien demain"),
                 "la conversation active n'est pas celle qui vient d'être commencée")
            narrow = [b for b in page.locator("#threads .thread").all()
                      if len(b.inner_text()) >= 20 and b.bounding_box()["width"] < 120]
            need(not narrow, f"{len(narrow)} titre(s) tronqués à moins de 120 px (pastilles comprimées)")
            shot("04-conversation.png")
            return f"{len(titles)} conversation(s) listée(s), la courante est active, titres lisibles"
        run.check("n6", "liste des conversations", conversation_list)

        # ---- 7. déconnexion : la page se vide
        def logout_empties():
            page.click("#logout")
            page.wait_for_selector("#who", state="hidden")
            need(page.locator("#log .msg.user").count() == 0 and page.locator("#log .msg.card").count() <= 1,
                 "des messages de la conversation restent affichés après la déconnexion")
            need("Déconnecté" in page.locator("#log").inner_text(), "pas de note de déconnexion")
            need(page.locator("#threads .thread").count() == 0, "la liste des conversations reste affichée")
            need(not visible("#history"), "le panneau d'historique reste visible")
            shot("05-deconnecte.png")
            return "conversation, liste et panneau vidés (seule reste la note « Déconnecté »)"
        run.check("n7", "déconnexion : la page se vide", logout_empties)

        # ---- 8. reconnexion : la conversation revient (rien n'a été supprimé en base)
        def relogin():
            login()
            page.wait_for_selector("#threads .thread")
            page.wait_for_selector("#log .msg.user")
            need(QUESTION in page.locator("#log .msg.user").first.inner_text(), "la dernière conversation n'est pas rechargée")
            need(page.locator("#log .msg.card").count() >= 1, "la réponse enregistrée n'est pas rechargée")
            shot("06-reconnecte.png")
            return "dernière conversation rechargée avec sa réponse"
        run.check("n8", "reconnexion : la conversation revient", relogin)

        # ---- 8 bis. course : la réouverture lente de la dernière conversation n'écrase pas une conversation commencée
        def slow_reopen_does_not_overwrite():
            page.click("#logout")
            page.wait_for_selector("#who", state="hidden")
            page.evaluate("window.__delayHistory = 5000")
            login()
            page.wait_for_selector("#threads .thread")                 # la liste est là, la réouverture est en retard
            page.click("#new-thread")
            ask("Est-ce que j'ai une jupe noire ?")
            page.wait_for_timeout(6500)                                  # la réouverture en retard arrive maintenant
            page.evaluate("window.__delayHistory = 0")
            users = page.locator("#log .msg.user").all_inner_texts()
            need(users == ["Est-ce que j'ai une jupe noire ?"], f"conversation écrasée : {users}")
            need(page.locator("#threads .thread.active").count() == 1
                 and page.locator("#threads .thread.active").inner_text().startswith("Est-ce que j'ai une jupe"),
                 "la conversation active n'est pas la nouvelle")
            return "la nouvelle conversation reste affichée et active"
        run.check("n11", "réouverture lente de la dernière conversation : n'écrase pas la nouvelle", slow_reopen_does_not_overwrite)

        # ---- 9. effacement avec réinitialisation des goûts (nettoyage du compte de test)
        def clear_all():
            page.click("#clear-history")
            page.check("#reset-profile")
            page.click("#do-clear")
            page.wait_for_function("() => document.querySelector('#log').innerText.includes('Ton historique a été effacé')")
            text = page.locator("#log").inner_text()
            need("Tes goûts ont été réinitialisés" in text, f"goûts non réinitialisés : {text[-120:]}")
            need(page.locator("#threads .thread").count() == 0, "des conversations restent listées")
            need(not visible("#confirm-clear"), "la confirmation reste affichée")
            shot("07-efface.png")
            return "historique effacé et goûts réinitialisés"
        run.check("n9", "« Effacer mon historique » + réinitialisation des goûts", clear_all)

        run.check("n10", "aucune erreur JavaScript dans la page",
                  lambda: need(not js_errors, f"{len(js_errors)} erreur(s) : {js_errors[:2]}") or "aucune")
        browser.close()
    return 1 if run.failed else 0


if __name__ == "__main__":
    sys.exit(main())
