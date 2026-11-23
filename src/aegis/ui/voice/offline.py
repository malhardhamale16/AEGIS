"""Keep Hugging Face libraries offline.

``huggingface_hub`` reads ``HF_HUB_OFFLINE`` once, when it is first imported. Setting the
environment variable after something (faster-whisper, kokoro, transformers) has imported it
has no effect, so we also flip the already-loaded constant.
"""

from __future__ import annotations

import os
import sys


def force_hf_offline() -> None:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    constants = sys.modules.get("huggingface_hub.constants")
    if constants is not None:
        constants.HF_HUB_OFFLINE = True
