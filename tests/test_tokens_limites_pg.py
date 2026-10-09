# ruff: noqa: E501, F401, F811
"""Tamaño de los tokens de candidata y alta, de extremo a extremo (Postgres real). Ver `test_tokens_limites.py`.

Recorrido: **descubrimiento simulado → candidata → vista previa de alta → token de alta → confirmación**, por HTTP y
sobre la aplicación real. Las fuentes se simulan (se parchea `DiscoveryService.search_detallada`); nada sale a la red.

Tres clases de evidencia, que no se mezclan:
1. **Recorrido completo con datos legítimos que antes excedían 8.000**, con una `clave` de grupo obtenida del servicio
   real (la carpeta más larga que cabe en `files.file_path`, hecha de controles de seis bytes) y 100 series parecidas
   reales. Los tokens que salen del servidor quedan a unos pocos caracteres del máximo calculado.
2. **Tokens firmados válidos de la longitud exacta del máximo**, enviados por HTTP y procesados por el servicio (el
   alta; la candidata no puede, ver la nota de `TestFronteraExacta`).
3. **Rechazo sin efectos** del exceso, de un token manipulado, de otro propósito o caducado.
Además: resultados que no se pueden dar de alta (se omiten con aviso, sin llegar a la base), más de 100 parecidas y
títulos a mano no guardables. Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import os
import time
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from tests.test_alta_serie_pg import (  # noqa: F401  (fixtures reutilizadas: BD efímera y entorno sin red)
    ALTA,
    PREV,
    SECRETO,
    cliente,
    entorno,
    numero_de_series,
    post,
    serie_en_bd,
    url_bd,
)
from tests.test_descubrimiento_grupo_pg import FuentesFalsas, res
from tests.test_revision_carpetas_pg import BIB, archivo
from zascarr.api import revision as api_revision
from zascarr.models import ComicTradition, MetadataSource, Series
from zascarr.services.discovery import CAMPO_ID_EXTERNO, DiscoveryService
from zascarr.services.tokens_revision import (
    ANIO_MIN_FIRMABLE,
    CARACTER_MAS_PESADO_DE_UNA_CLAVE,
    EPOCA_DEL_PEOR_CASO,
    MAX_CLAVE_GRUPO,
    MAX_COVER_URL,
    MAX_DESCRIPCION,
    MAX_ID_EXTERNO,
    MAX_PARECIDAS_FIRMADAS,
    MAX_TITULO,
    MAX_TOKEN_ALTA,
    MAX_TOKEN_CANDIDATA,
    TTL_SEGUNDOS,
    AltaFirmada,
    CandidataFirmada,
    crear_token_alta,
    crear_token_candidata,
)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

DESCUBRIR = "/api/revision/descubrir"
LETRA_4_BYTES = "\U00020000"          # 𠀀 (CJK, extensión B): una LETRA (el alta rechaza títulos «solo símbolos») de 4 bytes en UTF-8


@pytest.fixture
def fuentes(entorno, monkeypatch):
    """Sustituye el `search_detallada` que prohíbe `entorno` por el de las fuentes simuladas."""
    f = FuentesFalsas()
    monkeypatch.setattr(DiscoveryService, "search_detallada", f.buscar)
    monkeypatch.setattr(api_revision, "MIN_INTERVALO_S", 0.0)
    api_revision.reiniciar_ritmo_para_pruebas()
    return f


async def efectos(b) -> dict:
    """Todo lo que un rechazo por tamaño NO puede haber escrito."""
    async with b.fabrica() as s:
        return {t: (await s.execute(text(f"SELECT count(*) FROM {t}"))).scalar_one()
                for t in ("series", "issues", "alta_operaciones", "vinculacion_operaciones", "asignacion_operaciones",
                          "local_aliases")}


async def clave_del_grupo(carpeta: str) -> str:
    """La `clave` que la superficie de revisión da al grupo de esa carpeta (se lee de `/carpetas`, no se supone)."""
    async with cliente() as c:
        r = await c.get("/api/revision/carpetas")
    claves = [g["clave"] for g in r.json()["grupos"] if g["clave"] == carpeta]
    assert len(claves) == 1, [g["clave"] for g in r.json()["grupos"]]
    return claves[0]


async def sembrar_grupo(banco, carpeta: str, n: int = 3) -> str:
    await banco.sembrar(*(archivo(f"{carpeta}/Flash {i:02d} (1987).cbz") for i in range(1, n + 1)))
    return await clave_del_grupo(carpeta)


def holgura_de(clave: str, prefijo_de_portada: str) -> int:
    """Cuánto menos que el máximo calculado puede medir un token real: lo que le falta a la clave para 1000 caracteres de
    seis bytes, lo que ahorra el host ASCII de la portada (tres bytes por carácter) y algún dígito de caducidad o año."""
    return (MAX_CLAVE_GRUPO - len(clave)) * 6 * 4 // 3 + len(prefijo_de_portada) * 3 * 4 // 3 + 16


def carpeta_mas_larga() -> str:
    """La carpeta de controles más larga que cabe: `files.file_path` es `String(1000)` y la ruta es
    `{biblioteca}/{carpeta}/1.cbz`. La clave del grupo es esa carpeta, TAL CUAL (no se depura ni se renombra)."""
    return CARACTER_MAS_PESADO_DE_UNA_CLAVE * (1000 - len(f"{BIB}/") - len("/1.cbz"))


async def sembrar_carpeta_larga(banco) -> str:
    carpeta = carpeta_mas_larga()
    await banco.sembrar(archivo(f"{carpeta}/1.cbz"))
    return await clave_del_grupo(carpeta)


#: El grupo que ya siembra `entorno` (tres archivos de Flash).
CLAVE_BASE = "Comics/Flash (1987)"


# ── 1. El recorrido completo con datos legítimos que antes excedían 8.000 ────────────────────────

async def sembrar_parecidas_de(banco, n: int, titulo: str, tradicion: ComicTradition, anio: int) -> list[str]:
    ids = []
    async with banco.fabrica() as s:
        for _ in range(n):
            serie = Series(title=titulo, tradition=tradicion, start_year=anio)
            s.add(serie)
            await s.flush()
            ids.append(str(serie.id))
        await s.commit()
    return ids


class TestRecorridoConElMayorContenidoPosible:

    async def test_clave_real_de_controles_titulo_id_descripcion_portada_y_100_parecidas(self, entorno, fuentes):
        """La clave sale de `/carpetas` (no se construye a mano) y es la carpeta más larga posible, hecha de U+0001: cada
        carácter pesa SEIS bytes en el JSON del token. Es el caso que el primer cálculo del máximo no cubría."""
        clave = await sembrar_carpeta_larga(entorno.banco)
        assert clave == carpeta_mas_larga() and set(clave) == {"\x01"} and len(clave) < MAX_CLAVE_GRUPO
        titulo, ident = LETRA_4_BYTES * MAX_TITULO, LETRA_4_BYTES * MAX_ID_EXTERNO
        cover = "https://www.tebeosfera.com/img/" + LETRA_4_BYTES * (MAX_COVER_URL - len("https://www.tebeosfera.com/img/"))
        assert len(cover) == MAX_COVER_URL
        await sembrar_parecidas_de(entorno.banco, MAX_PARECIDAS_FIRMADAS, titulo, ComicTradition.TEBEO, 1987)
        fuentes.resultados = [res(MetadataSource.TEBEOSFERA, ident, titulo, 1987,
                                  descripcion=LETRA_4_BYTES * (MAX_DESCRIPCION + 500), cover=cover,
                                  tradicion=ComicTradition.TEBEO)]

        d = await post(DESCUBRIR, {"clave": clave, "consulta": "Flash"})
        assert d.status_code == 200, d.text
        candidatas = d.json()["candidatas"]
        assert len(candidatas) == 1 and not any("omitido" in a for a in d.json()["avisos"])
        assert len(candidatas[0]["parecidas_locales"]) == MAX_PARECIDAS_FIRMADAS
        token_candidata = candidatas[0]["token"]
        assert 8000 < len(token_candidata) <= MAX_TOKEN_CANDIDATA        # el límite antiguo la habría rechazado

        elegir = await post(PREV, {"clave": clave, "candidata": token_candidata, "tradicion": "tebeo"})
        assert elegir.status_code == 200 and elegir.json()["accion"] == "elegir"
        assert len(elegir.json()["parecidas"]) == MAX_PARECIDAS_FIRMADAS
        v = await post(PREV, {"clave": clave, "candidata": token_candidata, "tradicion": "tebeo",
                              "decision": "crear_igualmente"})
        assert v.status_code == 200, v.text
        token_alta = v.json()["token"]
        assert 8000 < len(token_alta) <= MAX_TOKEN_ALTA

        # Qué distancia queda al máximo calculado: la holgura de la clave (la real tiene menos de 1000 caracteres: es un
        # prefijo de una ruta de 1000) y la de la portada (empieza por un host ASCII, que pesa un byte y no cuatro),
        # más algún dígito de la caducidad y del año.
        holgura = holgura_de(clave, "https://www.tebeosfera.com/img/")
        assert 0 <= MAX_TOKEN_CANDIDATA - len(token_candidata) <= holgura
        assert 0 <= MAX_TOKEN_ALTA - len(token_alta) <= holgura

        c = await post(ALTA, {"token": token_alta})
        assert c.status_code == 200, c.text
        creadas = [x for x in await serie_en_bd(entorno.banco) if x.tebeosfera_slug == ident]
        assert len(creadas) == 1 and creadas[0].title == titulo
        assert len(creadas[0].description) == MAX_DESCRIPCION and len(creadas[0].cover_url) == MAX_COVER_URL
        assert await numero_de_series(entorno.banco) == MAX_PARECIDAS_FIRMADAS + 1

    async def test_una_candidata_normal_sigue_siendo_pequena(self, entorno, fuentes):
        clave = await clave_del_grupo(CLAVE_BASE)
        fuentes.resultados = [res(MetadataSource.COMIC_VINE, "796", "Flash", 1987, descripcion="Velocista.")]
        d = await post(DESCUBRIR, {"clave": clave, "consulta": "Flash"})
        token = d.json()["candidatas"][0]["token"]
        assert len(token) < 1000
        v = await post(PREV, {"clave": clave, "candidata": token, "tradicion": "american"})
        assert v.status_code == 200 and len(v.json()["token"]) < 1500
        assert (await post(ALTA, {"token": v.json()["token"]})).status_code == 200


# ── 2. Tokens firmados válidos en la frontera exacta ──────────────────────────────────────────────

def alta_firmada_maxima(clave: str, vistas: tuple[str, ...]) -> AltaFirmada:
    fuente = "tebeosfera"            # tan larga como la que más (10) y la única con identificador de texto
    tradicion = max((t.value for t in ComicTradition), key=len)
    return AltaFirmada(
        clave=clave, modo="crear", origen="descubrir", fuente=fuente, id_externo=LETRA_4_BYTES * MAX_ID_EXTERNO,
        titulo=LETRA_4_BYTES * MAX_TITULO, anio=ANIO_MIN_FIRMABLE, tradicion=tradicion, descripcion=LETRA_4_BYTES * MAX_DESCRIPCION,
        cover_url=LETRA_4_BYTES * MAX_COVER_URL,         # no es una URL permitida: al crear la serie se descarta
        serie_id=None, vistas=vistas, operacion=str(uuid4()))


class TestFronteraExacta:
    """Un token FIRMADO y válido cuya longitud es exactamente el máximo, enviado por HTTP y procesado por el servicio.

    Solo el alta puede probarse así: su contexto (la `clave`) viaja DENTRO del token, de modo que la confirmación no
    necesita que exista un grupo con esa clave. La candidata sí lo necesita (la vista previa busca el grupo) y la clave
    real nunca llega a 1000 caracteres (es un prefijo de una ruta de `String(1000)`), así que **el máximo de la
    candidata es una cota conservadora que el servicio no alcanza**: lo que se prueba de ella es el recorrido de
    arriba, a unos pocos caracteres del máximo, y la igualdad exacta con el cálculo en `test_tokens_limites.py`."""

    async def test_el_alta_firmada_de_la_longitud_exacta_se_procesa(self, entorno):
        clave = CARACTER_MAS_PESADO_DE_UNA_CLAVE * MAX_CLAVE_GRUPO
        vistas = tuple(await sembrar_parecidas_de(entorno.banco, MAX_PARECIDAS_FIRMADAS, LETRA_4_BYTES * MAX_TITULO,
                                                   ComicTradition.FRANCO_BELGIAN, 2100))
        token = crear_token_alta(alta_firmada_maxima(clave, vistas), SECRETO, ahora=EPOCA_DEL_PEOR_CASO)
        assert len(token) == MAX_TOKEN_ALTA, "ya no es la frontera: el máximo y esta prueba han dejado de coincidir"
        c = await post(ALTA, {"token": token})
        assert c.status_code == 200, c.text
        creada = [x for x in await serie_en_bd(entorno.banco) if x.tebeosfera_slug == LETRA_4_BYTES * MAX_ID_EXTERNO]
        assert len(creada) == 1 and creada[0].title == LETRA_4_BYTES * MAX_TITULO
        assert creada[0].cover_url is None                       # la portada no cumple la política: se descartó, no se rechazó
        assert await numero_de_series(entorno.banco) == MAX_PARECIDAS_FIRMADAS + 1

    async def test_la_candidata_firmada_con_la_clave_real_mas_larga_se_procesa(self, entorno):
        clave = await sembrar_carpeta_larga(entorno.banco)
        fuente = "tebeosfera"            # tan larga como la que más (10) y la única con identificador de texto
        tradicion = max((t.value for t in ComicTradition), key=len)
        c = CandidataFirmada(fuente, LETRA_4_BYTES * MAX_ID_EXTERNO, LETRA_4_BYTES * MAX_TITULO, 2100, tradicion,
                             LETRA_4_BYTES * MAX_DESCRIPCION,
                             "https://www.tebeosfera.com/" + LETRA_4_BYTES * (MAX_COVER_URL - len("https://www.tebeosfera.com/")))
        token = crear_token_candidata(clave, c, SECRETO, ahora=EPOCA_DEL_PEOR_CASO)
        assert 0 <= MAX_TOKEN_CANDIDATA - len(token) <= holgura_de(clave, "https://www.tebeosfera.com/")
        v = await post(PREV, {"clave": clave, "candidata": token, "tradicion": tradicion})
        assert v.status_code == 200, v.text
        assert len(v.json()["token"]) <= MAX_TOKEN_ALTA


# ── 3. El exceso, lo manipulado y lo caducado se rechazan sin efectos ─────────────────────────────

class TestRechazoSinEfectos:

    async def test_candidata_de_mas_del_maximo_da_422_de_validacion_y_no_escribe_nada(self, entorno):
        clave = await clave_del_grupo(CLAVE_BASE)
        antes = await efectos(entorno.banco)
        r = await post(PREV, {"clave": clave, "candidata": "a" * (MAX_TOKEN_CANDIDATA + 1), "tradicion": "american"})
        assert r.status_code == 422 and isinstance(r.json()["detail"], list)      # lo rechaza el esquema de la petición
        assert await efectos(entorno.banco) == antes

    async def test_el_limite_de_candidata_es_inclusivo(self, entorno):
        """Un cuerpo de exactamente el máximo llega al servicio (no es un token válido: solo prueba que el esquema no
        corta antes de tiempo; el token válido de la frontera es el de `TestFronteraExacta`)."""
        clave = await clave_del_grupo(CLAVE_BASE)
        antes = await efectos(entorno.banco)
        r = await post(PREV, {"clave": clave, "candidata": "a" * MAX_TOKEN_CANDIDATA, "tradicion": "american"})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "token_invalido"
        assert await efectos(entorno.banco) == antes

    async def test_alta_de_mas_del_maximo_da_422_de_validacion_y_no_escribe_nada(self, entorno):
        antes = await efectos(entorno.banco)
        r = await post(ALTA, {"token": "a" * (MAX_TOKEN_ALTA + 1)})
        assert r.status_code == 422 and isinstance(r.json()["detail"], list)
        assert await efectos(entorno.banco) == antes

    async def test_el_limite_del_alta_es_inclusivo(self, entorno):
        antes = await efectos(entorno.banco)
        r = await post(ALTA, {"token": "a" * MAX_TOKEN_ALTA})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "token_invalido"
        assert await efectos(entorno.banco) == antes

    async def test_firma_proposito_y_caducidad_se_siguen_exigiendo_con_tokens_grandes(self, entorno, fuentes):
        clave = await clave_del_grupo(CLAVE_BASE)
        fuentes.resultados = [res(MetadataSource.COMIC_VINE, "796", LETRA_4_BYTES * MAX_TITULO, 1987,
                                  descripcion=LETRA_4_BYTES * MAX_DESCRIPCION)]
        token = (await post(DESCUBRIR, {"clave": clave, "consulta": "Flash"})).json()["candidatas"][0]["token"]
        antes = await efectos(entorno.banco)

        manipulado = token[:-1] + ("0" if token[-1] != "0" else "1")                            # firma
        r = await post(PREV, {"clave": clave, "candidata": manipulado, "tradicion": "american"})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "token_invalido"

        r = await post(ALTA, {"token": token})                                                   # propósito
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "token_invalido"

        caducada = crear_token_candidata(clave, CandidataFirmada("comic_vine", "796", LETRA_4_BYTES * MAX_TITULO, 1987,
                                                                 "american", LETRA_4_BYTES * MAX_DESCRIPCION, None),
                                         SECRETO, ahora=time.time() - TTL_SEGUNDOS - 60)       # caducidad
        r = await post(PREV, {"clave": clave, "candidata": caducada, "tradicion": "american"})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "token_invalido"

        alta_caducada = crear_token_alta(alta_firmada_maxima(clave, ()), SECRETO, ahora=time.time() - TTL_SEGUNDOS - 60)
        r = await post(ALTA, {"token": alta_caducada})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "token_invalido"
        assert await efectos(entorno.banco) == antes


# ── 3b. Lo que no se puede dar de alta no se ofrece ni llega a la base ────────────────────────────

class TestResultadosQueNoSePuedenFirmar:

    async def test_postgres_rechaza_un_nul_o_un_sustituto_suelto_en_un_identificador_de_texto(self, entorno):
        """La premisa del orden de validación: el identificador de Tebeosfera es TEXTO y va en una consulta SQL. Si un
        resultado inválido llegara a ella, la base (o el controlador) la rechazaría y rompería la búsqueda entera."""
        for malo in ("flash\x00malo", "flash\ud800malo"):
            async with entorno.banco.fabrica() as s:
                with pytest.raises((DBAPIError, UnicodeEncodeError)):
                    await s.execute(select(Series).where(Series.tebeosfera_slug.in_([malo])))

    async def test_los_invalidos_de_tebeosfera_se_omiten_con_aviso_el_valido_se_conserva_y_no_se_escribe(self, entorno, fuentes):
        clave = await clave_del_grupo(CLAVE_BASE)
        async with entorno.banco.fabrica() as s:                       # una serie local con el slug del resultado válido
            s.add(Series(title="Flash", tradition=ComicTradition.TEBEO, start_year=1987, tebeosfera_slug="flash-1987"))
            await s.commit()
        antes = await efectos(entorno.banco)
        fuentes.resultados = [
            res(MetadataSource.TEBEOSFERA, "flash-1987", "Flash", 1987, tradicion=ComicTradition.TEBEO),      # válido
            res(MetadataSource.TEBEOSFERA, "flash\x00malo", "Flash Uno", 1987),                 # id con NUL
            res(MetadataSource.TEBEOSFERA, "flash\ud800malo", "Flash Dos", 1987),               # id con sustituto suelto
            res(MetadataSource.TEBEOSFERA, "t" * (MAX_ID_EXTERNO + 1), "Flash Tres", 1987),     # id demasiado largo
            res(MetadataSource.TEBEOSFERA, "ok-2", "T" * (MAX_TITULO + 1), 1987),                # título demasiado largo
        ]
        r = await post(DESCUBRIR, {"clave": clave, "consulta": "Flash"})
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        assert [c["titulo"] for c in cuerpo["candidatas"]] == ["Flash"]
        assert any(a.startswith("Se han omitido 4 resultado(s)") for a in cuerpo["avisos"]), cuerpo["avisos"]
        assert cuerpo["candidatas"][0]["ya_en_biblioteca"]["titulo"] == "Flash"        # la consulta por slug sí funcionó
        assert await efectos(entorno.banco) == antes

    async def test_los_datos_de_presentacion_se_depuran_sin_reinterpretar_identificadores(self, entorno, fuentes):
        clave = await clave_del_grupo(CLAVE_BASE)
        await entorno.banco.serie("Flash Negro", 1987)             # existe con el título YA depurado
        fuentes.resultados = [
            res(MetadataSource.COMIC_VINE, "5", "Flash \ud800 Rojo", 1987),                   # sustituto en el título: se depura
            res(MetadataSource.COMIC_VINE, "6", "Flash\x00Negro", 1987, descripcion="a\x00b"),   # NUL: se depura
            res(MetadataSource.COMIC_VINE, "7", "Flash Azul", 1987, sitio="https://ejemplo.example/\ud800"),   # ficha no firmable
        ]
        r = await post(DESCUBRIR, {"clave": clave, "consulta": "Flash"})
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        assert sorted(c["titulo"] for c in cuerpo["candidatas"]) == ["Flash Azul", "Flash Negro", "Flash Rojo"]
        assert next(c for c in cuerpo["candidatas"] if c["titulo"] == "Flash Azul")["sitio_url"] is None
        negro = next(c for c in cuerpo["candidatas"] if c["titulo"] == "Flash Negro")
        assert negro["descripcion"] == "a b"
        assert len(negro["parecidas_locales"]) == 1           # la consulta local usó el título depurado, no el crudo
        assert not any("omitido" in a for a in cuerpo["avisos"])
        for c in cuerpo["candidatas"]:                                  # y lo que se ofrece se puede dar de alta de verdad
            v = await post(PREV, {"clave": clave, "candidata": c["token"], "tradicion": "american"})
            assert v.status_code == 200, v.text

    async def test_un_anio_imposible_no_se_muestra_ni_se_firma(self, entorno, fuentes):
        clave = await clave_del_grupo(CLAVE_BASE)
        fuentes.resultados = [res(MetadataSource.COMIC_VINE, "9", "Flash Verde", 99999)]       # no cabe en una SmallInteger
        r = await post(DESCUBRIR, {"clave": clave, "consulta": "Flash"})
        assert r.status_code == 200, r.text
        c = r.json()["candidatas"][0]
        assert c["anio"] is None                                      # lo mostrado y lo firmado coinciden
        v = await post(PREV, {"clave": clave, "candidata": c["token"], "tradicion": "american"})
        assert v.status_code == 200 and v.json()["anio"] is None

    async def test_sin_omitidos_no_hay_aviso_de_omision(self, entorno, fuentes):
        clave = await clave_del_grupo(CLAVE_BASE)
        fuentes.resultados = [res(MetadataSource.COMIC_VINE, "1", "Flash", 1987)]
        r = await post(DESCUBRIR, {"clave": clave, "consulta": "Flash"})
        assert not any("omitido" in a for a in r.json()["avisos"])


# ── 4. Demasiadas parecidas ───────────────────────────────────────────────────────────────────────

async def sembrar_parecidas(banco, n: int):
    async with banco.fabrica() as s:
        s.add_all([Series(title="Flash", tradition=ComicTradition.AMERICAN, start_year=1987) for _ in range(n)])
        await s.commit()


def manual_flash(**kw) -> dict:
    return {"clave": "Comics/Flash (1987)", "manual": {"titulo": "Flash", "anio": 1987}, "tradicion": "american", **kw}


class TestDemasiadasParecidas:

    async def test_con_100_parecidas_se_emite_el_token_y_cabe_en_el_maximo(self, entorno):
        await sembrar_parecidas(entorno.banco, MAX_PARECIDAS_FIRMADAS)
        elegir = await post(PREV, manual_flash())
        assert elegir.status_code == 200 and elegir.json()["accion"] == "elegir" and elegir.json()["token"] is None
        v = await post(PREV, manual_flash(decision="crear_igualmente"))
        assert v.status_code == 200, v.text
        assert 4000 < len(v.json()["token"]) <= MAX_TOKEN_ALTA
        assert (await post(ALTA, {"token": v.json()["token"]})).status_code == 200
        assert await numero_de_series(entorno.banco) == MAX_PARECIDAS_FIRMADAS + 1

    async def test_con_101_parecidas_no_se_emite_token_y_no_se_escribe_nada(self, entorno):
        await sembrar_parecidas(entorno.banco, MAX_PARECIDAS_FIRMADAS + 1)
        antes = await efectos(entorno.banco)
        r = await post(PREV, manual_flash(decision="crear_igualmente"))
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "demasiadas_parecidas", r.text
        assert "101" in r.json()["detail"]["mensaje"]
        assert await efectos(entorno.banco) == antes

    async def test_con_101_parecidas_se_puede_seguir_reutilizando_una(self, entorno):
        """El límite solo afecta al alta que CREA (es la que firma las vistas); elegir una existente no firma ninguna."""
        await sembrar_parecidas(entorno.banco, MAX_PARECIDAS_FIRMADAS + 1)
        elegir = await post(PREV, manual_flash())
        assert elegir.json()["accion"] == "elegir" and len(elegir.json()["parecidas"]) == MAX_PARECIDAS_FIRMADAS + 1
        una = elegir.json()["parecidas"][0]["series_id"]
        v = await post(PREV, manual_flash(decision="reutilizar", serie_id=una))
        assert v.status_code == 200 and v.json()["accion"] == "reutilizar" and v.json()["token"]


# ── 5. Título a mano que no se puede guardar ──────────────────────────────────────────────────────

def _cliente_sin_relanzar() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=__import__("zascarr.main", fromlist=["app"]).app,
                                                           raise_app_exceptions=False),
                             base_url="http://localhost", headers={"Origin": "http://localhost"})


class TestTituloManualNoGuardable:

    @pytest.mark.parametrize("escape,nombre", [("\\u0000", "nul"), ("\\u0007", "campana")])
    async def test_da_422_claro_y_no_500_ni_escribe(self, entorno, escape, nombre):
        antes = await efectos(entorno.banco)
        cuerpo = ('{"clave":"Comics/Flash (1987)","manual":{"titulo":"Flash' + escape +
                  '","anio":1987},"tradicion":"american"}')
        async with _cliente_sin_relanzar() as c:
            r = await c.post(PREV, content=cuerpo.encode(), headers={"content-type": "application/json"})
        assert r.status_code == 422, (r.status_code, r.text)
        assert r.json()["detail"]["codigo"] == "datos_invalidos"
        assert await efectos(entorno.banco) == antes
