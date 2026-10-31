"""Météo du Stylist : plusieurs sources, un seul format, jamais d'exception vers /api/chat.

Ordre d'appel (RobustWeather) :
  0. mode démo hors ligne (STYLIST_WEATHER_OFFLINE=1) : prévision fixe de weather_offline.json, sans réseau ;
  1. cache frais (< 30 min) pour la ville et le jour ;
  2. Open-Meteo, 3. MET Norway Locationforecast 2.0 (api.met.no), 4. wttr.in (JSON) : 3 s au plus chacune,
     délai tenu par un fil d'exécution (il couvre aussi la résolution DNS, que le timeout de urllib ignore) ;
     une source en panne est ignorée 60 s, pour ne pas faire attendre chaque message ;
  5. cache de secours (< 24 h) ;
  6. sinon WeatherError : l'agent déduit la saison de la date et le dit en une ligne.

Format commun (toutes les sources) : city, date, t_min, t_max, rain_probability (0-100 ou None),
rain_code (pluie ou orage annoncés), season, source (affichée), attribution.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

HERE = Path(__file__).resolve().parent
OFFLINE_FILE = HERE / "weather_offline.json"
CACHE_FILE = Path(os.environ.get("STYLIST_WEATHER_CACHE") or HERE.parent / "data" / "weather_cache.json")
SOURCE_DEADLINE_S = 3.0
FRESH_CACHE_S = 30 * 60
STALE_CACHE_S = 24 * 3600
FAILURE_BACKOFF_S = 60.0
# MET Norway exige un User-Agent qui identifie l'application et un moyen de contact.
USER_AGENT = "DressMe/0.1 (projet universitaire; https://github.com/HackedMariam/dressme)"

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
MET_NORWAY_URL = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
WTTR_URL = "https://wttr.in/{city}"
ATTRIBUTION = {
    "Open-Meteo": "Open-Meteo.com (CC BY 4.0)",
    "MET Norway": "Données MET Norway, api.met.no (CC BY 4.0)",
    "wttr.in": "wttr.in (données World Weather Online)",
}
# Coordonnées utilisées par MET Norway quand le géocodage Open-Meteo est lui aussi en panne.
KNOWN_CITIES = {
    "tunis": (36.8065, 10.1815), "sfax": (34.7406, 10.7603), "sousse": (35.8256, 10.6084),
    "ariana": (36.8665, 10.1647), "bizerte": (37.2744, 9.8739), "nabeul": (36.4561, 10.7376),
    "paris": (48.8566, 2.3522), "lyon": (45.764, 4.8357), "marseille": (43.2965, 5.3698),
    "london": (51.5072, -0.1276), "londres": (51.5072, -0.1276), "madrid": (40.4168, -3.7038),
    "rome": (41.9028, 12.4964), "berlin": (52.52, 13.405), "bruxelles": (50.8503, 4.3517),
}
# Codes World Weather Online (wttr.in) de pluie, averse ou orage. 176 (« pluie éparse possible ») n'en fait pas
# partie : présent presque chaque jour sur une heure, il déclencherait la contrainte de pluie sans raison.
WTTR_RAIN_CODES = {200, 263, 266, 281, 284, 293, 296, 299, 302, 305, 308, 311, 314, 353, 356, 359,
                   386, 389, 392, 395}


class WeatherError(RuntimeError):
    """Prévision météo indisponible (réseau, ville inconnue, jour hors prévision, réponse invalide)."""


def season_from_temperature(t_min: float, t_max: float, month: int) -> str:
    """Traduit la température prévue en « saison » comprise par le moteur BO4.
    Moyenne <= 10 °C : hiver ; >= 22 °C : été ; sinon mi-saison (printemps ou automne selon le mois)."""
    mean = (t_min + t_max) / 2
    if mean <= 10:
        return "winter"
    if mean >= 22:
        return "summer"
    return "spring" if 3 <= month <= 8 else "autumn"


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text).strip().lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def normalize(raw: dict, city: str, day: dt.date, source: str) -> dict:
    """Prévision brute d'une source -> format commun ; WeatherError si les températures manquent
    (Open-Meteo peut renvoyer null : c'est ce qui faisait planter /api/chat)."""
    t_min, t_max = _number(raw.get("t_min")), _number(raw.get("t_max"))
    if t_min is None or t_max is None or not (-60 <= t_min <= 60 and -60 <= t_max <= 60):
        raise WeatherError(f"{source} : température absente ou invalide")
    t_min, t_max = min(t_min, t_max), max(t_min, t_max)
    rain = _number(raw.get("rain_probability"))
    rain = None if rain is None else int(round(min(max(rain, 0.0), 100.0)))
    return {"city": str(raw.get("city") or city), "date": day.isoformat(), "t_min": t_min, "t_max": t_max,
            "rain_probability": rain, "rain_code": bool(raw.get("rain_code")),
            "season": season_from_temperature(t_min, t_max, day.month), "source": source,
            "attribution": ATTRIBUTION.get(source, source)}


def _with_deadline(fn: Callable, seconds: float, *args: Any) -> Any:
    """Appelle fn(*args) dans un fil et abandonne au bout de `seconds` (le fil, démon, finit seul)."""
    box: dict = {}

    def run() -> None:
        try:
            box["value"] = fn(*args)
        except BaseException as exc:  # noqa: BLE001 - relancée dans l'appelant
            box["error"] = exc

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(seconds)
    if worker.is_alive():
        raise WeatherError(f"délai de {seconds:g} s dépassé")
    if "error" in box:
        raise box["error"]
    return box["value"]


def fetch_json(url: str, params: Optional[dict] = None, timeout: float = SOURCE_DEADLINE_S) -> Any:
    query = f"?{urllib.parse.urlencode(params)}" if params else ""
    request = urllib.request.Request(url + query, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


# --------------------------------------------------------------------------------------
# Sources secondaires (Open-Meteo reste stylist_agent.open_meteo_forecast)
# --------------------------------------------------------------------------------------
def coordinates(city: str, timeout: float = SOURCE_DEADLINE_S, get: Callable = fetch_json) -> tuple[float, float]:
    """Latitude et longitude : table intégrée, sinon géocodage Open-Meteo."""
    known = KNOWN_CITIES.get(_plain(city))
    if known:
        return known
    places = (get(GEOCODING_URL, {"name": city, "count": 1, "language": "fr", "format": "json"}, timeout)
              or {}).get("results") or []
    if not places:
        raise WeatherError(f"ville inconnue : {city}")
    return float(places[0]["latitude"]), float(places[0]["longitude"])


def met_norway_forecast(city: str, day: dt.date, timeout: float = SOURCE_DEADLINE_S,
                        get: Callable = fetch_json) -> dict:
    """MET Norway Locationforecast 2.0 (sans clé ; User-Agent obligatoire ; coordonnées à 4 décimales).
    Les heures sont en UTC : on garde celles dont la date UTC est le jour demandé."""
    lat, lon = coordinates(city, timeout, get)
    data = get(MET_NORWAY_URL, {"lat": round(lat, 4), "lon": round(lon, 4)}, timeout)
    temperatures, probabilities = [], []
    symbols: dict[str, list[str]] = {"long": [], "hourly": []}
    for step in (data.get("properties") or {}).get("timeseries") or []:
        if not str(step.get("time", "")).startswith(day.isoformat()):
            continue
        payload = step.get("data") or {}
        temperature = _number(((payload.get("instant") or {}).get("details") or {}).get("air_temperature"))
        if temperature is not None:
            temperatures.append(temperature)
        for period in ("next_1_hours", "next_6_hours", "next_12_hours"):
            block = payload.get(period) or {}
            probability = _number((block.get("details") or {}).get("probability_of_precipitation"))
            if probability is not None:
                probabilities.append(probability)
            symbol = str((block.get("summary") or {}).get("symbol_code") or "")
            if symbol:
                symbols["hourly" if period == "next_1_hours" else "long"].append(symbol)
    if not temperatures:
        raise WeatherError(f"MET Norway : pas de prévision pour le {day.isoformat()}")
    # Pluie annoncée : symboles des périodes de 6 et 12 h (une averse d'une heure ne suffit pas), sinon horaires.
    rainy = any(word in symbol for symbol in (symbols["long"] or symbols["hourly"])
                for word in ("rain", "sleet", "thunder"))
    return {"city": city, "t_min": min(temperatures), "t_max": max(temperatures),
            "rain_probability": max(probabilities) if probabilities else None, "rain_code": rainy}


def wttr_forecast(city: str, day: dt.date, timeout: float = SOURCE_DEADLINE_S, get: Callable = fetch_json) -> dict:
    """wttr.in au format JSON (format=j1) : trois jours de prévision par ville."""
    data = get(WTTR_URL.format(city=urllib.parse.quote(city)), {"format": "j1"}, timeout)
    for entry in data.get("weather") or []:
        if entry.get("date") != day.isoformat():
            continue
        hourly = entry.get("hourly") or []
        chances = [c for c in (_number(h.get("chanceofrain")) for h in hourly) if c is not None]
        codes = {int(c) for c in (_number(h.get("weatherCode")) for h in hourly) if c is not None}
        area = ((data.get("nearest_area") or [{}])[0].get("areaName") or [{}])[0].get("value")
        return {"city": area or city, "t_min": entry.get("mintempC"), "t_max": entry.get("maxtempC"),
                "rain_probability": max(chances) if chances else None, "rain_code": bool(codes & WTTR_RAIN_CODES)}
    raise WeatherError(f"wttr.in : pas de prévision pour le {day.isoformat()}")


# --------------------------------------------------------------------------------------
# Cache (dernière prévision réussie par ville et par jour)
# --------------------------------------------------------------------------------------
class WeatherCache:
    """En mémoire, et dans un fichier JSON si `path` est donné (relu au démarrage, erreurs d'écriture ignorées)."""

    def __init__(self, path: Optional[Path] = CACHE_FILE, clock: Callable[[], float] = time.time):
        self.path, self.clock, self._lock = path, clock, threading.Lock()
        self._entries: dict = {}
        if path and Path(path).is_file():
            try:
                self._entries = json.loads(Path(path).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._entries = {}

    @staticmethod
    def key(city: str, day: dt.date) -> str:
        return f"{_plain(city)}|{day.isoformat()}"

    def get(self, city: str, day: dt.date, max_age_s: float) -> Optional[tuple[dict, float]]:
        entry = self._entries.get(self.key(city, day))
        if not entry:
            return None
        age = self.clock() - float(entry.get("saved_at", 0))
        return (dict(entry["forecast"]), age) if 0 <= age <= max_age_s else None

    def put(self, city: str, day: dt.date, forecast: dict) -> None:
        with self._lock:
            now = self.clock()
            self._entries = {k: v for k, v in self._entries.items()
                             if now - float(v.get("saved_at", 0)) <= STALE_CACHE_S}
            self._entries[self.key(city, day)] = {"saved_at": now, "forecast": forecast}
            if self.path:
                try:
                    Path(self.path).parent.mkdir(parents=True, exist_ok=True)
                    Path(self.path).write_text(json.dumps(self._entries, ensure_ascii=False), encoding="utf-8")
                except OSError:
                    pass


def offline_forecast(city: str, day: dt.date, path: Path = OFFLINE_FILE) -> dict:
    """Prévision fixe de démonstration (sans réseau), à la date demandée."""
    recorded = json.loads(Path(path).read_text(encoding="utf-8"))
    forecast = normalize({**recorded, "city": city}, city, day, "prévision enregistrée (démo hors ligne)")
    forecast["attribution"] = "valeurs fixes de weather_offline.json (aucune donnée réelle)"
    return forecast


def _age(seconds: float) -> str:
    return f"{seconds / 60:.0f} min" if seconds < 3600 else f"{seconds / 3600:.1f} h"


class RobustWeather:
    """Fournisseur météo de l'agent : weather(city, day) -> prévision au format commun, ou WeatherError."""

    def __init__(self, sources: list[tuple[str, Callable]], cache: Optional[WeatherCache] = None,
                 deadline_s: float = SOURCE_DEADLINE_S, backoff_s: float = FAILURE_BACKOFF_S,
                 clock: Callable[[], float] = time.time, offline: Optional[bool] = None,
                 offline_file: Path = OFFLINE_FILE):
        self.sources, self.deadline_s, self.backoff_s, self.clock = sources, deadline_s, backoff_s, clock
        self.cache = cache if cache is not None else WeatherCache(clock=clock)
        self.offline, self.offline_file = offline, offline_file
        self._down_until: dict[str, float] = {}

    def is_offline(self) -> bool:
        return self.offline if self.offline is not None else os.environ.get("STYLIST_WEATHER_OFFLINE") == "1"

    def __call__(self, city: str, day: dt.date) -> dict:
        if self.is_offline():
            return offline_forecast(city, day, self.offline_file)
        fresh = self.cache.get(city, day, FRESH_CACHE_S)
        if fresh:
            forecast, age = fresh
            return {**forecast, "source": f"{forecast['source']} (cache, il y a {_age(age)})"}
        failures = []
        for name, fetch in self.sources:
            if self.clock() < self._down_until.get(name, 0):
                failures.append(f"{name} : ignorée (en panne il y a moins de {self.backoff_s:g} s)")
                continue
            try:
                forecast = normalize(_with_deadline(fetch, self.deadline_s, city, day, self.deadline_s),
                                     city, day, name)
            except Exception as exc:  # réseau, DNS, TLS, HTTP, JSON, délai, valeurs nulles...
                self._down_until[name] = self.clock() + self.backoff_s
                failures.append(f"{name} : {str(exc)[:120]}")
                continue
            self._down_until.pop(name, None)
            self.cache.put(city, day, forecast)
            return {**forecast, "failures": failures} if failures else forecast
        stale = self.cache.get(city, day, STALE_CACHE_S)
        if stale:
            forecast, age = stale
            return {**forecast, "source": f"{forecast['source']} (cache de secours, il y a {_age(age)})",
                    "failures": failures}
        raise WeatherError("aucune source météo n'a répondu (" + " ; ".join(failures) + ")")
