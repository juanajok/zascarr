"""#1188: una obra única no nace con #1 ni con single_issue por defecto."""
from types import SimpleNamespace

from zascarr.models import IssueFormat, SeriesKind
from zascarr.services.obra_unica import numero_y_formato_de_alta


def test_obra_unica_no_crea_single_issue_ni_numero_inventado():
    obra = SimpleNamespace(kind=SeriesKind.ONE_SHOT)
    assert numero_y_formato_de_alta(obra, "1", IssueFormat.SINGLE_ISSUE) == (
        None, IssueFormat.GRAPHIC_NOVEL)
    assert numero_y_formato_de_alta(obra, None, IssueFormat.SINGLE_ISSUE) == (
        None, IssueFormat.GRAPHIC_NOVEL)
    assert numero_y_formato_de_alta(obra, "1", IssueFormat.OMNIBUS) == (
        None, IssueFormat.OMNIBUS)
    normal = SimpleNamespace(kind=SeriesKind.REGULAR)
    assert numero_y_formato_de_alta(normal, "1", IssueFormat.SINGLE_ISSUE) == (
        "1", IssueFormat.SINGLE_ISSUE)
