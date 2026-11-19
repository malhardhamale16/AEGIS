# AEGIS

A local-first AI assistant for Windows. Tell it what you want, typed or spoken, and agents
carry it out through small, typed skills, behind a permission gate.

- **Local only.** LLM inference through [Ollama](https://ollama.com) on `127.0.0.1`.
  Speech-to-text (Faster-Whisper) and text-to-speech (Kokoro) run from local files. No cloud
  APIs, no telemetry, no runtime downloads.
- **Safe by default.** State-changing skills only *simulate* until you turn dry-run off, and
  even then each one asks before acting.
- **Configuration-driven.** Everything lives in `configs/*.yaml`, validated on load.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design and diagrams.

## Requirements

- Windows 10/11, Python 3.11+
- [Ollama](https://ollama.com) running locally, with a chat model pulled
- For voice: a microphone; headphones recommended if you use barge-in

## Setup

Create and activate a virtual environment wherever you keep them, then install from the
project folder:

```powershell
py -3.12 -m venv $env:USERPROFILE\venvs\aegis
& $env:USERPROFILE\venvs\aegis\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Pull the model named in `configs/models.yaml` (default `llama3.1:8b`) and check everything:

```powershell
ollama pull llama3.1:8b
aegis doctor
```

### Voice (optional)

```powershell
pip install -e ".[voice]"          # mic, VAD, Faster-Whisper
pip install -e ".[speak]"          # Kokoro TTS for spoken replies (pulls in torch, CPU)
python scripts\fetch_voice_models.py   # one-time, explicit model download (~500 MB)
python scripts\diagnose_audio.py --list
python scripts\check_voice_models.py
```

`fetch_voice_models.py` is the only thing that downloads models. AEGIS itself loads them
with `stt.local_files_only: true` and `tts.offline: true`.

## Usage

```powershell
aegis skills list                         # what AEGIS can do, with risk levels
aegis skills show write_file              # full input/output schema

aegis run "how much memory does this PC have"
aegis run "write a file shopping.txt with eggs and milk"            # simulated (dry-run)
aegis run "write a file shopping.txt with eggs and milk" --execute  # asks y/N, then writes
aegis run "list chrome processes" --json

aegis chat                                # interactive; /help, /reset, /exit
aegis voice                               # talk; replies printed
aegis voice --speak                       # talk; replies spoken (Ctrl+C to stop)

aegis doctor                              # config, Ollama, models, skills, voice packages
```

Without an install, `python -m aegis ...` works from the project folder with
`$env:PYTHONPATH = "src"`.

## Skills

| Skill | Risk | Does |
|---|---|---|
| `system_info` | safe | OS, hostname, CPU, memory, Python version |
| `file_search` | safe | find files by name pattern under a folder |
| `clipboard_read` | safe | read clipboard text (length-capped) |
| `list_processes` | safe | running processes, optional name filter |
| `open_app` | safe | launch an app **from the allow-list** in `skills.yaml` |
| `web_open` | safe | open an `http(s)` URL in the default browser |
| `write_file` | confirm | write a text file **inside `write_file.allowed_roots` only** |

Risk can be raised (never lowered) per skill in `skills.yaml`, e.g.
`overrides: { open_app: { risk: confirm } }`.

## Configuration

| File | Main settings |
|---|---|
| `configs/aegis.yaml` | `safety.dry_run`, `safety.require_confirmation`, logging, planner/executor limits |
| `configs/models.yaml` | Ollama URL (loopback only), timeouts, model per role |
| `configs/skills.yaml` | enabled skills, overrides, app allow-list, write roots, result caps |
| `configs/voice.yaml` | input device (default **1**) and host API (default **MME**), 16 kHz / 30 ms frames, VAD timing, Whisper model (`base`), Kokoro voice, barge-in |

The audio device and host API are never switched automatically. If device 1 isn't an MME
input on your machine, `aegis voice` stops with a message; pick the right index from
`python scripts\diagnose_audio.py --list`.

Use another config folder with `aegis --config-dir path\to\configs ...` or
`$env:AEGIS_CONFIG_DIR`.

## Development

```powershell
pytest          # no Ollama, mic, speakers or models needed
ruff check .
ruff format --check .
```

Opt-in checks against real hardware and services:

| Script | Checks |
|---|---|
| `scripts/check_ollama.py` | Ollama reachable, configured models pulled |
| `scripts/diagnose_audio.py` | `--list` devices; or record 5 s and report frames, drops, levels, VAD, turns (audio never saved) |
| `scripts/check_voice_models.py` | offline Kokoro → Whisper round trip; `--play` to hear it |

## Project layout

```
src/aegis/
  models/   pydantic contracts (config, Skill, Plan, results)
  core/     config, logging, event bus, Ollama client, skill registry, permission gate
  agents/   planner, executor, conversation
  skills/   built-in skills
  apps/     runtime wiring, doctor checks
  ui/       cli/ (Typer + rich), voice/ (capture, VAD, turns, STT, TTS, playback, session)
configs/    aegis.yaml, models.yaml, skills.yaml, voice.yaml
tests/      mirrors src/aegis
scripts/    opt-in diagnostics and the explicit model fetcher
docs/       ARCHITECTURE.md
```

## Limitations

- Plan steps can't use an earlier step's output yet.
- No acoustic echo cancellation: with speakers, AEGIS can interrupt itself. Use headphones
  or set `barge_in.enabled: false`.
- Confirmations happen at the terminal (`y/N`), not by voice.
- Kokoro on CPU is about real-time or slower; replies start after the first sentence.
