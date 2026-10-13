# ruff: noqa: E501, F401, F811
"""#116 — qué se comunica del resultado de confirmar un lote de vinculación, criterio por criterio (Postgres real).

El contrato funcional lo define #116; esta suite lo FIJA con una prueba por criterio y por estado observable. Casi todo el
mecanismo ya estaba (#103) y tiene sus pruebas en `test_vinculacion_pg.py`; aquí se enlazan, y se acredita lo que #116
añade: el **criterio 5** (token caducado sin informe: se dice qué se sabe y qué no, y no se presenta como informe).

| Criterio de #116 | Estado | Dónde se prueba |
|---|---|---|
| 1. Fallo antes del commit | nada persistido, ni informe | aquí (`TestCriterio1`) y `test_vinculacion_pg::TestIdempotencia` |
| 2. Respuesta perdida tras el commit | el mismo token devuelve el informe | aquí (`TestCriterio2`) |
| 3. Fallo posterior al commit | el reintento devuelve lo persistido | `test_vinculacion_pg::TestFalloDespuesDeLaRespuestaPreparada` y aquí (`TestCriterio3`) |
| 4. Resultado no determinable | «pendiente de confirmación» y repetir el token | aquí (`TestCriterio4`) |
| 5. Token caducado | limitación explícita, no es un informe | aquí (`TestCriterio5`) |
"""
from __future__ import annotations

import os
import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_vinculacion_pg import (  # noqa: F401  (fixtures y ayudas compartidas)
    CLAVE,
    SECRETO,
    archivos,
    confirmar,
    ent,
    entorno,
    estado_de_archivos,
    firmar,
    informes,
    numero_de,
    serie_de_prueba,
    token_de,
    url_bd,
)
from zascarr.services import vinculacion
from zascarr.services.tokens_revision import TTL_SEGUNDOS
from zascarr.services.vinculacion import (
    MENSAJE_CADUCADO_SIN_APLICAR,
    MENSAJE_CADUCADO_SIN_INFORME,
    RETENCION_HORAS,
    TokenCaducadoError,
    VinculacionDeArchivos,
)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)"),
]

UNO = "Flash 01 (1987).cbz"


async def sin_efectos(ent) -> None:
    assert await numero_de("issues", ent.banco) == 0 and await informes(ent.banco) == []
    assert all(v[0] is None for v in (await estado_de_archivos(ent.banco)).values())


class TestCriterio1FalloAntesDelCommit:
    async def test_un_fallo_antes_del_commit_no_deja_vinculos_ni_informe_y_no_se_presenta_como_confirmado(self, ent, monkeypatch):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO)
        token = await token_de(serie, ids.values())

        async def falla(self, *a, **k):
            raise RuntimeError("fallo inesperado antes del commit")
        monkeypatch.setattr(VinculacionDeArchivos, "_nombres", falla)       # se prepara la respuesta ANTES del commit
        r = await confirmar(token)
        assert r.status_code == 500 and r.json()["detail"]["codigo"] == "error_inesperado"
        assert "no se ha cambiado nada" in r.json()["detail"]["mensaje"].lower()
        assert "resultado" not in r.json() and "vinculados" not in r.text      # no es un informe, ni parcial
        await sin_efectos(ent)


class TestCriterio2RespuestaPerdidaTrasElCommit:
    async def test_reenviar_el_mismo_token_devuelve_el_informe_persistido_sin_ejecutar_otra_vez(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO)
        token = await firmar(ent, serie, [(ids[UNO], "1")])
        primero = (await confirmar(token)).json()                          # «la respuesta no llegó»: se reenvía
        otra_vez = await confirmar(token)
        assert otra_vez.status_code == 200 and otra_vez.json()["repetida"] is True
        assert otra_vez.json()["resultado"] == primero["resultado"]
        assert await numero_de("issues", ent.banco) == 1 and len(await informes(ent.banco)) == 1


class TestCriterio3FalloPosteriorAlCommit:
    async def test_tras_un_fallo_al_entregar_la_respuesta_el_reintento_devuelve_lo_persistido(self, ent, monkeypatch):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO)
        token = await token_de(serie, ids.values())
        real = AsyncSession.commit

        async def commit_y_luego_falla(self):
            await real(self)
            raise ConnectionError("se perdió la conexión al confirmar")
        monkeypatch.setattr(AsyncSession, "commit", commit_y_luego_falla)
        r = await confirmar(token)
        monkeypatch.setattr(AsyncSession, "commit", real)
        assert r.status_code == 503 and r.json()["detail"]["codigo"] == "resultado_incierto"
        assert "no se ha cambiado nada" not in r.text.lower()               # no dice «sin cambios»
        b = (await confirmar(token)).json()
        assert b["repetida"] is True and b["resultado"]["global"] == "vinculados_todos"
        assert await numero_de("issues", ent.banco) == 1                    # y no se repitieron los efectos


