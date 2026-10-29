"""Client HTTP minimal pour un serveur Ollama LOCAL.

Pas de méthode de téléchargement (/api/pull n'est jamais appelé) ; tout hôte
autre que la machine locale est refusé.
"""

from urllib.parse import urlparse

import requests

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class OllamaClient:
    def __init__(self, host="http://localhost:11434", timeout=120.0, session=None):
        if urlparse(host).hostname not in LOCAL_HOSTS:
            raise ValueError(f"hôte non local refusé : {host}")
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()

    def _get(self, path):
        response = self.session.get(self.host + path, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def version(self):
        return self._get("/api/version").get("version")

    def tags(self):
        return self._get("/api/tags").get("models", [])

    def ps(self):
        return self._get("/api/ps").get("models", [])

    def show(self, model):
        """Métadonnées du modèle (capacités, gabarit, paramètres) : aucune inférence."""
        response = self.session.post(self.host + "/api/show", json={"model": model}, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def unload(self, model):
        """Décharge le modèle (keep_alive=0, sans prompt) : aucune inférence."""
        response = self.session.post(self.host + "/api/generate", json={"model": model, "keep_alive": 0},
                                     timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def chat(self, model, messages, format_schema, options, think=False, keep_alive="10m"):
        payload = {"model": model, "messages": messages, "format": format_schema, "options": options,
                   "think": think, "keep_alive": keep_alive, "stream": False}
        response = self.session.post(self.host + "/api/chat", json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
