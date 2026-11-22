"""Alta de una obra única (ADR 0022, #1188).

Una obra autoconclusiva no es una grapa y no lleva número inventado: si la
asignación no trae un número de fuente, se guarda `issue_number=NULL` y un
formato no-grapa (`graphic_novel` por defecto, o el que se haya elegido).
"""
from __future__ import annotations

from zascarr.models import IssueFormat, SeriesKind


def numero_y_formato_de_alta(serie, issue_number: str | None,
                             formato: IssueFormat | None) -> tuple[str | None, IssueFormat | None]:
    """Número y formato con los que se crea el número de una asignación."""
    if getattr(serie, "kind", None) == SeriesKind.ONE_SHOT:
        if formato in (None, IssueFormat.SINGLE_ISSUE):
            formato = IssueFormat.GRAPHIC_NOVEL
        return None, formato
    return issue_number, formato
