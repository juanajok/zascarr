# ruff: noqa: E501
"""D4-B4 (#233): clave canónica, deduplicación, ciclo de vida, tope/archivado y «Mantener lo mío» puro.

Sin PostgreSQL: las funciones de esta suite son puras sobre `File.metadata_`. La acción con token y
comprobante se prueba sobre Postgres en `test_rescan_relacion_confirmada_pg.py`.
"""
from __future__ import annotations

import json

from zascarr.services.discrepancias import (
    CLAVE_ARCHIVADAS,
    CLAVE_METADATA,
    MANTENIDA,
    OBSOLETA,
    PENDIENTE,
    RESUELTA,
    TOPE,
    TOPE_ARCHIVADAS,
    Propuesta,
    clave_de,
    clave_valida,
    crear_discrepancia,
    entrada,
    mantener,
    marcar_estado_por_relacion,
    origen_valido,
    pendientes,
    registrar,
)
from zascarr.services.tokens_revision import (
    MAX_TOKEN_MANTENER,
    MantenerFirmada,
    crear_token_mantener,
    verificar_token_mantener,
)

RELACION = {"issue_id": "11111111-1111-4111-8111-111111111111",
            "serie_id": "22222222-2222-4222-8222-222222222222",
            "operacion_id": "33333333-3333-4333-8333-333333333333"}


def _propuesta(**kw) -> Propuesta:
    base = dict(origen="rescan", serie_destino_id=RELACION["serie_id"],
                issue_destino_uuid="44444444-4444-4444-8444-444444444444",
                numero="2", formato="single_issue")
    base.update(kw)
    return Propuesta(**base)


def _entrada(propuesta=None, relacion=None, *, ahora="2026-11-09T00:00:00+00:00"):
    return crear_discrepancia(propuesta or _propuesta(), relacion or RELACION, ahora=ahora)


def test_clave_estable_y_sin_fecha_score_ruta():
    a = clave_de(_propuesta())
    b = clave_de(_propuesta())
    assert a == b and len(a) == 64 and all(c in "0123456789abcdef" for c in a)
    assert clave_de(_propuesta(numero="3")) != a
    assert clave_de(_propuesta(issue_destino_uuid=None)) != a
    assert clave_de(_propuesta(origen="comicinfo")) != a
    # El nombre de archivo, la ruta, el score y la fecha NO forman parte de la afirmación.
    assert "ruta" not in json.dumps(_propuesta().como_dict())
    assert _entrada(ahora="2026-11-09T01:00:00+00:00")["clave"] == _entrada(ahora="2026-11-10T01:00:00+00:00")["clave"]


def test_origenes_cerrados():
    assert origen_valido("rescan") and origen_valido("comicinfo") and origen_valido("importador")
    assert origen_valido("fuente:comic_vine") and not origen_valido("fuente:")
    assert not origen_valido("inventado") and not origen_valido("")


def test_la_entrada_no_lleva_usuario_ip_ni_ruta():
    e = _entrada()
    serializado = json.dumps(e, ensure_ascii=False).lower()
    for prohibido in ("usuario", "user", "ip", "ruta", "path", "token", "sesion", "sesión"):
        assert prohibido not in serializado
    assert e["estado"] == PENDIENTE and e["version"] == 1


def test_dedupe_por_clave_no_duplica_la_misma_afirmacion():
    meta = registrar(None, _entrada())[0]
    meta, novedad = registrar(meta, _entrada(ahora="2026-11-09T01:00:00+00:00"))
    activas = meta[CLAVE_METADATA]
    assert len(activas) == 1
    assert activas[0]["observada_en"] == "2026-11-09T01:00:00+00:00"   # refresca la observación, no duplica
    assert novedad is False                                            # F4: solo observada no cuenta


def test_reobservar_no_es_una_discrepancia_nueva_pero_reabrir_obsoleta_si():
    meta = registrar(None, _entrada())[0]
    meta, novedad = registrar(meta, _entrada(ahora="2026-11-09T01:00:00+00:00"))
    assert novedad is False
    obsoleta = marcar_estado_por_relacion(meta, {**RELACION, "issue_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"})
    assert entrada(obsoleta, _entrada()["clave"])["estado"] == OBSOLETA
    _meta, novedad = registrar(obsoleta, _entrada(ahora="2026-11-09T02:00:00+00:00"))
    assert novedad is True


def test_mantener_no_se_pisa_por_una_repeticion_posterior():
    meta = registrar(None, _entrada())[0]
    meta, actualizada = mantener(meta, _entrada()["clave"], operacion_id="55555555-5555-4555-8555-555555555555",
                                 fecha="2026-11-09T02:00:00+00:00")
    assert actualizada and entrada(meta, _entrada()["clave"])["estado"] == MANTENIDA
    meta, novedad = registrar(meta, _entrada(ahora="2026-11-09T03:00:00+00:00"))
    assert novedad is False and entrada(meta, _entrada()["clave"])["estado"] == MANTENIDA


def test_afirmacion_distinta_genera_otra_entrada():
    meta = registrar(None, _entrada())[0]
    meta, _ = registrar(meta, _entrada(_propuesta(numero="3")))
    assert len(meta[CLAVE_METADATA]) == 2


