# ruff: noqa: E501, F401, F811
"""Tamaño de los tokens de candidata y alta, de extremo a extremo (Postgres real). Ver `test_tokens_limites.py`.

Recorrido: **descubrimiento simulado → candidata → vista previa de alta → token de alta → confirmación**, por HTTP y
sobre la aplicación real. Las fuentes se simulan (se parchea `DiscoveryService.search_detallada`); nada sale a la red.

Qué se prueba aquí y no en la prueba sin base de datos:
- el recorrido completo funciona con la candidata y el alta MÁS GRANDES posibles (por encima de los 8.000 antiguos);
- el máximo de la petición se acepta justo en su valor y un carácter más se rechaza SIN efectos (ni filas ni comprobante);
- un resultado que no se puede dar de alta (título largo, identificador largo, sustituto suelto de Unicode) se omite con
  un aviso y no rompe la búsqueda;
- un alta que crearía con más de 100 series parecidas no emite token (y con 100, sí);
- un título a mano con caracteres no guardables da un error claro y no un 500.
Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import text

from tests.test_alta_serie_pg import (  # noqa: F401  (fixtures reutilizadas: BD efímera y entorno sin red)
    ALTA,
    PREV,
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
from zascarr.services.discovery import DiscoveryService
from zascarr.services.tokens_revision import (
    MAX_COVER_URL,
    MAX_DESCRIPCION,
    MAX_ID_EXTERNO,
    MAX_PARECIDAS_FIRMADAS,
    MAX_TITULO,
    MAX_TOKEN_ALTA,
    MAX_TOKEN_CANDIDATA,
)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

DESCUBRIR = "/api/revision/descubrir"
LETRA_4_BYTES = "\U0001D400"          # 𝐀: una LETRA (el alta rechaza títulos «solo símbolos») de 4 bytes en UTF-8


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


#: El grupo que ya siembra `entorno` (tres archivos de Flash).
CLAVE_BASE = "Comics/Flash (1987)"


# ── 1. El recorrido completo con la candidata y el alta más grandes ───────────────────────────────

class TestRecorridoConElMayorTokenValido:

    async def test_candidata_grande_pasa_por_descubrir_previsualizar_y_confirmar(self, entorno, fuentes):
        # La carpeta (y por tanto la `clave` del grupo) es larga y no latina; el título, el identificador, la
        # descripción y la portada están en sus cotas. Cada texto de 4 bytes: es lo más grande que se puede firmar.
        carpeta = "\U00020000" * 120                                          # 120 caracteres de 4 bytes
        clave = await sembrar_grupo(entorno.banco, carpeta)
        titulo = LETRA_4_BYTES * MAX_TITULO
        ident = LETRA_4_BYTES * MAX_ID_EXTERNO
        fuentes.resultados = [res(MetadataSource.TEBEOSFERA, ident, titulo, 1987,
                                  descripcion=LETRA_4_BYTES * (MAX_DESCRIPCION + 500),
                                  cover="https://www.tebeosfera.com/img/" + "1" * (MAX_COVER_URL - 31),
                                  tradicion=ComicTradition.TEBEO)]

        d = await post(DESCUBRIR, {"clave": clave, "consulta": "Flash"})
        assert d.status_code == 200, d.text
        candidata = d.json()["candidatas"]
        assert len(candidata) == 1 and not any("omitido" in a for a in d.json()["avisos"])
        token_candidata = candidata[0]["token"]
        assert 8000 < len(token_candidata) <= MAX_TOKEN_CANDIDATA       # el límite antiguo la habría rechazado

        v = await post(PREV, {"clave": clave, "candidata": token_candidata, "tradicion": "tebeo"})
        assert v.status_code == 200, v.text
        token_alta = v.json()["token"]
        assert 8000 < len(token_alta) <= MAX_TOKEN_ALTA

        c = await post(ALTA, {"token": token_alta})
        assert c.status_code == 200, c.text
        creada = await serie_en_bd(entorno.banco)
        assert len(creada) == 1 and creada[0].title == titulo and creada[0].tebeosfera_slug == ident
        assert len(creada[0].description) == MAX_DESCRIPCION and len(creada[0].cover_url) == MAX_COVER_URL

    async def test_una_candidata_normal_sigue_siendo_pequena(self, entorno, fuentes):
        clave = await clave_del_grupo(CLAVE_BASE)
        fuentes.resultados = [res(MetadataSource.COMIC_VINE, "796", "Flash", 1987, descripcion="Velocista.")]
        d = await post(DESCUBRIR, {"clave": clave, "consulta": "Flash"})
        token = d.json()["candidatas"][0]["token"]
        assert len(token) < 1000
        v = await post(PREV, {"clave": clave, "candidata": token, "tradicion": "american"})
        assert v.status_code == 200 and len(v.json()["token"]) < 1500
        assert (await post(ALTA, {"token": v.json()["token"]})).status_code == 200


# ── 2. El exceso de tamaño se rechaza sin efectos ─────────────────────────────────────────────────

class TestElExcesoSeRechazaSinEfectos:

    async def test_candidata_de_mas_del_maximo_da_422_de_validacion_y_no_escribe_nada(self, entorno):
        clave = await clave_del_grupo(CLAVE_BASE)
        antes = await efectos(entorno.banco)
        r = await post(PREV, {"clave": clave, "candidata": "a" * (MAX_TOKEN_CANDIDATA + 1), "tradicion": "american"})
        assert r.status_code == 422 and isinstance(r.json()["detail"], list)      # lo rechaza el esquema de la petición
        assert await efectos(entorno.banco) == antes

    async def test_candidata_de_exactamente_el_maximo_llega_al_servicio_y_se_rechaza_por_no_ser_un_token(self, entorno):
        """El máximo es inclusivo: no es la longitud la que la rechaza, sino que no está firmada."""
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

    async def test_alta_de_exactamente_el_maximo_llega_al_servicio_y_se_rechaza_por_no_ser_un_token(self, entorno):
        antes = await efectos(entorno.banco)
        r = await post(ALTA, {"token": "a" * MAX_TOKEN_ALTA})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "token_invalido"
        assert await efectos(entorno.banco) == antes

    async def test_firma_proposito_y_caducidad_se_siguen_exigiendo_con_un_token_grande(self, entorno, fuentes):
        clave = await clave_del_grupo(CLAVE_BASE)
        fuentes.resultados = [res(MetadataSource.COMIC_VINE, "796", LETRA_4_BYTES * MAX_TITULO, 1987,
                                  descripcion=LETRA_4_BYTES * MAX_DESCRIPCION)]
        token = (await post(DESCUBRIR, {"clave": clave, "consulta": "Flash"})).json()["candidatas"][0]["token"]
        antes = await efectos(entorno.banco)
        manipulado = token[:-1] + ("0" if token[-1] != "0" else "1")
        r = await post(PREV, {"clave": clave, "candidata": manipulado, "tradicion": "american"})
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "token_invalido"
        otro_proposito = await post(ALTA, {"token": token})                    # una candidata no es un alta
        assert otro_proposito.status_code == 422 and otro_proposito.json()["detail"]["codigo"] == "token_invalido"
        assert await efectos(entorno.banco) == antes


# ── 3. Lo que no se puede dar de alta no se ofrece ────────────────────────────────────────────────

class TestResultadosQueNoSePuedenFirmar:

    async def test_se_omiten_con_un_aviso_y_la_busqueda_no_se_rompe(self, entorno, fuentes):
        clave = await clave_del_grupo(CLAVE_BASE)
        fuentes.resultados = [
            res(MetadataSource.COMIC_VINE, "1", "Flash", 1987),
            res(MetadataSource.COMIC_VINE, "2", "T" * (MAX_TITULO + 1), 1987),            # título que no cabe
            res(MetadataSource.TEBEOSFERA, "i" * (MAX_ID_EXTERNO + 1), "Flash Gordon", 1987),     # id que no cabe
            res(MetadataSource.COMIC_VINE, "\ud800", "Flash Azul", 1987),                  # identificador no firmable
            res(MetadataSource.COMIC_VINE, "5", "Flash \ud800 Rojo", 1987),                # sustituto suelto: se depura
            res(MetadataSource.COMIC_VINE, "6", "Flash\x00Negro", 1987, descripcion="a\x00b"),    # control: se depura
        ]
        r = await post(DESCUBRIR, {"clave": clave, "consulta": "Flash"})
        assert r.status_code == 200, r.text
        cuerpo = r.json()
        assert sorted(c["titulo"] for c in cuerpo["candidatas"]) == ["Flash", "Flash Negro", "Flash Rojo"]
        negro = next(c for c in cuerpo["candidatas"] if c["titulo"] == "Flash Negro")
        assert negro["descripcion"] == "a b"                               # el NUL de la descripción se depuró
        assert any(a.startswith("Se han omitido 3 resultado(s)") for a in cuerpo["avisos"]), cuerpo["avisos"]
        # Lo que se ofrece se puede dar de alta de verdad
        for c in cuerpo["candidatas"]:
            v = await post(PREV, {"clave": clave, "candidata": c["token"], "tradicion": "american"})
            assert v.status_code == 200, v.text

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
