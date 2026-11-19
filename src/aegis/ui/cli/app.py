"""``aegis`` command line: chat, run, voice, skills list/show, doctor."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.text import Text

from aegis.apps.doctor import Status, run_checks
from aegis.apps.runtime import build_registry, build_runtime
from aegis.core.config import ConfigError, load_config, resolve_config_dir
from aegis.core.llm import OllamaClient
from aegis.core.logging import setup_logging
from aegis.models.config import Settings
from aegis.models.permission import ConfirmRequest
from aegis.ui.cli.render import (
    confirm_panel,
    doctor_table,
    dry_run_banner,
    render_reply,
    skills_table,
)
from aegis.ui.voice.audio import AudioDeviceError
from aegis.ui.voice.factory import VoiceComponents, VoiceSetupError, build_voice
from aegis.ui.voice.session import VoiceSession

# Builds the LLM client (and, for doctor, the health/list_models client) from settings.
LLMFactory = Callable[[Settings], Any]
# Builds mic/VAD/STT (+ TTS/player when speak=True).
VoiceFactory = Callable[[Settings, bool], VoiceComponents]

VOICE_STYLES = {"you": "bold cyan", "aegis": "bold magenta", "status": "dim", "error": "red"}


def default_voice_factory(settings: Settings, speak: bool) -> VoiceComponents:
    return build_voice(settings, speak=speak)


CHAT_HELP = "Commands: /help, /reset (clear history), /exit"


def default_llm_factory(settings: Settings) -> OllamaClient:
    return OllamaClient(settings.models.ollama, settings.models.generation)


def make_confirm(console: Console) -> Callable[[ConfirmRequest], bool]:
    """Interactive y/N prompt on stderr. Anything but an explicit yes denies."""

    def confirm(request: ConfirmRequest) -> bool:
        console.print(confirm_panel(request))
        try:
            return typer.confirm("Allow this action?", default=False, err=True)
        except (typer.Abort, EOFError):
            return False

    return confirm


ExecuteOpt = Annotated[
    bool | None,
    typer.Option(
        "--execute/--dry-run",
        help="Act for real (confirm-level skills still ask) or force a simulation. "
        "Default comes from aegis.yaml (dry-run).",
    ),
]
JsonOpt = Annotated[bool, typer.Option("--json", help="Print machine-readable JSON.")]


def create_app(
    llm_factory: LLMFactory = default_llm_factory,
    voice_factory: VoiceFactory = default_voice_factory,
) -> typer.Typer:
    app = typer.Typer(
        help="AEGIS: local-first AI assistant for Windows.",
        no_args_is_help=True,
        add_completion=False,
    )
    skills_app = typer.Typer(help="Inspect available skills.", no_args_is_help=True)
    app.add_typer(skills_app, name="skills")

    out = Console(highlight=False)
    err = Console(stderr=True, highlight=False)

    @app.callback()
    def _root(
        ctx: typer.Context,
        config_dir: Annotated[
            Path | None,
            typer.Option("--config-dir", "-c", help="Config directory (default: ./configs)."),
        ] = None,
    ) -> None:
        ctx.obj = {"config_dir": config_dir}

    def load(ctx: typer.Context) -> Settings:
        config_dir = (ctx.obj or {}).get("config_dir")
        try:
            settings = load_config(config_dir)
        except ConfigError as exc:
            err.print(Text(str(exc), style="red"))
            raise typer.Exit(2) from exc
        base = resolve_config_dir(config_dir).resolve().parent
        setup_logging(settings.aegis.logging, base_dir=base)
        return settings

    def dry_run_flag(execute: bool | None) -> bool | None:
        return None if execute is None else not execute

    # ------------------------------------------------------------------- run

    @app.command()
    def run(
        ctx: typer.Context,
        instruction: Annotated[str, typer.Argument(help="What you want AEGIS to do.")],
        execute: ExecuteOpt = None,
        as_json: JsonOpt = False,
    ) -> None:
        """Plan and run a single instruction."""
        settings = load(ctx)
        dry_run = dry_run_flag(execute)
        runtime = build_runtime(settings, llm=llm_factory(settings), confirm=make_confirm(err))
        try:
            if not as_json and (settings.aegis.safety.dry_run if dry_run is None else dry_run):
                dry_run_banner(err)
            reply = runtime.conversation.handle(instruction, dry_run=dry_run)
        finally:
            runtime.close()
        if as_json:
            typer.echo(reply.model_dump_json(indent=2))
        else:
            render_reply(out, reply)
        failed = reply.error is not None or (reply.result is not None and not reply.result.ok)
        if failed:
            raise typer.Exit(1)

    # ------------------------------------------------------------------ chat

    @app.command()
    def chat(ctx: typer.Context, execute: ExecuteOpt = None) -> None:
        """Interactive conversation. Type /exit to quit."""
        settings = load(ctx)
        dry_run = dry_run_flag(execute)
        runtime = build_runtime(settings, llm=llm_factory(settings), confirm=make_confirm(err))
        out.print(Text(f"{settings.aegis.app.name} chat. {CHAT_HELP}", style="bold"))
        if settings.aegis.safety.dry_run if dry_run is None else dry_run:
            dry_run_banner(out)
        try:
            while True:
                try:
                    line = out.input(Text("you> ", style="bold cyan")).strip()
                except (EOFError, KeyboardInterrupt):
                    out.print()
                    break
                if not line:
                    continue
                if line in {"/exit", "/quit"}:
                    break
                if line == "/help":
                    out.print(CHAT_HELP)
                    continue
                if line == "/reset":
                    runtime.conversation.reset()
                    out.print(Text("History cleared.", style="dim"))
                    continue
                render_reply(out, runtime.conversation.handle(line, dry_run=dry_run))
        finally:
            runtime.close()
        out.print(Text("Bye.", style="dim"))

    # ----------------------------------------------------------------- voice

    @app.command()
    def voice(
        ctx: typer.Context,
        speak: Annotated[
            bool, typer.Option("--speak/--no-speak", help="Speak replies aloud with Kokoro.")
        ] = False,
        execute: ExecuteOpt = None,
        seconds: Annotated[
            float | None, typer.Option("--seconds", help="Stop after N seconds.", min=0.1)
        ] = None,
    ) -> None:
        """Talk to AEGIS through the microphone. Ctrl+C to stop."""
        settings = load(ctx)
        dry_run = dry_run_flag(execute)
        try:
            parts = voice_factory(settings, speak)
        except (VoiceSetupError, AudioDeviceError) as exc:
            err.print(Text(f"Voice setup failed: {exc}", style="red"))
            raise typer.Exit(1) from exc

        runtime = build_runtime(settings, llm=llm_factory(settings), confirm=make_confirm(err))

        def show(kind: str, text: str) -> None:
            label = {"status": "  ", "error": "error: "}.get(kind, f"{kind}> ")
            out.print(Text(label, style=VOICE_STYLES[kind]) + Text(text))

        v = settings.voice
        session = VoiceSession(
            parts.capture(settings, bus=runtime.bus),
            parts.stt,
            runtime.conversation,
            barge_in=v.barge_in,
            frame_ms=v.audio.frame_ms,
            tts=parts.tts,
            player=parts.player,
            on_event=show,
            dry_run=dry_run,
        )
        mode = "speaking replies" if speak else "text replies only (use --speak for audio)"
        out.print(
            Text(
                f"Listening on device {v.audio.input_device} via {v.audio.host_api}; {mode}. "
                "Ctrl+C to stop.",
                style="bold",
            )
        )
        if settings.aegis.safety.dry_run if dry_run is None else dry_run:
            dry_run_banner(out)

        stop = threading.Event()
        deadline = time.monotonic() + seconds if seconds else None
        try:
            stats = session.run(stop, deadline=deadline)
        except KeyboardInterrupt:
            stop.set()
            stats = session.stats
        except AudioDeviceError as exc:
            err.print(Text(f"Audio input failed: {exc}", style="red"))
            raise typer.Exit(1) from exc
        finally:
            runtime.close()
        out.print(
            Text(
                f"Stopped. utterances={stats.utterances} replies={stats.replies} "
                f"spoken={stats.spoken} interruptions={stats.barge_ins} errors={stats.errors}",
                style="dim",
            )
        )

    # ---------------------------------------------------------------- skills

    @skills_app.command("list")
    def skills_list(ctx: typer.Context, as_json: JsonOpt = False) -> None:
        """List enabled skills with their risk level."""
        infos = build_registry(load(ctx)).describe()
        if as_json:
            typer.echo(json.dumps([i.model_dump(mode="json") for i in infos], indent=2))
        else:
            out.print(skills_table(infos))

    @skills_app.command("show")
    def skills_show(
        ctx: typer.Context, name: Annotated[str, typer.Argument(help="Skill name.")]
    ) -> None:
        """Show one skill's description and input/output schema."""
        registry = build_registry(load(ctx))
        if name not in registry:
            err.print(Text(f"Unknown or disabled skill: {name}", style="red"))
            raise typer.Exit(1)
        typer.echo(registry.info(name).model_dump_json(indent=2))

    # ---------------------------------------------------------------- doctor

    @app.command()
    def doctor(ctx: typer.Context, as_json: JsonOpt = False) -> None:
        """Check config, Ollama, models and skills. Exit code 1 if anything fails."""
        settings = load(ctx)
        client = llm_factory(settings)
        try:
            checks = run_checks(settings, client)
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
        if as_json:
            typer.echo(
                json.dumps(
                    [
                        {"name": c.name, "status": c.status.value, "detail": c.detail}
                        for c in checks
                    ],
                    indent=2,
                )
            )
        else:
            out.print(doctor_table(checks))
        if any(c.status is Status.FAIL for c in checks):
            raise typer.Exit(1)

    return app


def main() -> None:
    create_app()()


if __name__ == "__main__":
    main()