def test_otra_relacion_archiva_la_anterior_y_abre_pendiente():
    meta = registrar(None, _entrada())[0]
    mantenida, _ = mantener(meta, _entrada()["clave"], operacion_id="55555555-5555-4555-8555-555555555555",
                            fecha="2026-11-09T02:00:00+00:00")
    otra = {**RELACION, "issue_id": "99999999-9999-4999-8999-999999999999", "operacion_id": None}
    meta, _ = registrar(mantenida, _entrada(relacion=otra))
    assert entrada(meta, _entrada()["clave"])["estado"] == PENDIENTE
    assert any(e["estado"] == OBSOLETA for e in meta[CLAVE_ARCHIVADAS])


def test_ciclo_resuelta_y_obsoleta_por_cambio_de_relacion():
    meta = registrar(None, _entrada())[0]
    # La corrección elige justo la publicación que proponía la fuente → resuelta.
    meta = marcar_estado_por_relacion(meta, {**RELACION, "issue_id": "44444444-4444-4444-8444-444444444444"})
    assert entrada(meta, _entrada()["clave"])["estado"] == RESUELTA
    # Otra corrección distinta → obsoleta.
    meta2 = registrar(None, _entrada())[0]
    meta2 = marcar_estado_por_relacion(meta2, {**RELACION, "issue_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"})
    assert entrada(meta2, _entrada()["clave"])["estado"] == OBSOLETA
    # Sin relación (archivo desvinculado) → obsoleta.
    meta3 = marcar_estado_por_relacion(registrar(None, _entrada())[0], None)
    assert entrada(meta3, _entrada()["clave"])["estado"] == OBSOLETA


def test_solo_se_avisan_las_pendientes_de_la_relacion_actual():
    meta = registrar(None, _entrada())[0]
    assert pendientes(meta, RELACION) and len(pendientes(meta, RELACION)) == 1
    assert pendientes(meta, {**RELACION, "issue_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"}) == []
    mantenida, _ = mantener(meta, _entrada()["clave"], operacion_id="55555555-5555-4555-8555-555555555555",
                            fecha="2026-11-09T02:00:00+00:00")
    assert pendientes(mantenida, RELACION) == []


def test_tope_y_archivado_no_crecen_sin_limite():
    meta = None
    for i in range(TOPE + 5):
        meta, _ = registrar(meta, _entrada(_propuesta(numero=str(i))))
    assert len(meta[CLAVE_METADATA]) == TOPE
    assert len(meta[CLAVE_ARCHIVADAS]) == 5
    for i in range(TOPE + 5, TOPE + 5 + TOPE_ARCHIVADAS + 10):
        meta, _ = registrar(meta, _entrada(_propuesta(numero=str(i))))
    assert len(meta[CLAVE_METADATA]) <= TOPE
    assert len(meta[CLAVE_ARCHIVADAS]) <= TOPE_ARCHIVADAS


def test_metadata_manipulado_no_rompe_la_lectura():
    assert registrar({"discrepancias": "no-es-una-lista"}, _entrada())[0][CLAVE_METADATA]
    meta = registrar(None, _entrada())[0]
    meta["discrepancias"].append({"clave": "x"})           # entrada incompleta: se ignora al leer
    assert len(pendientes(meta, RELACION)) == 1


def test_mantener_solo_desde_pendiente_y_es_idempotente():
    meta = registrar(None, _entrada())[0]
    clave = _entrada()["clave"]
    meta, actualizada = mantener(meta, clave, operacion_id="55555555-5555-4555-8555-555555555555",
                                 fecha="2026-11-09T02:00:00+00:00")
    assert actualizada
    meta2, actualizada = mantener(meta, clave, operacion_id="55555555-5555-4555-8555-555555555555",
                                  fecha="2026-11-09T02:00:00+00:00")
    assert not actualizada and meta2 == meta
    assert mantener(meta, "no-existe", operacion_id="55555555-5555-4555-8555-555555555555", fecha="x") == (None, False)
    assert mantener(meta, "no-es-una-clave", operacion_id="55555555-5555-4555-8555-555555555555", fecha="x") == (None, False)
    assert entrada(meta, "no-es-una-clave") is None


def test_clave_valida_es_64_hex_minusculas():
    assert clave_valida(_entrada()["clave"]) is True
    assert clave_valida("A" * 64) is False
    assert clave_valida("a" * 63) is False
    assert clave_valida("a" * 65) is False
    assert clave_valida("g" * 64) is False
    assert clave_valida(None) is False


def test_el_token_de_mantener_esta_atado_al_archivo_y_a_esa_clave():
    secreto = "x" * 32
    ident = "00000000-0000-4000-8000-000000000001"
    m = MantenerFirmada(file_id=ident, clave="f" * 64, issue_id=ident, serie_id=ident,
                        vinculo_operacion=ident, operacion=ident)
    token = crear_token_mantener(m, secreto, ahora=1000.0)
    assert len(token) <= MAX_TOKEN_MANTENER
    v = verificar_token_mantener(token, secreto, ahora=1001.0)
    assert v is not None and v.file_id == ident and v.clave == "f" * 64
    # Otro contexto, otro propósito y el token manipulado no valen.
    assert verificar_token_mantener(token, secreto, ahora=1001.0) is not None
    assert verificar_token_mantener(token, "y" * 32, ahora=1001.0) is None
    assert verificar_token_mantener(token + "x", secreto, ahora=1001.0) is None
    assert verificar_token_mantener(token, secreto, ahora=10_000.0) is None
    # Caducado pero legible para resolver idempotencia: `ignorar_caducidad`.
    assert verificar_token_mantener(token, secreto, ahora=10_000.0, ignorar_caducidad=True) is not None
