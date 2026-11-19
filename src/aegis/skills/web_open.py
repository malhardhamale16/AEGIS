"""web_open: open an http(s) URL in the default browser."""

from __future__ import annotations

import webbrowser
from collections.abc import Callable
from urllib.parse import urlparse

from pydantic import Field, field_validator

from aegis.models.skill import RiskLevel, Skill, SkillError, SkillIO

UrlOpener = Callable[[str], bool]


class WebOpenInput(SkillIO):
    url: str = Field(..., description="Absolute http or https URL")

    @field_validator("url")
    @classmethod
    def _http_only(cls, v: str) -> str:
        v = v.strip()
        parsed = urlparse(v)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("only absolute http:// or https:// URLs are allowed")
        return v


class WebOpenOutput(SkillIO):
    url: str
    opened: bool


class WebOpenSkill(Skill):
    name = "web_open"
    description = "Open an http(s) URL in the default web browser."
    risk = RiskLevel.SAFE
    input_model = WebOpenInput
    output_model = WebOpenOutput

    def __init__(self, opener: UrlOpener = webbrowser.open) -> None:
        self._opener = opener

    def run(self, data: WebOpenInput, *, dry_run: bool) -> WebOpenOutput:
        if dry_run:
            return WebOpenOutput(url=data.url, opened=False)
        if not self._opener(data.url):
            raise SkillError("no web browser could be opened")
        return WebOpenOutput(url=data.url, opened=True)
