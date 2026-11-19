"""Opt-in, explicit download of the voice models named in voice.yaml.

AEGIS itself never downloads at runtime (stt.local_files_only / tts.offline). Run this
once, deliberately, to put the files in the local Hugging Face cache:

  python scripts/fetch_voice_models.py            # Whisper + Kokoro
  python scripts/fetch_voice_models.py --stt-only

Downloads: the Faster-Whisper model (base ~140 MB), Kokoro-82M weights (~330 MB) plus the
configured voice, and spaCy's small English model that Kokoro's English G2P needs (~13 MB).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aegis.core.config import load_config  # noqa: E402

WHISPER_REPOS = {  # what faster-whisper resolves short names to
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
}


def fetch_whisper(stt) -> None:
    from huggingface_hub import snapshot_download

    if Path(stt.model).is_dir():
        print(f"stt.model is a local directory, nothing to fetch: {stt.model}")
        return
    repo = WHISPER_REPOS.get(stt.model)
    if repo is None:
        raise SystemExit(f"unknown Whisper model {stt.model!r}; use one of {list(WHISPER_REPOS)}")
    path = snapshot_download(repo, cache_dir=str(stt.model_dir) if stt.model_dir else None)
    print(f"OK    Whisper {stt.model}: {path}")


def fetch_kokoro(tts) -> None:
    from huggingface_hub import hf_hub_download

    for name in ("config.json", "kokoro-v1_0.pth", f"voices/{tts.voice}.pt"):
        path = hf_hub_download(tts.repo_id, name)
        print(f"OK    Kokoro {name}: {path}")
    try:
        import spacy

        if spacy.util.is_package("en_core_web_sm"):
            print("OK    spaCy en_core_web_sm already installed")
            return
    except ImportError:
        pass
    subprocess.run([sys.executable, "-m", "spacy", "download", "en_core_web_sm"], check=True)
    print("OK    spaCy en_core_web_sm installed")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config-dir", default=None)
    parser.add_argument("--stt-only", action="store_true", help="skip Kokoro")
    args = parser.parse_args()
    voice = load_config(args.config_dir).voice
    fetch_whisper(voice.stt)
    if not args.stt_only:
        fetch_kokoro(voice.tts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
