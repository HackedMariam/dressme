"""Outils communs des tests de bout en bout : configuration lue sans rien afficher, piles de services de test
isolées (Stylist + orchestrateur sur leurs propres ports, avec leurs propres fichiers de goûts et de mémoire),
client HTTP de l'orchestrateur et compte rendu.

Aucun secret n'est écrit ici ni affiché : les identifiants du compte de test viennent de orchestrator/.env.test, la clé
anon de l'environnement ou de .env ; le jeton reste en mémoire ; les extraits de journaux sont filtrés (scrub).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORCHESTRATOR = HERE.parent
REPO = ORCHESTRATOR.parent
BACKEND_BO4 = REPO / "bo4" / "backend"
BO1_URL, PURCHASE_URL = "http://127.0.0.1:8000", "http://127.0.0.1:8040"
SECRET_PATTERNS = (re.compile(r"eyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{5,}"), re.compile(r"(?i)bearer\s+\S+"),
                   re.compile(r"(?i)(apikey|password|token)[\"'=: ]+\S+"))


def scrub(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[masqué]", text)
    return text


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key and not key.startswith("#"):
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_config(env_file: str | None = None) -> dict[str, str]:
    """SUPABASE_URL, SUPABASE_ANON_KEY (environnement, puis --env-file, orchestrator/.env, .env racine) et
    TEST_EMAIL / TEST_PASSWORD (orchestrator/.env.test). Lève RuntimeError sans jamais citer une valeur."""
    config: dict[str, str] = {}
    sources = [Path(env_file)] if env_file else []
    sources += [ORCHESTRATOR / ".env", REPO / ".env"]
    for key in ("SUPABASE_URL", "SUPABASE_ANON_KEY"):
        config[key] = os.environ.get(key, "")
        for source in sources:
            config[key] = config[key] or read_env_file(source).get(key, "")
    test = read_env_file(ORCHESTRATOR / ".env.test")
    config["TEST_EMAIL"] = os.environ.get("TEST_EMAIL") or test.get("TEST_EMAIL", "")
    config["TEST_PASSWORD"] = os.environ.get("TEST_PASSWORD") or test.get("TEST_PASSWORD", "")
    missing = [k for k in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "TEST_EMAIL", "TEST_PASSWORD") if not config[k]]
    if missing:
        raise RuntimeError("configuration incomplète : " + ", ".join(missing)
                           + " (SUPABASE_* : --env-file ou orchestrator/.env ; TEST_* : orchestrator/.env.test)")
    return config


def http(method: str, url: str, token: str | None = None, body=None, timeout: float = 120.0):
    """(statut, JSON ou None). Ne lève pas sur un statut d'erreur HTTP."""
    headers = {"Accept": "application/json"}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else None
        except ValueError:
            return exc.code, None


def wait_for(url: str, seconds: float = 90.0) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if http("GET", url, timeout=3)[0] == 200:
                return True
        except Exception:  # noqa: BLE001 - service pas encore prêt
            pass
        time.sleep(1.0)
    return False


# ---------------------------------------------------------------------------------------------- piles de services
class Stack:
    """Un Stylist et un orchestrateur de test (ports dédiés, --require-auth, sans LLM pour des réponses
    reproductibles), branchés sur le vrai BO1 (8000) et le vrai Purchase Redundancy (8040).

    weather : "none" = saison de la date, sans appel météo ; "offline" = prévision fixe enregistrée (pluie 63 %)."""

    def __init__(self, name: str, stylist_port: int, orchestrator_port: int, weather: str, config: dict[str, str]):
        self.name, self.weather, self.config = name, weather, config
        self.stylist_port, self.orchestrator_port = stylist_port, orchestrator_port
        self.tmp = Path(tempfile.mkdtemp(prefix=f"dressme-e2e-{name}-"))
        self.processes: list[subprocess.Popen] = []
        self.logs: dict[str, Path] = {}

    @property
    def orchestrator_url(self) -> str:
        return f"http://127.0.0.1:{self.orchestrator_port}"

    @property
    def stylist_url(self) -> str:
        return f"http://127.0.0.1:{self.stylist_port}"

    def _spawn(self, label: str, args: list[str], cwd: Path, env: dict[str, str]) -> None:
        log = self.tmp / f"{label}.log"
        self.logs[label] = log
        handle = open(log, "wb")
        self.processes.append(subprocess.Popen([sys.executable, "-X", "utf8", *args], cwd=cwd, env=env,
                                               stdout=handle, stderr=subprocess.STDOUT))

    def start(self) -> None:
        import yaml

        env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        env.pop("STYLIST_WEATHER_OFFLINE", None)
        stylist_env = {**env, "STYLIST_CHECKPOINT_DB": str(self.tmp / "stylist.sqlite")}
        stylist_args = ["stylist_web.py", "--port", str(self.stylist_port), "--require-auth", "--no-llm",
                        "--bo1-url", BO1_URL, "--feedback-file", str(self.tmp / "feedback.json")]
        if self.weather == "offline":
            stylist_env["STYLIST_WEATHER_OFFLINE"] = "1"
        else:
            stylist_args.append("--no-weather")
        self._spawn("stylist", stylist_args, BACKEND_BO4, stylist_env)

        services = yaml.safe_load((ORCHESTRATOR / "services.yaml").read_text(encoding="utf-8"))
        services["services"]["stylist"]["url"] = self.stylist_url
        services_file = self.tmp / "services.yaml"
        services_file.write_text(yaml.safe_dump(services, allow_unicode=True), encoding="utf-8")
        orchestrator_env = {**env, "ORCHESTRATOR_CHECKPOINT_DB": str(self.tmp / "orchestrator.sqlite"),
                            "SUPABASE_URL": self.config["SUPABASE_URL"],
                            "SUPABASE_ANON_KEY": self.config["SUPABASE_ANON_KEY"]}
        self._spawn("orchestrator", ["app.py", "--port", str(self.orchestrator_port), "--require-auth", "--no-llm",
                                     "--services", str(services_file)], ORCHESTRATOR, orchestrator_env)
        for label, url in (("stylist", f"{self.stylist_url}/api/graph"),
                           ("orchestrateur", f"{self.orchestrator_url}/api/config")):
            if not wait_for(url):
                raise RuntimeError(f"{label} de la pile « {self.name} » ne démarre pas :\n" + self.log_tail())

    def log_tail(self, lines: int = 12) -> str:
        out = []
        for label, path in self.logs.items():
            text = path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
            out.append(f"--- {label}\n" + scrub("\n".join(text)))
        return "\n".join(out)

    def stop(self) -> None:
        for process in self.processes:
            process.terminate()
        for process in self.processes:
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
        self.processes.clear()
        shutil.rmtree(self.tmp, ignore_errors=True)


