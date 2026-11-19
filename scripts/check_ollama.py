"""Opt-in check against the real local Ollama server. Not part of the test suite.

Usage:  python scripts/check_ollama.py [--config-dir configs]
Exit code 0 if Ollama is reachable and every configured role model is pulled.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aegis.core.config import load_config  # noqa: E402
from aegis.core.llm import LLMError, OllamaClient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", default=None)
    args = parser.parse_args()

    settings = load_config(args.config_dir)
    cfg = settings.models
    print(f"Ollama URL: {cfg.ollama.base_url}")

    with OllamaClient(cfg.ollama, cfg.generation) as client:
        health = client.health()
        if not health.ok:
            print(f"FAIL  health: {health.error}")
            return 1
        print(f"OK    health: version {health.version}, {health.latency_ms} ms")

        try:
            installed = set(client.list_models())
        except LLMError as exc:
            print(f"FAIL  list models: {exc}")
            return 1

        missing = 0
        for role, model in cfg.roles.model_dump().items():
            present = model in installed
            missing += not present
            print(f"{'OK  ' if present else 'MISS'}  {role:<12} {model}")
        if missing:
            print(
                "Missing models are NOT pulled automatically. Run `ollama pull <model>` yourself."
            )
        return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
