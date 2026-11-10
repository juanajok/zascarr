"""#479/BL-CNV2: lote de conversión CBR→CBZ (selección, omisiones y parada).

Pruebas puras del bucle del lote: se sustituyen la consulta de ficheros, la vista previa y la
confirmación por dobles, así que no tocan disco, BD ni `unar`. La conversión de verdad por archivo
la cubren `tests/test_conversion_*.py` (#478).
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from zascarr.services.conversion import (
    LOTE_ESCANEO_MAX,
    ConversionDeArchivo,
    MotivoConversion,
    ResultadoConversion,
    VistaConversion,
)


def _vista(fid, *, puede: bool = True, advertencia: str | None = None) -> VistaConversion:
    return VistaConversion(
        file_id=str(fid), serie_id=None, nombre_original=f"Tebeo {fid}.cbr",
        nombre_nuevo=f"Tebeo {fid}.cbz", metodo="recomprimir",
        tamano_entrada=1024, estimado_salida=2048, espacio_libre=None, necesario=2048,
        puede_convertir=puede,
        motivo=None if puede else MotivoConversion.ILEGIBLE.value,
        mensaje="Se puede convertir." if puede else "El CBR está dañado.",
        advertencia=advertencia, forzable=advertencia is not None, token=f"tok-{fid}")


def _resultado(file_id, *, resultado: str, motivo: str | None = None,
               mensaje: str = "Hecho.") -> ResultadoConversion:
    return ResultadoConversion(1, "conversion", "op", str(file_id), resultado, motivo, mensaje)


class _Lote(ConversionDeArchivo):
    def __init__(self, filas, vistas, respuestas=None):
        self._filas = filas
        self._vistas = vistas
        self._respuestas = respuestas or {}
        self.confirmadas: list[tuple[str, bool]] = []

    async def _cbrs_de_serie(self, serie_id):
        return [(fid, f"/lib/{fid}.cbr") for fid in self._filas]

    async def previsualizar(self, serie_id, file_id):
        return self._vistas[file_id]

    async def confirmar(self, token, *, forzar_compartido=False, **_kw):
        self.confirmadas.append((token, forzar_compartido))
        return self._respuestas[token]


@pytest.mark.asyncio
async def test_llena_la_tanda_y_omite_con_motivo():
    filas = [uuid4() for _ in range(8)]
    vistas = {
        filas[0]: _vista(filas[0]),
        filas[1]: _vista(filas[1], puede=False),
        filas[2]: _vista(filas[2]),
        filas[3]: _vista(filas[3], advertencia="Parece compartido."),
        filas[4]: _vista(filas[4]),
    }
    servicio = _Lote(filas, vistas)
    lote = await servicio.previsualizar_lote(uuid4(), limite=3)

    assert lote.total_cbr == 8 and lote.escaneados == 5 and lote.limite == 3
    assert [v.file_id for v in lote.vistas] == [str(filas[0]), str(filas[2]), str(filas[4])]
    assert [v.file_id for v in lote.bloqueadas] == [str(filas[1])]
    assert [v.file_id for v in lote.compartidas] == [str(filas[3])]


@pytest.mark.asyncio
async def test_el_tope_de_escaneo_evita_recorrer_la_serie_entera():
    filas = [uuid4() for _ in range(100)]
    vistas = {fid: _vista(fid, puede=False) for fid in filas}
    lote = await _Lote(filas, vistas).previsualizar_lote(uuid4())

    assert lote.vistas == ()
    assert lote.escaneados == LOTE_ESCANEO_MAX
    assert len(lote.bloqueadas) == LOTE_ESCANEO_MAX


@pytest.mark.asyncio
async def test_convertir_lote_cuadra_y_nunca_fuerza_compartidos():
    filas = [uuid4(), uuid4(), uuid4()]
    vistas = {
        filas[0]: _vista(filas[0]),
        filas[1]: _vista(filas[1], advertencia="Parece compartido."),
        filas[2]: _vista(filas[2]),
    }
    servicio = _Lote(filas, vistas, respuestas={
        f"tok-{filas[0]}": _resultado(filas[0], resultado="convertida"),
        f"tok-{filas[2]}": _resultado(filas[2], resultado="omitida",
                                      motivo=MotivoConversion.COMPARTIDO.value),
    })
    informe = await servicio.convertir_lote(uuid4())

    assert informe.convertidas == 1 and informe.omitidas == 1
    assert len(informe.detalles) == 2
    assert all(no_forzado is False for _token, no_forzado in servicio.confirmadas)
    assert f"tok-{filas[1]}" not in [token for token, _ in servicio.confirmadas]


@pytest.mark.asyncio
async def test_para_si_el_resultado_es_incierto():
    filas = [uuid4(), uuid4(), uuid4()]
    vistas = {fid: _vista(fid) for fid in filas}
    servicio = _Lote(filas, vistas, respuestas={
        f"tok-{filas[0]}": _resultado(filas[0], resultado="convertida"),
        f"tok-{filas[1]}": _resultado(filas[1], resultado="omitida",
                                      motivo=MotivoConversion.RESULTADO_INCIERTO.value),
        f"tok-{filas[2]}": _resultado(filas[2], resultado="convertida"),
    })
    informe = await servicio.convertir_lote(uuid4())

    assert informe.convertidas == 1 and informe.omitidas == 1
    assert len(servicio.confirmadas) == 2  # la tanda se para: no se intenta la tercera