class TestCriterio4ResultadoNoDeterminable:
    async def test_se_comunica_como_pendiente_de_confirmacion_y_se_ofrece_repetir_con_el_mismo_token(self, ent, monkeypatch):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO)
        token = await token_de(serie, ids.values())

        async def falla(self):
            raise ConnectionError("se cayó antes de confirmar")
        monkeypatch.setattr(AsyncSession, "commit", falla)
        r = await confirmar(token)
        d = r.json()["detail"]
        assert r.status_code == 503 and d["codigo"] == "resultado_incierto" and r.headers["retry-after"] == "1"
        assert "no se pudo confirmar si se aplicó" in d["mensaje"].lower() and "mismo token" in d["mensaje"].lower()
        texto = d["mensaje"].lower()
        assert "no se ha cambiado nada" not in texto and "se aplicó correctamente" not in texto
        assert "resultado" not in r.json()                                # no se afirma ni un informe ni su ausencia


class TestCriterio5TokenCaducadoSinInforme:
    async def test_dentro_de_la_retencion_se_dice_que_no_llego_a_aplicarse_y_no_es_un_informe(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO)
        token = await firmar(ent, serie, [(ids[UNO], "1")], ahora=time.time() - 16 * 60)
        r = await confirmar(token)
        d = r.json()["detail"]
        assert r.status_code == 410 and d["codigo"] == "token_caducado"
        assert d["informe_disponible"] is False and d["puede_haberse_aplicado"] is False
        assert d["mensaje"] == MENSAJE_CADUCADO_SIN_APLICAR
        assert "resultado" not in r.json() and "repetida" not in r.json()     # no se presenta como informe
        await sin_efectos(ent)

    async def test_pasada_la_retencion_se_dice_que_ya_no_se_puede_saber_ni_reconstruir(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO)
        token = await firmar(ent, serie, [(ids[UNO], "1")], ahora=time.time() - 25 * 3600)
        r = await confirmar(token)
        d = r.json()["detail"]
        assert r.status_code == 410 and d["informe_disponible"] is False and d["puede_haberse_aplicado"] is True
        assert d["mensaje"] == MENSAJE_CADUCADO_SIN_INFORME
        assert "no se puede saber" in d["mensaje"].lower() and "reconstruir" in d["mensaje"].lower()
        assert "resultado" not in r.json()
        await sin_efectos(ent)                                                 # y la confirmación NO ejecutó nada

    @pytest.mark.parametrize("segundos_tras_la_firma,puede", [
        (TTL_SEGUNDOS + 1, False),                                             # recién caducado
        (RETENCION_HORAS * 3600 - 1, False),                                   # un segundo antes de que pueda estar purgado
        (RETENCION_HORAS * 3600, True),                                        # frontera: ya puede haberse purgado
        (RETENCION_HORAS * 3600 + 3600, True),
    ])
    async def test_la_frontera_entre_no_se_aplico_y_no_se_puede_saber(self, ent, segundos_tras_la_firma, puede):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO)
        t0 = float(int(time.time()))                                           # `exp` del token es entero: frontera exacta
        token = await firmar(ent, serie, [(ids[UNO], "1")], ahora=t0)
        async with ent.banco.fabrica() as s:
            with pytest.raises(TokenCaducadoError) as e:
                await VinculacionDeArchivos(s, secret=SECRETO, ahora=t0 + segundos_tras_la_firma).confirmar(token)
        assert e.value.puede_haberse_aplicado is puede
        assert str(e.value) == (MENSAJE_CADUCADO_SIN_INFORME if puede else MENSAJE_CADUCADO_SIN_APLICAR)

    async def test_un_token_caducado_con_informe_si_devuelve_el_informe_completo(self, ent):
        """Lo contrario: si el informe se conserva, el token caducado devuelve el informe persistido, no la limitación."""
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO)
        token = await firmar(ent, serie, [(ids[UNO], "1")])
        primero = (await confirmar(token)).json()
        async with ent.banco.fabrica() as s:
            b = await VinculacionDeArchivos(s, secret=SECRETO, ahora=time.time() + 25 * 3600).confirmar(token)
        assert b.repetida is True and b.resultado.model_dump(by_alias=True) == primero["resultado"]

    async def test_el_aviso_es_cierto_tras_purgar_de_verdad(self, ent):
        """Aplicada, purgada y reenviada: la limitación dice «no se puede saber», y de hecho SÍ se aplicó."""
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO)
        t0 = time.time() - 25 * 3600
        token = await firmar(ent, serie, [(ids[UNO], "1")], ahora=t0)
        async with ent.banco.fabrica() as s:                                   # se aplicó cuando el token aún valía
            await VinculacionDeArchivos(s, secret=SECRETO, ahora=t0 + 60).confirmar(token)
        async with ent.banco.fabrica() as s:                                   # y su informe ya se purgó
            from sqlalchemy import text
            await s.execute(text("DELETE FROM vinculacion_operaciones"))
            await s.commit()
        r = await confirmar(token)
        d = r.json()["detail"]
        assert r.status_code == 410 and d["puede_haberse_aplicado"] is True      # honesto: pudo (y de hecho se aplicó)
        assert await numero_de("issues", ent.banco) == 1                         # el hecho: sí estaba aplicada
