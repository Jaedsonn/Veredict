import importlib.resources
from pathlib import Path

import pytest
from jinja2 import FileSystemLoader, TemplateNotFound, UndefinedError
from pydantic import JsonValue

from notification_service.adapters.jinja_renderer import JinjaEmailRenderer
from notification_service.catalog import WelcomeData, build_registry
from notification_service.domain import RenderedEmail, TemplateRenderError
from notification_service.registry import TemplateRegistry, TemplateSpec

SNAPSHOTS = Path(__file__).parent / "snapshots"
WEB_URL = "http://localhost:3000"
VERIFICATION: dict[str, JsonValue] = {"name": "João", "code": "042137", "expires_in_minutes": 15}
XSS_NAME = '<script>alert(1)</script> & "x"'


def _render(template: str, data: dict[str, JsonValue], web_url: str = WEB_URL) -> RenderedEmail:
    renderer = JinjaEmailRenderer(web_url=web_url)
    return renderer.render(template, build_registry().parse(template, data))


@pytest.mark.parametrize(
    ("template", "data"),
    [("email_verification", VERIFICATION), ("welcome", {"name": "João"})],
)
@pytest.mark.parametrize("part", ["txt", "html"])
def test_bodies_match_reviewed_snapshots(
    template: str, data: dict[str, JsonValue], part: str
) -> None:
    rendered = _render(template, data)
    body = rendered.text if part == "txt" else rendered.html

    assert body == (SNAPSHOTS / f"{template}.body.{part}").read_text(encoding="utf-8")


def test_subjects_are_exact() -> None:
    assert _render("email_verification", VERIFICATION).subject == (
        "Seu código de verificação Veriditi"
    )
    assert _render("welcome", {"name": "Ana"}).subject == "Bem-vindo(a) ao Veriditi"


def test_one_minute_is_singular() -> None:
    rendered = _render("email_verification", {**VERIFICATION, "expires_in_minutes": 1})

    assert "expira em 1 minuto." in rendered.text
    assert "expira em 1 minuto." in rendered.html


@pytest.mark.parametrize("template", ["email_verification", "welcome"])
def test_html_escapes_name_and_text_keeps_it_raw(template: str) -> None:
    data: dict[str, JsonValue] = {"name": XSS_NAME}
    if template == "email_verification":
        data = {**VERIFICATION, **data}

    rendered = _render(template, data)

    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; &#34;x&#34;" in rendered.html
    assert "<script>" not in rendered.html
    assert f"Olá, {XSS_NAME}!" in rendered.text


def test_links_use_web_url() -> None:
    verification = _render("email_verification", VERIFICATION, web_url="https://veriditi.app")
    welcome = _render("welcome", {"name": "Ana"}, web_url="https://veriditi.app")

    assert 'href="https://veriditi.app/verificar-email"' in verification.html
    assert "https://veriditi.app/verificar-email" in verification.text
    assert 'href="https://veriditi.app/entrar"' in welcome.html
    assert "https://veriditi.app/entrar" in welcome.text


def test_body_repr_hides_the_code() -> None:
    assert "042137" not in repr(_render("email_verification", VERIFICATION))


def _write(root: Path, name: str, subject: str, text: str = "x", html: str = "<p>x</p>") -> None:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "subject.txt").write_text(subject, encoding="utf-8")
    (folder / "body.txt").write_text(text, encoding="utf-8")
    (folder / "body.html").write_text(html, encoding="utf-8")


def _fs_render(tmp_path: Path, name: str = "welcome", **data: JsonValue) -> RenderedEmail:
    renderer = JinjaEmailRenderer(web_url=WEB_URL, loader=FileSystemLoader(tmp_path))
    registry = TemplateRegistry([TemplateSpec(name, WelcomeData)])
    return renderer.render(name, registry.parse(name, data or {"name": "Ana"}))


@pytest.mark.parametrize(
    "subject",
    ["Olá\n{{ name }}", "Olá\r{{ name }}", "Olá {{ name }}", "Olá\x1b{{ name }}", "   \n"],
    ids=["lf", "cr", "line-separator", "escape", "blank"],
)
def test_subject_with_line_break_or_control_char_is_a_render_error(
    tmp_path: Path, subject: str
) -> None:
    _write(tmp_path, "welcome", subject)

    with pytest.raises(TemplateRenderError):
        _fs_render(tmp_path)


def test_subject_trailing_newline_is_stripped_and_bodies_end_with_one(tmp_path: Path) -> None:
    _write(tmp_path, "welcome", "Oi, {{ name }}\n\n", text="corpo\n\n\n", html="<p>x</p>")

    rendered = _fs_render(tmp_path)

    assert rendered.subject == "Oi, Ana"
    assert rendered.text == "corpo\n"
    assert rendered.html == "<p>x</p>\n"


def test_undefined_variable_fails_instead_of_rendering_empty(tmp_path: Path) -> None:
    _write(tmp_path, "welcome", "Oi", text="{{ code }}")

    with pytest.raises(UndefinedError):
        _fs_render(tmp_path)


def test_check_fails_when_a_file_is_missing(tmp_path: Path) -> None:
    _write(tmp_path, "welcome", "Oi")
    (tmp_path / "welcome" / "body.html").unlink()
    renderer = JinjaEmailRenderer(web_url=WEB_URL, loader=FileSystemLoader(tmp_path))

    with pytest.raises(TemplateNotFound):
        renderer.check(["welcome"])


def test_check_accepts_every_registered_template() -> None:
    JinjaEmailRenderer(web_url=WEB_URL).check(build_registry().names)


def test_template_files_ship_inside_the_package() -> None:
    root = importlib.resources.files("notification_service") / "templates"

    assert (root / "_layout.html").is_file()
    for name in build_registry().names:
        for filename in ("subject.txt", "body.txt", "body.html"):
            assert (root / name / filename).is_file(), f"{name}/{filename}"


@pytest.mark.parametrize("template", ["email_verification", "welcome"])
def test_line_breaks_in_name_never_reach_subject_or_bodies(template: str) -> None:
    data: dict[str, JsonValue] = {"name": "Ana\r\nBcc: x@evil.com \tSilva"}
    if template == "email_verification":
        data = {**VERIFICATION, **data}

    rendered = _render(template, data)

    assert "Olá, Ana Bcc: x@evil.com Silva!" in rendered.text
    assert "Olá, Ana Bcc: x@evil.com Silva!" in rendered.html
    for part in (rendered.subject, rendered.text, rendered.html):
        assert "\r" not in part
        assert " " not in part
        assert "\t" not in part
    assert "\n" not in rendered.subject
