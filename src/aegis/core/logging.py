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

    logger.propagate = False
    levels: list[int] = []

    if config.console:
        # stderr, so logs never mix with command output on stdout
        console = RichHandler(console=Console(stderr=True), show_path=False, rich_tracebacks=True)
        console.setLevel(config.console_level)
        logger.addHandler(console)
        levels.append(console.level)

    if config.file is not None:
        path = (
            config.file if config.file.is_absolute() or base_dir is None else base_dir / config.file
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(_FILE_FORMAT))
        file_handler.setLevel(config.level)
        logger.addHandler(file_handler)
        levels.append(file_handler.level)

    # The logger passes everything any handler wants; each handler filters for itself.
    logger.setLevel(min(levels) if levels else config.level)

    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a child of the ``aegis`` logger."""
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
