"""Logging setup driven by ``LoggingConfig``."""

from __future__ import annotations

import logging
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

from aegis.models.config import LoggingConfig

ROOT_LOGGER_NAME = "aegis"
_FILE_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def setup_logging(config: LoggingConfig, base_dir: Path | None = None) -> logging.Logger:
    """Configure the ``aegis`` logger. Safe to call repeatedly (handlers are replaced)."""
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    logger.setLevel(config.level)
    logger.propagate = False

    if config.console:
        # stderr, so logs never mix with command output on stdout
        logger.addHandler(
            RichHandler(console=Console(stderr=True), show_path=False, rich_tracebacks=True)
        )

    if config.file is not None:
        path = (
            config.file if config.file.is_absolute() or base_dir is None else base_dir / config.file
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))
        logger.addHandler(file_handler)

    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child of the ``aegis`` logger."""
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
