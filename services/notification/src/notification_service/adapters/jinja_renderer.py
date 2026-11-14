import unicodedata
from collections.abc import Iterable
from typing import Final

from jinja2 import BaseLoader, Environment, PackageLoader, StrictUndefined, select_autoescape
from pydantic import BaseModel

from notification_service.domain import RenderedEmail, TemplateRenderError

TEMPLATE_FILES: Final = ("subject.txt", "body.txt", "body.html")
# Separadores de linha que não são Cc mas quebrariam o header Subject
_LINE_SEPARATORS: Final = frozenset({" ", " "})


class JinjaEmailRenderer:
    """Templates do pacote; o data só entra como contexto, nunca é compilado como template"""

    def __init__(self, *, web_url: str, loader: BaseLoader | None = None) -> None:
        self._env = Environment(
            loader=loader or PackageLoader("notification_service", "templates"),
            # Só o .html escapa: no texto puro o nome sai como foi digitado
            autoescape=select_autoescape(
                enabled_extensions=("html",), default_for_string=False, default=False
            ),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            auto_reload=False,
        )
        self._env.globals["web_url"] = web_url

    def check(self, names: Iterable[str]) -> None:
        """Fail-fast na subida: pasta ou arquivo faltando não espera o primeiro envio"""
        for name in names:
            for filename in TEMPLATE_FILES:
                self._env.get_template(f"{name}/{filename}")

    def render(self, template: str, data: BaseModel) -> RenderedEmail:
        context = data.model_dump()
        subject = self._render(template, "subject.txt", context).strip()
        _check_subject(subject)
        return RenderedEmail(
            subject=subject,
            text=_one_trailing_newline(self._render(template, "body.txt", context)),
            html=_one_trailing_newline(self._render(template, "body.html", context)),
        )

    def _render(self, template: str, filename: str, context: dict[str, object]) -> str:
        return self._env.get_template(f"{template}/{filename}").render(context)


def _check_subject(subject: str) -> None:
    """Assunto vira header: quebra de linha permitiria injetar outro header"""
    if not subject:
        raise TemplateRenderError("assunto vazio")
    if any(unicodedata.category(c) == "Cc" or c in _LINE_SEPARATORS for c in subject):
        raise TemplateRenderError("assunto com caractere de controle ou quebra de linha")


def _one_trailing_newline(body: str) -> str:
    return body.rstrip() + "\n"
