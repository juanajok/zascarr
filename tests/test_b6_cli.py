"""B6 — el informe del comando administrativo (`--json` incluido).

Nada de BD: se comprueba que el informe es serializable tal cual sale del
servicio, porque el `File.id` llega del ORM como `UUID` y `json.dumps` no lo
acepta — un fallo que solo se veía ejecutando el comando de verdad.
"""
from __future__ import annotations

import json
from uuid import uuid4

from zascarr.cli.etiquetar import _imprimir_texto, _salida_json
from zascarr.core.comicinfo_write import Accion, CampoPlan
from zascarr.services.tagger import (
    ESCRITO,
    INVALIDO,
    PREVISTO,
    SALTADO,
    InformeEtiquetado,
    ResultadoEtiquetado,
)

CAMPOS = [
    CampoPlan("Series", Accion.CAMBIA, None, "Thorgal"),
    CampoPlan("Summary", Accion.CONSERVA, "lo mío", "Resumen de ZascArr"),
    CampoPlan("LanguageISO", Accion.SIN_DATO, None, None),
    CampoPlan("Number", Accion.BLOQUEADO, "1", "1"),
]


def _informe() -> InformeEtiquetado:
    """Con `file_id` como UUID a propósito: es lo que entrega el ORM."""
    informe = InformeEtiquetado(escritos=1, previstos=1, saltados=1, invalidos=1)
    informe.resultados = [
        ResultadoEtiquetado(uuid4(), "a.cbz", ESCRITO, CAMPOS, reconciliado=True),
        ResultadoEtiquetado(uuid4(), "b.cbz", PREVISTO, CAMPOS),
        ResultadoEtiquetado(uuid4(), "c.cbz", SALTADO, [], "ya al día"),
        ResultadoEtiquetado(uuid4(), "d.cbz", INVALIDO, [], "ComicInfo.xml inválido"),
    ]
    return informe


def test_el_informe_json_es_serializable(capsys):
    _salida_json(_informe(), aplicar=False)
    datos = json.loads(capsys.readouterr().out)

    assert datos["modo"] == "dryrun"
    assert datos["resumen"]["escritos"] == 1
    assert len(datos["resultados"]) == 4
    assert isinstance(datos["resultados"][0]["file_id"], str)
    assert datos["resultados"][0]["reconciliado"] is True
    assert datos["resultados"][0]["campos"][0] == {
        "tag": "Series", "accion": "cambia", "actual": None, "nuevo": "Thorgal",
    }


def test_el_informe_json_marca_el_modo_apply(capsys):
    _salida_json(_informe(), aplicar=True)
    assert json.loads(capsys.readouterr().out)["modo"] == "apply"


def test_el_informe_de_texto_no_revienta(capsys):
    _imprimir_texto(_informe(), aplicar=False)
    salida = capsys.readouterr().out

    assert "Thorgal" in salida
    assert "se conserva (procedencia desconocida)" in salida
    assert "sin dato (no se inventa)" in salida
    assert "bloqueado (locked_fields)" in salida
    assert "Nada se ha escrito. Para aplicarlo: --apply" in salida


def test_el_resumen_cuenta_los_ya_revisados():
    informe = InformeEtiquetado(ya_revisados=7)
    assert "7 ya revisados antes" in informe.resumen()


def test_file_id_del_orm_se_normaliza_a_texto():
    """Sin esto, `--json` revienta con «Object of type UUID is not JSON
    serializable» (visto ejecutando el comando contra Postgres real)."""
    identificador = uuid4()
    resultado = ResultadoEtiquetado(identificador, "a.cbz", ESCRITO)
    assert resultado.file_id == str(identificador)
    assert json.dumps({"file_id": resultado.file_id})
