"""Logging helpers."""
from __future__ import annotations

import logging
from logging import handlers
from pathlib import Path


def configure_logging(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = handlers.RotatingFileHandler(
        log_path, maxBytes=512000, backupCount=3
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[handler],
    )