class Orchestrator:
    """Client de l'orchestrateur d'une pile, avec le jeton du compte de test (jamais affiché)."""

    def __init__(self, base_url: str, stylist_url: str, token: str):
        self.base, self.stylist, self.token = base_url, stylist_url, token

    def chat(self, message: str, thread_id: str | None = None) -> dict:
        status, data = http("POST", f"{self.base}/api/chat", self.token, {"message": message, "thread_id": thread_id})
        if status != 200:
            raise AssertionError(f"/api/chat a répondu HTTP {status} : {str(data)[:160]}")
        return data

    def history(self, token: str | None = None) -> list[dict]:
        status, data = http("GET", f"{self.base}/api/history", token or self.token)
        if status != 200:
            raise AssertionError(f"/api/history a répondu HTTP {status}")
        return data["threads"]

    def thread(self, thread_id: str, token: str | None = None) -> list[dict]:
        status, data = http("GET", f"{self.base}/api/history/{thread_id}", token or self.token)
        if status != 200:
            raise AssertionError(f"/api/history/<fil> a répondu HTTP {status}")
        return data["messages"]

    def taste(self) -> dict:
        """Profil de goûts vu par le Stylist (compte du jeton) : likes, dislikes…"""
        status, data = http("GET", f"{self.stylist}/api/profile", self.token)
        if status != 200:
            raise AssertionError(f"/api/profile du Stylist a répondu HTTP {status}")
        return data

    def reset_taste(self) -> int:
        status, data = http("POST", f"{self.base}/api/profile/reset", self.token)
        if status != 200:
            raise AssertionError(f"/api/profile/reset a répondu HTTP {status} : {str(data)[:120]}")
        return data["removed"]

    def clear_history(self, reset_profile: bool = False) -> dict:
        status, data = http("DELETE", f"{self.base}/api/history" + ("?reset_profile=true" if reset_profile else ""),
                            self.token)
        if status != 200:
            raise AssertionError(f"DELETE /api/history a répondu HTTP {status}")
        return data


# ---------------------------------------------------------------------------------------------- compte rendu
class Report:
    def __init__(self):
        self.rows: list[tuple[str, str, str, str]] = []

    @contextmanager
    def scenario(self, key: str, title: str):
        """Un scénario : un échec (assertion ou exception) est consigné, les suivants continuent."""
        try:
            yield
            self.rows.append((key, title, "OK", ""))
        except AssertionError as exc:
            self.rows.append((key, title, "ÉCHEC", scrub(str(exc))[:400]))
        except Exception as exc:  # noqa: BLE001
            self.rows.append((key, title, "ERREUR", scrub(f"{type(exc).__name__}: {exc}")[:400]))
            traceback.print_exc(limit=2)

    def add(self, key: str, title: str, status: str, detail: str = "") -> None:
        self.rows.append((key, title, status, scrub(detail)[:400]))

    @property
    def failed(self) -> bool:
        return any(status != "OK" for _, _, status, _ in self.rows)

    def print(self) -> None:
        width = max(len(title) for _, title, _, _ in self.rows) if self.rows else 10
        print("\n" + "=" * (width + 22))
        for key, title, status, detail in self.rows:
            print(f"{key:4} {title:<{width}}  {status}")
            if detail:
                print(f"       -> {detail}")
        ok = sum(status == "OK" for _, _, status, _ in self.rows)
        print("=" * (width + 22) + f"\n{ok}/{len(self.rows)} scénarios OK")


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
