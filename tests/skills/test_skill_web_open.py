import pytest
from pydantic import ValidationError

from aegis.models.skill import SkillError
from aegis.skills.web_open import WebOpenInput, WebOpenSkill


def test_opens_https_url():
    opened = []
    skill = WebOpenSkill(opener=lambda u: opened.append(u) or True)
    out = skill.run(WebOpenInput(url=" https://example.com/x "), dry_run=False)
    assert out.opened and opened == ["https://example.com/x"]


@pytest.mark.parametrize(
    "url", ["file:///C:/Windows/system32", "javascript:alert(1)", "example.com", "http://"]
)
def test_non_http_urls_rejected(url):
    with pytest.raises(ValidationError):
        WebOpenInput(url=url)


def test_dry_run_does_not_open():
    opened = []
    out = WebOpenSkill(opener=opened.append).run(WebOpenInput(url="http://a.b"), dry_run=True)
    assert out.opened is False and opened == []


def test_browser_failure():
    with pytest.raises(SkillError):
        WebOpenSkill(opener=lambda u: False).run(WebOpenInput(url="http://a.b"), dry_run=False)
