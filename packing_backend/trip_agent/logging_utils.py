"""Small structured logging helpers."""

from __future__ import annotations

import json
import logging
from typing import Any


def configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def log_event(
    logger: logging.Logger,
    event: str,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Log one event with machine-friendly key=value JSON fields."""
    payload = json.dumps(fields, default=str, sort_keys=True)
    logger.log(level, "%s %s", event, payload)
