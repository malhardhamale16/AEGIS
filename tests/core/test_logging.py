import logging
from pathlib import Path

from aegis.core.logging import ROOT_LOGGER_NAME, get_logger, setup_logging
from aegis.models.config import LoggingConfig


def _flush(logger: logging.Logger) -> None:
    for h in logger.handlers:
        h.flush()


def test_level_applied(tmp_path):
    logger = setup_logging(LoggingConfig(level="DEBUG", console=False, file=None))
    assert logger.level == logging.DEBUG
    assert logger.name == ROOT_LOGGER_NAME


def test_file_handler_writes_relative_to_base_dir(tmp_path):
    cfg = LoggingConfig(level="INFO", console=False, file=Path("logs/test.log"))
    logger = setup_logging(cfg, base_dir=tmp_path)
    get_logger("unit").info("hello world")
    _flush(logger)
    content = (tmp_path / "logs" / "test.log").read_text(encoding="utf-8")
    assert "hello world" in content
    assert "aegis.unit" in content


def test_level_filters_messages(tmp_path):
    cfg = LoggingConfig(level="WARNING", console=False, file=Path("a.log"))
    logger = setup_logging(cfg, base_dir=tmp_path)
    get_logger("unit").info("quiet")
    get_logger("unit").warning("loud")
    _flush(logger)
    content = (tmp_path / "a.log").read_text(encoding="utf-8")
    assert "loud" in content
    assert "quiet" not in content


def test_repeated_setup_does_not_duplicate_handlers(tmp_path):
    cfg = LoggingConfig(console=False, file=Path("b.log"))
    setup_logging(cfg, base_dir=tmp_path)
    logger = setup_logging(cfg, base_dir=tmp_path)
    assert len(logger.handlers) == 1


def test_no_outputs_falls_back_to_null_handler():
    logger = setup_logging(LoggingConfig(console=False, file=None))
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0], logging.NullHandler)
