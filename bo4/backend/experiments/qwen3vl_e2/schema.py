"""Schéma Pydantic strict des réponses du modèle et validation.

Tous les champs sont requis, chaque valeur est une énumération fermée et tout
champ supplémentaire est refusé. Chaque réponse est revalidée, même si Ollama
contraint déjà la génération avec ce schéma.
"""

import json
from typing import Literal

from pydantic import ConfigDict, ValidationError, create_model

from experiments.qwen3vl_e2.taxonomy import DIMENSIONS, values

GarmentAttributes = create_model(
    "GarmentAttributes",
    __config__=ConfigDict(extra="forbid"),
    **{name: (Literal[values(name)], ...) for name in DIMENSIONS},
)


def ollama_format_schema():
    """Schéma JSON transmis au paramètre `format` d'Ollama."""
    return GarmentAttributes.model_json_schema()


def validate_response(text):
    """(analysable, conforme, attributs | None, message d'erreur | None)."""
    try:
        json.loads(text)
    except (TypeError, ValueError) as error:
        return False, False, None, f"JSON invalide : {error}"
    try:
        model = GarmentAttributes.model_validate_json(text)
    except ValidationError as error:
        return True, False, None, f"non conforme : {error.errors()[0]['type']} sur {error.errors()[0]['loc']}"
    return True, True, model.model_dump(), None
