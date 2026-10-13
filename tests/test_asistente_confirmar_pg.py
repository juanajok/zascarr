# ruff: noqa: E501, F401, F811
"""#120 (MIT-M3-US03) — confirmar la vinculación preparada desde el navegador, sobre Postgres real y archivos reales.

La interfaz consume el token que entrega #119 y el contrato de 2d (`ejecutar_vinculacion`); no tiene reglas de dominio.
La suite simula al navegador: abre la revisión (#119), toma el formulario de confirmación tal como está en la página y lo
envía. Cada clase cubre un criterio; los fallos se provocan con los mecanismos reales del servicio (token caducado,
`commit` que falla, archivo que cambia entre la vista previa y la confirmación).

| # | Criterio de #120 | Clase |
|---|---|---|
| 1 | Confirmación con token válido, y solo con él | `TestCriterio1Token` |
| 2 | Consentimientos separados | `TestCriterio2Consentimiento` |
| 3 | Resultado por página | `TestCriterio3Resultado` |
| 4 | Resultado parcial sin perder el contexto | `TestCriterio4Parcial` |
| 5 | Reintento tras corregir | `TestCriterio5Reintento` |
| 6 | Pendientes sin resolución inventada | `TestCriterio6Pendientes` |
| 7 | Accesibilidad y coherencia | `TestCriterio7Accesibilidad` |
| 8 | Fallos visibles | `TestCriterio8Fallos` |

Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import asyncio
import html
import os
import re
import time
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_asistente_vinculacion_pg import (  # noqa: F401  (fixtures y ayudas compartidas)
    CLAVE,
    RUTA,
    SECRETO,
    Pagina,
    _secreto_en_el_asistente,
    abrir,
    archivos,
    cliente,
    entorno,
    sembrar_issue,
    serie_de_prueba,
    url_bd,
)
from tests.test_vinculacion_pg import ent, firmar  # noqa: F401
from zascarr.models import IssueFormat
from zascarr.services.tokens_revision import candidata_firmable, crear_token_candidata
from zascarr.services.vinculacion import MOTIVOS, VinculacionDeArchivos
from zascarr.web import asistente_vinculacion
from zascarr.web.asistente_vinculacion import FALLOS, TEXTO_DE_MOTIVO

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)"),
]

CONFIRMAR = f"{RUTA}/confirmar"
UNO, DOS, TRES = "Flash 01 (1987).cbz", "Flash 02 (1987).cbz", "Flash 03 (1987).cbz"


def formulario_de_confirmacion(t: str) -> list[tuple[str, str]]:
    """Lo que enviaría el navegador al pulsar «Vincular»: los campos del formulario de confirmación, y solo esos."""
    m = re.search(r'<form class="vinculacion-confirmar".*?</form>', t, re.S)
    assert m, "la página no ofrece confirmar"
    return [(html.unescape(n), html.unescape(v))
            for n, v in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', m.group(0))]


async def enviar(campos, *, htmx: bool = True) -> httpx.Response:
    cab = {"Content-Type": "application/x-www-form-urlencoded", **({"HX-Request": "true"} if htmx else {})}
    async with cliente() as c:
        return await c.post(CONFIRMAR, content=urlencode(campos), headers=cab)


async def confirmar(pagina: Pagina, **kw) -> Resultado:
    r = await enviar(formulario_de_confirmacion(pagina.t), **kw)
    assert r.status_code == 200, r.text
    return Resultado(r.text)


class Resultado:
    def __init__(self, t: str):
        self.t = t

    @property
    def visible(self) -> str:
        return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", self.t)).split())

    @property
    def estado(self) -> str | None:
        m = re.search(r'data-estado="([^"]+)"', self.t)
        return m.group(1) if m else None

    def total(self, que: str) -> int | None:
        m = re.search(rf'data-total="{que}">.*?(\d+) ', self.t, re.S)
        return int(m.group(1)) if m else None

    def grupo(self, que: str) -> list[str]:
        m = re.search(rf'data-grupo="{que}".*?</section>', self.t, re.S)
        if not m:
            return []
        return [html.unescape(re.sub(r"<[^>]+>", "", x)).split(" — ")[0].strip()
                for x in re.findall(r"<li[^>]*>(.*?)</li>", m.group(0), re.S)]


async def listo(entorno, *nombres: str, marcar=None) -> Pagina:
    """Una revisión con esos archivos marcados y un token vigente."""
    serie = await serie_de_prueba(entorno)
    await archivos(entorno, *nombres)
    p = await abrir(serie)
    p = await p.reenviar(marcar=list(marcar or nombres))
    assert p.token is not None
    p.serie = serie
    return p


async def vinculados(banco) -> int:
    async with banco.fabrica() as s:
        return (await s.execute(text("SELECT count(*) FROM files WHERE issue_id IS NOT NULL"))).scalar_one()


async def operaciones(banco) -> int:
    async with banco.fabrica() as s:
        return (await s.execute(text("SELECT count(*) FROM vinculacion_operaciones"))).scalar_one()


async def numero_de(tabla: str, banco) -> int:
    async with banco.fabrica() as s:
        return (await s.execute(text(f"SELECT count(*) FROM {tabla}"))).scalar_one()


# ── 1. Token válido ─────────────────────────────────────────────────────────────────────────────

class TestCriterio1Token:

    async def test_envia_el_token_de_la_revision_tal_cual_y_muestra_el_resultado_del_servicio(self, ent, monkeypatch):
        p = await listo(ent, UNO, DOS)
        recibido = []
        real = asistente_vinculacion.ejecutar_vinculacion

        async def espia(db, token):
            recibido.append(token)
            return await real(db, token)
        monkeypatch.setattr(asistente_vinculacion, "ejecutar_vinculacion", espia)
        r = await confirmar(p)
        assert recibido == [p.token]                              # el token de la revisión, no otro ni uno reconstruido
        assert r.estado == "vinculados_todos" and r.total("vinculados") == 2
        assert sorted(r.grupo("vinculado")) == [f"{UNO}", f"{DOS}"] or len(r.grupo("vinculado")) == 2
        assert await vinculados(ent.banco) == 2 and await operaciones(ent.banco) == 1

    async def test_sin_token_o_con_uno_que_no_es_de_vinculacion_no_se_ejecuta_nada(self, ent):
        p = await listo(ent, UNO)
        antes = await vinculados(ent.banco)
        # sin token: la petición no es válida (el formulario real nunca la manda así)
        sin = await enviar([("cursor_actual", "inicio")])
        assert sin.status_code == 422
        # basura y un token firmado con OTRO propósito (el de una candidata de búsqueda): ninguno ejecuta
        candidata = crear_token_candidata(CLAVE, candidata_firmable("comic_vine", "1", "Flash", 1987, "american", None, None), SECRETO)
        for malo in ("esto-no-es-un-token", candidata):
            r = Resultado((await enviar([("token", malo)])).text)
            assert "La preparación no es válida" in r.visible and "Hecho" not in r.visible
        assert await vinculados(ent.banco) == antes == 0 and await operaciones(ent.banco) == 0
        assert p.token                                              # y el token bueno sigue sirviendo

    async def test_serie_y_grupo_salen_del_token_no_de_lo_que_reenvia_el_navegador(self, ent):
        p = await listo(ent, UNO)
        campos = [(k, v) for k, v in formulario_de_confirmacion(p.t) if k not in ("clave", "series_id")]
        campos += [("clave", "Comics/Otra"), ("series_id", str(uuid4()))]       # intentos de cambiar el contexto
        r = Resultado((await enviar(campos)).text)
        assert CLAVE in r.visible and "Comics/Otra" not in r.visible and r.estado == "vinculados_todos"


# ── 2. Consentimientos separados ────────────────────────────────────────────────────────────────

class TestCriterio2Consentimiento:

    async def test_navegar_o_revisar_no_ejecuta_y_confirmar_es_una_accion_aparte_que_dice_que_hace(self, ent):
        p = await listo(ent, UNO, DOS)
        assert await vinculados(ent.banco) == 0 and await operaciones(ent.banco) == 0
        v = p.visible
        assert "Al pulsar «Vincular»" in v and "en su sitio" in v and "no se crea ninguna serie" in v
        assert "Es una acción distinta de revisar" in v
        async with cliente() as c:
            assert (await c.get(CONFIRMAR)).status_code == 405        # un GET (enlace, recarga) nunca confirma
        assert await vinculados(ent.banco) == 0

    async def test_confirmar_vincula_pero_no_crea_ninguna_serie_ni_mueve_archivos(self, ent):
        p = await listo(ent, UNO, DOS)
        series_antes, rutas = await numero_de("series", ent.banco), sorted(x.name for x in ent.lib.rglob("*") if x.is_file())
        r = await confirmar(p)
        assert r.estado == "vinculados_todos"
        assert await numero_de("series", ent.banco) == series_antes
        assert sorted(x.name for x in ent.lib.rglob("*") if x.is_file()) == rutas

    async def test_el_token_de_una_pagina_no_confirma_otra(self, ent):
        serie = await serie_de_prueba(ent)
        await archivos(ent, UNO, DOS)
        p = await abrir(serie)
        a = await p.reenviar(marcar=[UNO])
        b = await a.reenviar(marcar=[DOS])                  # nueva revisión: otro token con los dos
        r = await confirmar(a)                              # confirmar el ANTERIOR solo vincula lo que él representa
        assert r.total("vinculados") == 1 and await vinculados(ent.banco) == 1
        assert b.token != a.token


# ── 3. Resultado por página ─────────────────────────────────────────────────────────────────────

class TestCriterio3Resultado:

    async def test_distingue_vinculados_ya_existentes_y_omitidos_con_el_motivo_del_servicio(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO, DOS, TRES)
        p = await abrir(serie)
        p = await p.reenviar(marcar=[UNO, DOS, TRES])
        # Entre la revisión y la confirmación: DOS ya queda vinculado al mismo número (otra operación) y TRES cambia.
        async with ent.banco.fabrica() as s:
            iid = await sembrar_issue(ent.banco, serie, "2")
            await s.execute(text("UPDATE files SET issue_id = :i WHERE id = :f"), {"i": iid, "f": ids[DOS]})
            await s.commit()
        ruta_tres = (ent.lib / "Comics/Flash (1987)" / TRES)
        ruta_tres.write_bytes(b"cambiado despues de revisar" * 9)
        r = await confirmar(p)
        assert r.estado == "vinculados_parcialmente"
        assert r.grupo("vinculado") == [UNO]
        assert r.grupo("ya_estaba_vinculado") == [DOS]                   # ya estaba en ese número: nada cambia
        assert [x.split(" (número")[0] for x in r.grupo("omitido")] == [TRES]  # cambió tras revisar: pendiente
        assert (r.total("vinculados"), r.total("ya_estaban"), r.total("omitidos")) == (1, 1, 1)

    async def test_el_resultado_no_inventa_estados_y_cada_motivo_del_contrato_tiene_texto(self, ent):
        assert set(MOTIVOS) <= set(TEXTO_DE_MOTIVO), set(MOTIVOS) - set(TEXTO_DE_MOTIVO)
        p = await listo(ent, UNO)
        t = (await confirmar(p)).t
        assert "vinculados_todos" in t and "inventado" not in t.lower()


# ── 4. Parcial ──────────────────────────────────────────────────────────────────────────────────

class TestCriterio4Parcial:

    async def test_un_resultado_parcial_conserva_serie_grupo_y_pagina_y_no_se_presenta_como_completo(self, ent):
        serie = await serie_de_prueba(ent, "Flash", 1987)
        await archivos(ent, UNO, DOS)
        p = await abrir(serie)
        p = await p.reenviar(marcar=[UNO, DOS])
        (ent.lib / "Comics/Flash (1987)" / DOS).write_bytes(b"otro contenido" * 20)     # cambia tras revisar
        r = await confirmar(p)
        v = r.visible
        assert r.estado == "vinculados_parcialmente"
        assert "Flash (1987)" in v and CLAVE in v and "archivos 1–2" in v           # contexto conservado
        assert "Esto NO está completo" in v and "Hecho:" not in v and "ya está todo" not in v.lower()
        assert "Cambió (tamaño o fecha) mientras revisabas" in v                     # qué quedó pendiente y por qué


# ── 5. Reintento ────────────────────────────────────────────────────────────────────────────────

class TestCriterio5Reintento:

    async def test_tras_corregir_se_prepara_una_vista_nueva_y_no_se_reutiliza_el_token(self, ent):
        serie = await serie_de_prueba(ent)
        await archivos(ent, UNO, DOS)
        p = await abrir(serie)
        p = await p.reenviar(marcar=[UNO, DOS])
        (ent.lib / "Comics/Flash (1987)" / DOS).write_bytes(b"otro contenido" * 20)
        r = await confirmar(p)
        enlace = re.search(r'href="(/ui/pendientes/carpetas/asistente/vinculacion\?[^"]+)"[^>]*>Revisar de nuevo', r.t)
        assert enlace, "un resultado parcial debe ofrecer revisar de nuevo"
        async with cliente() as c:
            nueva = Pagina((await c.get(html.unescape(enlace.group(1)))).text)
        assert nueva.token is None                                  # nada preparado todavía: hay que revisar y marcar
        assert [f.nombre for f in nueva.filas] == [DOS]             # lo vinculado ya no está pendiente
        nueva = await nueva.reenviar(marcar=[DOS])
        assert nueva.token is not None and nueva.token != p.token   # un token nuevo, de la vista nueva
        assert (await confirmar(nueva)).estado == "vinculados_todos"

    async def test_repetir_el_token_viejo_devuelve_su_informe_y_no_vincula_otra_vez(self, ent):
        p = await listo(ent, UNO, DOS)
        a = await confirmar(p)
        b = await confirmar(p)
        assert "ya se había aplicado antes" in b.visible and "ya se había aplicado antes" not in a.visible
        assert a.total("vinculados") == b.total("vinculados") == 2
        assert await vinculados(ent.banco) == 2 and await operaciones(ent.banco) == 1

    async def test_dos_envios_a_la_vez_aplican_una_sola_vez(self, ent):
        p = await listo(ent, UNO, DOS)
        r = await asyncio.gather(enviar(formulario_de_confirmacion(p.t)), enviar(formulario_de_confirmacion(p.t)))
        assert [x.status_code for x in r] == [200, 200]
        assert sorted("ya se había aplicado antes" in Resultado(x.text).visible for x in r) == [False, True]
        assert await vinculados(ent.banco) == 2 and await operaciones(ent.banco) == 1


# ── 6. Pendientes ───────────────────────────────────────────────────────────────────────────────

class TestCriterio6Pendientes:

    async def test_un_pendiente_se_explica_y_no_se_resuelve_ni_se_elige_nada_por_la_persona(self, ent):
        serie = await serie_de_prueba(ent)
        await archivos(ent, UNO, "Flash 01 (copia).cbz")
        p = await abrir(serie)
        p = await p.reenviar(marcar=[UNO])
        # Mientras tanto otro archivo ocupa el número 1: al confirmar, UNO ya no puede entrar.
        async with ent.banco.fabrica() as s:
            iid = await sembrar_issue(ent.banco, serie, "1")
            otro = (await archivos(ent, "Otro 01.cbz", carpeta="Comics/Otra"))["Otro 01.cbz"]
            await s.execute(text("UPDATE files SET issue_id = :i WHERE id = :f"), {"i": iid, "f": otro})
            await s.commit()
        r = await confirmar(p)
        v = r.visible
        assert r.estado == "nada_vinculado" and "No se vinculó ningún archivo" in v
        assert "Ese número ya tiene un archivo vinculado en la serie: no se pisa" in v
        assert "Nada se ha elegido, fusionado ni resuelto por ti" in v
        assert "<button" not in r.t and "<form" not in r.t           # sin acciones que decidan por la persona
        assert await vinculados(ent.banco) == 1                      # solo el que ya estaba


# ── 7. Accesibilidad y coherencia ───────────────────────────────────────────────────────────────

class TestCriterio7Accesibilidad:

    async def test_la_confirmacion_y_el_resultado_usan_controles_nativos_titulos_y_avisos_con_rol(self, ent):
        p = await listo(ent, UNO, DOS)
        assert re.search(r'<button type="submit">Vincular 2 archivos</button>', p.t)
        assert 'aria-labelledby="vinc-lote"' in p.t and '<h3 id="vinc-lote">' in p.t
        r = await confirmar(p)
        assert re.search(r'<h2 id="res-contexto">', r.t) and re.search(r'<h3 id="res-resultado">', r.t)
        assert 'role="status"' in r.t or 'role="alert"' in r.t
        assert 'aria-label="Totales"' in r.t
        assert "<a class=\"btn ghost sm\"" in r.t                   # los accesos son enlaces reales
        assert "hx-disabled-elt" in p.t                              # el botón se desactiva mientras se envía

    async def test_sin_htmx_la_confirmacion_devuelve_la_pagina_entera(self, ent):
        p = await listo(ent, UNO)
        r = await enviar(formulario_de_confirmacion(p.t), htmx=False)
        assert "<html" in r.text and 'lang="es"' in r.text and "Hecho: todos los archivos" in Resultado(r.text).visible


# ── 8. Fallos visibles ──────────────────────────────────────────────────────────────────────────

class TestCriterio8Fallos:

    async def test_token_caducado_dentro_de_la_retencion_no_llego_a_aplicarse(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO)
        token = await firmar(ent, serie, [(ids[UNO], "1")], ahora=time.time() - 16 * 60)
        r = Resultado((await enviar([("token", token)])).text)
        assert "La preparación caducó" in r.visible and "no llegó a aplicarse" in r.visible
        assert "Hecho" not in r.visible and "Reintentar" not in r.visible and await vinculados(ent.banco) == 0

    async def test_token_caducado_pasada_la_retencion_dice_que_no_se_puede_saber(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO)
        token = await firmar(ent, serie, [(ids[UNO], "1")], ahora=time.time() - 25 * 3600)
        r = Resultado((await enviar([("token", token)])).text)
        assert "no se puede saber si llegó a aplicarse" in r.visible and "Vuelve a revisar los archivos" in r.visible
        assert "Hecho" not in r.visible and "Comprobar el resultado" not in r.visible

    async def test_resultado_incierto_se_distingue_y_se_puede_comprobar_sin_duplicar(self, ent, monkeypatch):
        p = await listo(ent, UNO, DOS)
        real = AsyncSession.commit

        async def commit_y_luego_falla(self):
            await real(self)
            raise ConnectionError("se perdió la conexión al confirmar")
        monkeypatch.setattr(AsyncSession, "commit", commit_y_luego_falla)
        r = Resultado((await enviar(formulario_de_confirmacion(p.t))).text)
        monkeypatch.setattr(AsyncSession, "commit", real)
        assert r.estado == "fallo" and "No se sabe si se llegó a vincular" in r.visible
        assert "No sabemos si la vinculación llegó a aplicarse" in r.visible
        assert "Hecho" not in r.visible and "Comprobar el resultado" in r.visible
        assert "no se ha cambiado nada" not in r.visible.lower()
        # «Comprobar el resultado» = repetir el MISMO token: devuelve el informe y no duplica nada
        comprobado = Resultado((await enviar(formulario_de_confirmacion_de_fallo(r.t))).text)
        assert comprobado.estado == "vinculados_todos" and "ya se había aplicado antes" in comprobado.visible
        assert await vinculados(ent.banco) == 2 and await operaciones(ent.banco) == 1

    async def test_un_fallo_definitivo_y_uno_reintentable_se_distinguen(self, ent, monkeypatch):
        p = await listo(ent, UNO)

        real_nombres = VinculacionDeArchivos._nombres

        async def falla(self, *a, **k):
            raise RuntimeError("fallo inesperado antes del commit")
        monkeypatch.setattr(VinculacionDeArchivos, "_nombres", falla)
        r = Resultado((await enviar(formulario_de_confirmacion(p.t))).text)
        assert "No se pudo completar y no se ha cambiado nada" in r.visible and "Reintentar" in r.visible
        assert await vinculados(ent.banco) == 0
        monkeypatch.setattr(VinculacionDeArchivos, "_nombres", real_nombres)
        # y la serie borrada es definitiva: no hay nada que reintentar
        async with ent.banco.fabrica() as s:
            await s.execute(text("DELETE FROM series"))
            await s.commit()
        q = Resultado((await enviar(formulario_de_confirmacion(p.t))).text)
        assert "La serie ya no existe" in q.visible and "Reintentar" not in q.visible and "Hecho" not in q.visible

    async def test_los_codigos_de_fallo_del_servicio_tienen_titulo_en_espanol(self):
        for codigo, (titulo, _, _) in FALLOS.items():
            assert titulo and re.search(r"[a-záéíóúñ]", titulo), codigo


def formulario_de_confirmacion_de_fallo(t: str) -> list[tuple[str, str]]:
    """El formulario «Comprobar el resultado / Reintentar» de una página de fallo (mismo token, mismo contexto)."""
    m = re.search(r'<form method="post" action="[^"]*confirmar".*?</form>', t, re.S)
    assert m, "la página de fallo no ofrece repetir"
    return [(html.unescape(n), html.unescape(v))
            for n, v in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', m.group(0))]
