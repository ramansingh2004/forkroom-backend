from pathlib import Path
from typing import Any, cast

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML


class DecisionPdfRenderer:
    def __init__(self) -> None:
        template_directory = Path(__file__).resolve().parent.parent / "templates"
        self._environment = Environment(
            loader=FileSystemLoader(template_directory),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def render(
        self,
        snapshot: dict[str, object],
        *,
        document_hash: str,
        snapshot_version: int,
        locked_at: str,
    ) -> bytes:
        template = self._environment.get_template("decision_export.html")
        html = template.render(
            decision=self._mapping(snapshot.get("decision")),
            approved=self._mapping(snapshot.get("approved_proposal")),
            voting=self._mapping(snapshot.get("voting_result")),
            dissent=self._mapping(snapshot.get("dissent")),
            document_hash=document_hash,
            snapshot_version=snapshot_version,
            locked_at=locked_at,
        )
        return cast(
            bytes,
            HTML(string=html, base_url=str(Path(__file__).resolve().parent.parent)).write_pdf(),
        )

    @staticmethod
    def _mapping(value: object) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}
