# ruff: noqa: E501, F401, F811
"""#119 (MIT-M3-US02) — «Revisar selección y números»: la interfaz de la vista previa de la vinculación (2c), sobre
Postgres real y archivos reales en un directorio temporal. La suite simula lo que hace el navegador: lee el formulario
de la página, cambia lo que cambiaría la persona y lo reenvía (`Pagina.reenviar`).

| # | Criterio de #119 | Clase |
|---|---|---|
| 1, 12 | Entrada con grupo y serie local; nada marcado | `TestCriterio1y12Entrada` |
| 2 | Páginas de hasta 100 y alcance de la revisión | `TestCriterio2Paginas` |
| 3 | Número propuesto, origen y edición | `TestCriterio3Numero` |
| 4 | Número ausente / ambiguo | `TestCriterio4AusenteYAmbiguo` |
| 5 | Coincidencias entre archivos | `TestCriterio5Repetidos` |
| 6 | Publicaciones existentes y colisiones | `TestCriterio6Existentes` |
| 7, 8 | Marcado / marcable / incluido y subconjunto del token | `TestCriterio7y8Seleccion` |
| 9 | Renovación tras cambiar decisiones | `TestCriterio9Renovacion` |
| 10 | Sin efectos de vinculación | `TestCriterio10SinEfectos` |
| 11 | Borrador al navegar | `TestCriterio11Borrador` |

Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import html
import json
import os
import re
from dataclasses import dataclass
from types import SimpleNamespace
from urllib.parse import urlencode
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from tests.test_vinculacion_previa_pg import (  # noqa: F401  (fixtures y ayudas compartidas)
    CLAVE,
    SECRETO,
    archivos,
    cliente,
    entorno,
    huella_disco,
    instantanea,
    serie_de_prueba,
    url_bd,
)
from zascarr.models import Issue, IssueFormat
from zascarr.services.vinculacion_previa import LIMITE_ARCHIVOS
from zascarr.web import asistente_vinculacion
from zascarr.web.asistente_vinculacion import INICIO

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)"),
]

RUTA = "/ui/pendientes/carpetas/asistente/vinculacion"
FILA = re.compile(
    r'<li class="vinc-fila"\s+data-id="([^"]+)"\s+data-estado="([^"]+)"\s+data-marcado="(\d)"\s+data-marcable="(\d)"\s+'
    r'data-incluido="(\d)"\s+data-numero-origen="([^"]+)">(.*?)</li>', re.S)


@pytest.fixture(autouse=True)
def _secreto_en_el_asistente(monkeypatch):
    monkeypatch.setattr(asistente_vinculacion, "get_settings", lambda: SimpleNamespace(secret_key=SECRETO))


@dataclass
class Fila:
    id: str
    nombre: str
    estado: str
    marcado: bool
    marcable: bool
    incluido: bool
    origen: str
    numero: str
    cuerpo: str


class Pagina:
    """Una página ya pintada y lo que el navegador reenviaría si la persona toca algo."""

    def __init__(self, t: str, clave: str = CLAVE):
        self.t = t
        self.clave = clave
        self.filas: list[Fila] = []
        for fid, estado, marcado, marcable, incluido, origen, cuerpo in FILA.findall(t):
            nombre = html.unescape(re.search(r'<span class="nombre-archivo">(.*?)</span>', cuerpo, re.S).group(1)).strip()
            n = re.search(rf'name="numero:{fid}" value="([^"]*)"', cuerpo)
            self.filas.append(Fila(fid, nombre, estado, marcado == "1", marcable == "1", incluido == "1", origen,
                                   html.unescape(n.group(1)) if n else "", cuerpo))

    def fila(self, nombre: str) -> Fila:
        return next(f for f in self.filas if f.nombre == nombre)

    @property
    def visible(self) -> str:
        return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", self.t)).split())

    @property
    def token(self) -> str | None:
        m = re.search(r'class="card lote-listo" data-token="([^"]+)"', self.t)
        return m.group(1) if m else None

    def oculto(self, nombre: str) -> str:
        m = re.search(rf'name="{nombre}" value="([^"]*)"', self.t)
        return html.unescape(m.group(1)) if m else ""

    def total(self, que: str) -> int:
        m = re.search(rf'data-total="{que}">.*?(\d+) ', self.t, re.S)
        return int(m.group(1))

    def formulario(self, *, marcar=(), desmarcar=(), numeros=None, ir_a=None) -> list[tuple[str, str]]:
        """Lo que serializaría el navegador: campos ocultos, los marcados que siguen marcados y cada número."""
        numeros = numeros or {}
        campos = [(k, self.oculto(k)) for k in ("clave", "series_id", "cursor_actual", "pagina_desde", "pagina_hasta", "borradores")]
        quitar = set(desmarcar)
        for f in self.filas:
            if f.estado in ("ya_vinculado", "fuera_de_la_pagina"):
                continue
            if (f.marcado and f.nombre not in quitar) or f.nombre in marcar:
                campos.append(("marcar", f.id))
            campos.append((f"numero:{f.id}", numeros.get(f.nombre, f.numero)))
            campos.append((f"numero_base:{f.id}", self._base(f)))
            campos.append((f"numero_origen:{f.id}", f.origen))
        if ir_a:
            campos.append(("ir_a", ir_a))
        return campos

    def _base(self, f: Fila) -> str:
        m = re.search(rf'name="numero_base:{f.id}" value="([^"]*)"', f.cuerpo)
        return html.unescape(m.group(1)) if m else ""

    async def reenviar(self, **kw) -> Pagina:
        r = await enviar(self.formulario(**kw))
        assert r.status_code == 200, r.text
        return Pagina(r.text, self.clave)

    def siguiente(self) -> str:
        m = re.search(r'name="ir_a" value="([^"]+)"[^>]*>Página siguiente', self.t)
        assert m, "no hay página siguiente"
        return html.unescape(m.group(1))


async def enviar(campos: list[tuple[str, str]], *, htmx: bool = True) -> httpx.Response:
    """POST de un formulario tal como lo manda el navegador (httpx no acepta una lista de pares en `data`)."""
    cabeceras = {"Content-Type": "application/x-www-form-urlencoded", **({"HX-Request": "true"} if htmx else {})}
    async with cliente() as c:
        return await c.post(f"{RUTA}/revisar", content=urlencode(campos), headers=cabeceras)


async def abrir(serie, clave: str = CLAVE) -> Pagina:
    async with cliente() as c:
        r = await c.get(RUTA, params={"clave": clave, "series_id": str(serie)})
    assert r.status_code == 200, r.text
    return Pagina(r.text, clave)


async def sembrar_issue(banco, serie, numero: str, *, volume: int = 1, formato=IssueFormat.SINGLE_ISSUE):
    iid = uuid4()
    async with banco.fabrica() as s:
        s.add(Issue(id=iid, series_id=serie, issue_number=numero, volume=volume, format=formato))
        await s.commit()
    return iid


async def estado_de_la_base(banco) -> dict:
    return await instantanea(banco)


# ── 1 y 12. Entrada ─────────────────────────────────────────────────────────────────────────────

class TestCriterio1y12Entrada:

    async def test_identifica_grupo_y_serie_y_todo_empieza_sin_marcar_ni_token(self, entorno):
        serie = await serie_de_prueba(entorno, "Flash", 1987)
        await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        p = await abrir(serie)
        assert CLAVE in p.visible and "Flash (1987)" in p.visible
        assert [f.nombre for f in p.filas] == ["Flash 01 (1987).cbz", "Flash 02 (1987).cbz"]
        assert all(not f.marcado for f in p.filas) and p.token is None
        assert p.total("marcados") == 0 and p.total("a_vincular") == 0
        assert "No has marcado ningún archivo" in p.visible

    @pytest.mark.parametrize("series_id", ["", "no-es-un-uuid", "eyJhbGciOi.candidata.firmada"])
    async def test_sin_una_serie_local_valida_no_se_prepara_nada(self, entorno, series_id):
        await archivos(entorno, "Flash 01 (1987).cbz")
        async with cliente() as c:
            r = await c.get(RUTA, params={"clave": CLAVE, "series_id": series_id})
        p = Pagina(r.text)
        assert r.status_code == 200 and p.filas == [] and p.token is None
        assert "Hace falta una serie de tu biblioteca" in p.visible

    async def test_una_serie_que_no_existe_o_un_grupo_que_no_existe_se_dicen_y_no_preparan(self, entorno):
        await archivos(entorno, "Flash 01 (1987).cbz")
        async with cliente() as c:
            ajena = await c.get(RUTA, params={"clave": CLAVE, "series_id": str(uuid4())})
            sin_grupo = await c.get(RUTA, params={"clave": "Comics/NoExiste", "series_id": str(await serie_de_prueba(entorno))})
        assert "ya no existe en tu biblioteca" in Pagina(ajena.text).visible and Pagina(ajena.text).filas == []
        assert "ya no tiene registros pendientes" in Pagina(sin_grupo.text).visible

    async def test_sin_clave_de_firma_se_dice_y_no_hay_token(self, entorno, monkeypatch):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        monkeypatch.setattr(asistente_vinculacion, "get_settings", lambda: SimpleNamespace(secret_key=""))
        p = await abrir(serie)
        assert "no tiene clave para firmar" in p.visible and p.filas == [] and p.token is None

    async def test_la_busqueda_del_asistente_ofrece_preparar_con_la_serie_local_que_ya_se_tiene(self, entorno, monkeypatch):
        """Entrada desde la elección de una serie que YA está en la biblioteca (sin el tramo de alta)."""
        from tests.test_descubrimiento_grupo_pg import res
        from zascarr.api import revision as api_revision
        from zascarr.models import MetadataSource
        from zascarr.services.discovery import Busqueda, DiscoveryService
        from zascarr.web import asistente_carpetas
        serie = await serie_de_prueba(entorno, "Flash", 1987, comic_vine_id=796)
        await archivos(entorno, "Flash 01 (1987).cbz")

        async def buscar(self, consulta, limit=10):
            return Busqueda([res(MetadataSource.COMIC_VINE, "796", "Flash", 1987)], [], {"comic_vine": "ok"})
        monkeypatch.setattr(DiscoveryService, "search_detallada", buscar)
        monkeypatch.setattr(asistente_carpetas, "get_settings", lambda: SimpleNamespace(secret_key=SECRETO))
        monkeypatch.setattr(api_revision, "get_settings", lambda: SimpleNamespace(secret_key=SECRETO))
        monkeypatch.setattr(api_revision, "MIN_INTERVALO_S", 0.0)
        api_revision.reiniciar_ritmo_para_pruebas()
        async with cliente() as c:
            r = await c.post("/ui/pendientes/carpetas/asistente/buscar", data={"clave": CLAVE, "consulta": "Flash"})
        enlace = re.search(r'href="(/ui/pendientes/carpetas/asistente/vinculacion\?[^"]+)"', r.text)
        assert enlace, "la candidata que ya está en la biblioteca debe ofrecer preparar la vinculación"
        destino = html.unescape(enlace.group(1))
        assert f"series_id={serie}" in destino and "clave=Comics/Flash%20%281987%29" in destino
        async with cliente() as c:                                   # y ese enlace abre la preparación para esa serie
            pagina = Pagina((await c.get(destino)).text)
        assert pagina.filas and "Flash (1987)" in pagina.visible and all(not f.marcado for f in pagina.filas)


# ── 2. Páginas ──────────────────────────────────────────────────────────────────────────────────

class TestCriterio2Paginas:

    async def test_hasta_cien_por_pagina_ordenados_y_el_alcance_se_explica(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(1, LIMITE_ARCHIVOS + 6)))
        p = await abrir(serie)
        assert len(p.filas) == LIMITE_ARCHIVOS
        assert [f.nombre for f in p.filas] == sorted(f.nombre for f in p.filas)
        assert "solo para los archivos de esta página" in p.visible and "archivos 1–100" in p.visible
        segunda = await p.reenviar(ir_a=p.siguiente())
        assert [f.nombre for f in segunda.filas] == [f"Flash {i:03d} (1987).cbz" for i in range(101, 106)]
        assert "archivos 101–105" in segunda.visible and "Primera página" in segunda.visible

    async def test_lo_marcado_en_otra_pagina_no_se_presenta_como_evaluado_ni_entra_en_su_token(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(1, LIMITE_ARCHIVOS + 4)))
        p = await abrir(serie)
        p = await p.reenviar(marcar=["Flash 001 (1987).cbz"])
        assert p.token is not None and p.total("a_vincular") == 1
        segunda = await p.reenviar(ir_a=p.siguiente())
        assert segunda.token is None and segunda.total("marcados") == 0
        assert not any(f.estado == "fuera_de_la_pagina" for f in segunda.filas)
        assert "Trabajo guardado en otras páginas" in segunda.visible and "1 marcado" in segunda.visible

    async def test_un_cursor_inventado_se_rechaza_con_la_pagina_limpia(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        p = await abrir(serie)
        campos = p.formulario(ir_a="esto-no-es-un-cursor")
        r = await enviar(campos)
        q = Pagina(r.text)
        assert r.status_code == 200 and [f.nombre for f in q.filas] == ["Flash 01 (1987).cbz"]
        assert "No se ha podido reconstruir" in q.visible and q.token is None


# ── 3. Número, origen y edición ─────────────────────────────────────────────────────────────────

class TestCriterio3Numero:

    async def test_el_numero_del_nombre_y_el_escrito_por_la_persona_se_distinguen(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        p = await abrir(serie)
        assert (p.fila("Flash 01 (1987).cbz").origen, p.fila("Flash 01 (1987).cbz").numero) == ("nombre", "1")
        assert "Sale del nombre del archivo" in p.visible
        q = await p.reenviar(numeros={"Flash 01 (1987).cbz": "7"})
        f = q.fila("Flash 01 (1987).cbz")
        assert (f.origen, f.numero) == ("persona", "7")
        assert q.fila("Flash 02 (1987).cbz").origen == "nombre"          # lo no tocado sigue siendo del nombre
        assert "Escrito por ti (el nombre decía 1)" in q.visible

    async def test_un_texto_vacio_elimina_el_numero_de_la_propuesta(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        p = await abrir(serie)
        q = await p.reenviar(numeros={"Flash 01 (1987).cbz": ""}, marcar=["Flash 01 (1987).cbz"])
        f = q.fila("Flash 01 (1987).cbz")
        assert f.numero == "" and f.estado == "requiere_numero" and not f.marcable and q.token is None
        assert "Falta el número" in q.visible

    async def test_un_numero_del_nombre_no_valido_se_trata_como_ausente_sin_truncar(self, entorno):
        serie = await serie_de_prueba(entorno)
        largo = "1" * 25
        await archivos(entorno, f"Flash #{largo} (1987).cbz")
        p = await abrir(serie)
        f = p.filas[0]
        assert f.estado == "requiere_numero" and f.numero == "" and f.origen == "ninguno"
        assert "más de 20 caracteres" in p.visible and largo not in html.unescape(re.sub(r"<[^>]+>", "", p.t.split("Resumen")[0]).replace(f"Flash #{largo} (1987).cbz", ""))

    async def test_un_numero_escrito_no_valido_no_se_aplica_se_avisa_y_no_se_pierde_el_resto(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        p = await abrir(serie)
        q = await p.reenviar(numeros={"Flash 01 (1987).cbz": "9" * 30, "Flash 02 (1987).cbz": "5"})
        assert q.fila("Flash 01 (1987).cbz").origen == "nombre"            # el inválido no se aplicó
        assert q.fila("Flash 02 (1987).cbz").numero == "5"                 # y el válido sí
        assert "1 número(s) no se han aplicado" in q.visible


# ── 4. Ausente y ambiguo ────────────────────────────────────────────────────────────────────────

class TestCriterio4AusenteYAmbiguo:

    async def test_requiere_numero_y_numero_ambiguo_se_distinguen_y_no_son_marcables(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 05 (1987).cbz", "Sin numero.cbz")
        await sembrar_issue(entorno.banco, serie, "5", volume=1)
        await sembrar_issue(entorno.banco, serie, "5", volume=2)
        p = await abrir(serie)
        ambiguo, ausente = p.fila("Flash 05 (1987).cbz"), p.fila("Sin numero.cbz")
        assert ambiguo.estado == "numero_ambiguo" and ausente.estado == "requiere_numero"
        assert not ambiguo.marcable and not ausente.marcable
        assert "más de un número así" in p.visible and "Falta el número" in p.visible
        assert "disabled" in ambiguo.cuerpo and "disabled" in ausente.cuerpo
        q = await p.reenviar(marcar=["Flash 05 (1987).cbz", "Sin numero.cbz"])
        assert q.token is None and q.total("a_vincular") == 0 and q.total("marcados_bloqueados") == 2


# ── 5. Repetidos ────────────────────────────────────────────────────────────────────────────────

class TestCriterio5Repetidos:

    async def _dos_con_el_mismo_numero(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 03 (1987).cbz", "Flash 03 (copia).cbz")
        return serie

    async def test_la_coincidencia_se_muestra_y_no_bloquea_por_si_sola(self, entorno):
        p = await abrir(await self._dos_con_el_mismo_numero(entorno))
        assert "Mismo número que: Flash 03 (copia).cbz" in p.visible
        assert all(f.marcable for f in p.filas) and p.token is None

    async def test_marcar_solo_uno_lo_incluye_y_marcar_los_dos_los_excluye_a_ambos(self, entorno):
        p = await abrir(await self._dos_con_el_mismo_numero(entorno))
        uno = await p.reenviar(marcar=["Flash 03 (1987).cbz"])
        assert uno.fila("Flash 03 (1987).cbz").incluido and not uno.fila("Flash 03 (copia).cbz").incluido
        assert uno.token is not None
        los_dos = await uno.reenviar(marcar=["Flash 03 (copia).cbz"])
        assert all(f.estado == "numero_repetido_en_el_grupo" and not f.incluido for f in los_dos.filas)
        assert los_dos.token is None and "marca solo uno de los dos" in los_dos.visible


# ── 6. Existentes y colisiones ──────────────────────────────────────────────────────────────────

class TestCriterio6Existentes:

    async def test_issue_existente_se_reutiliza_y_las_colisiones_bloquean(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz", "Flash Omnigold 03.cbz")
        await sembrar_issue(entorno.banco, serie, "1")                                     # sin archivos: reutilizable
        con_archivo = await sembrar_issue(entorno.banco, serie, "2")
        await archivos(entorno, "Otro 02.cbz", carpeta="Comics/Otra", issue_id=con_archivo)   # ya tiene un archivo
        await sembrar_issue(entorno.banco, serie, "3", formato=IssueFormat.SINGLE_ISSUE)       # edición distinta (omnigold)
        p = await abrir(serie)
        uno, dos, tres = (p.fila(n) for n in ("Flash 01 (1987).cbz", "Flash 02 (1987).cbz", "Flash Omnigold 03.cbz"))
        assert uno.marcable and "La serie ya tiene esta publicación sin archivos" in uno.cuerpo
        assert dos.estado == "numero_ya_existe" and not dos.marcable and "ya tiene 1 archivo" in html.unescape(dos.cuerpo)
        assert tres.estado == "colision_de_edicion" and not tres.marcable
        q = await p.reenviar(marcar=["Flash 01 (1987).cbz", "Flash 02 (1987).cbz", "Flash Omnigold 03.cbz"])
        assert [f.nombre for f in q.filas if f.incluido] == ["Flash 01 (1987).cbz"] and q.token is not None


# ── 7 y 8. Marcado / marcable / incluido y subconjunto ──────────────────────────────────────────

class TestCriterio7y8Seleccion:

    async def _lote_mixto(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz", "Sin numero.cbz")
        p = await abrir(serie)
        return await p.reenviar(marcar=["Flash 01 (1987).cbz", "Flash 02 (1987).cbz", "Sin numero.cbz"])

    async def test_un_marcado_bloqueado_sigue_marcado_y_dice_por_que(self, entorno):
        q = await self._lote_mixto(entorno)
        f = q.fila("Sin numero.cbz")
        assert f.marcado and not f.marcable and not f.incluido                  # solicitado, bloqueado, fuera del token
        assert "checked" in f.cuerpo and "Marcado, pero bloqueado" in q.visible
        assert q.total("marcados") == 3 and q.total("a_vincular") == 2 and q.total("marcados_bloqueados") == 1

    async def test_el_token_representa_solo_el_subconjunto_y_se_listan_los_excluidos_con_su_motivo(self, entorno):
        q = await self._lote_mixto(entorno)
        assert q.token is not None
        assert "Lote preparado: 2 archivos de esta página" in q.visible
        assert "Marcados pero fuera del lote" in q.visible and "Sin numero.cbz — Falta el número" in q.visible
        from zascarr.services.tokens_revision import verificar_token_vinculacion
        firmado = verificar_token_vinculacion(q.token, SECRETO)
        assert sorted(a.id for a in firmado.archivos) == sorted(f.id for f in q.filas if f.incluido) and len(firmado.archivos) == 2

    async def test_si_ninguno_se_puede_incluir_no_hay_token_y_se_explica(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Sin numero.cbz")
        p = await abrir(serie)
        q = await p.reenviar(marcar=["Sin numero.cbz"])
        assert q.token is None and "Ninguno de los archivos marcados se puede vincular" in q.visible
        assert "Lote preparado" not in q.visible


# ── 9. Renovación ───────────────────────────────────────────────────────────────────────────────

class TestCriterio9Renovacion:

    async def test_cada_cambio_pide_una_vista_nueva_y_la_anterior_no_se_reutiliza(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        p = await abrir(serie)
        a = await p.reenviar(marcar=["Flash 01 (1987).cbz"])
        b = await a.reenviar(marcar=["Flash 02 (1987).cbz"])
        c = await b.reenviar(numeros={"Flash 02 (1987).cbz": "8"})
        assert len({a.token, b.token, c.token}) == 3 and None not in (a.token, b.token, c.token)
        assert c.fila("Flash 02 (1987).cbz").numero == "8" and c.total("a_vincular") == 2

    async def test_el_formulario_se_renueva_con_cualquier_cambio_y_con_los_botones_de_pagina(self, entorno):
        """Regresión (encontrada en navegador real): sin `submit` en `hx-trigger`, los botones «Página siguiente» y
        «Volver a esa página» hacían un envío NATIVO (GET con todos los campos en la URL) en lugar de renovar."""
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        t = (await abrir(serie)).t
        assert 'hx-trigger="change, submit"' in t and 'method="post"' in t

    async def test_sin_htmx_el_envio_devuelve_la_pagina_entera(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        r = await enviar((await abrir(serie)).formulario(marcar=["Flash 01 (1987).cbz"]), htmx=False)
        assert "<html" in r.text and Pagina(r.text).fila("Flash 01 (1987).cbz").incluido
        r2 = await enviar((await abrir(serie)).formulario(), htmx=True)
        assert "<html" not in r2.text

    async def test_la_pagina_marca_la_revision_como_pendiente_mientras_se_renueva(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        t = (await abrir(serie)).t
        assert 'hx-post="/ui/pendientes/carpetas/asistente/vinculacion/revisar"' in t
        assert "classList.add('pendiente')" in t and "Revisión pendiente" in t
        assert "hx-sync" in t                                                    # una renovación sustituye a la anterior

    async def test_si_la_renovacion_falla_se_muestra_el_fallo_y_no_queda_token(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        p = await abrir(serie)
        a = await p.reenviar(marcar=["Flash 01 (1987).cbz"])
        assert a.token is not None
        async with entorno.banco.fabrica() as s:                                # la serie desaparece entre una petición y otra
            await s.execute(text("DELETE FROM series"))
            await s.commit()
        r = await enviar(a.formulario())
        q = Pagina(r.text)
        assert r.status_code == 200 and q.token is None and q.filas == []
        assert "ya no existe en tu biblioteca" in q.visible


# ── 10. Sin efectos ─────────────────────────────────────────────────────────────────────────────

class TestCriterio10SinEfectos:

    async def test_abrir_editar_paginar_y_renovar_no_cambian_la_base_ni_los_archivos(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(1, LIMITE_ARCHIVOS + 3)))
        antes = (await estado_de_la_base(entorno.banco), huella_disco(entorno.lib))
        n = len(entorno.banco.sentencias)
        p = await abrir(serie)
        p = await p.reenviar(marcar=["Flash 001 (1987).cbz"], numeros={"Flash 002 (1987).cbz": "9"})
        p = await p.reenviar(ir_a=p.siguiente())
        p = await p.reenviar(ir_a=INICIO)
        assert p.token is not None
        escrituras = [q for q in entorno.banco.sentencias[n:] if re.match(r"\s*(INSERT|UPDATE|DELETE)\b", q, re.I)]
        assert escrituras == []
        assert (await estado_de_la_base(entorno.banco), huella_disco(entorno.lib)) == antes


# ── 11. Borrador ────────────────────────────────────────────────────────────────────────────────

class TestCriterio11Borrador:

    async def _dos_paginas(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(1, LIMITE_ARCHIVOS + 4)))
        return await abrir(serie)

    async def test_al_volver_a_la_pagina_se_recuperan_marcas_y_numeros_y_se_revisa_de_nuevo(self, entorno):
        p = await self._dos_paginas(entorno)
        p = await p.reenviar(marcar=["Flash 001 (1987).cbz", "Flash 002 (1987).cbz"],
                             numeros={"Flash 002 (1987).cbz": "42"})
        token_original = p.token
        segunda = await p.reenviar(ir_a=p.siguiente())
        assert segunda.token is None and not any(f.marcado for f in segunda.filas)
        assert "Archivos 1–100: 2 marcados, 1 número escrito" in segunda.visible
        de_vuelta = await segunda.reenviar(ir_a=INICIO)
        assert de_vuelta.fila("Flash 001 (1987).cbz").marcado and de_vuelta.fila("Flash 002 (1987).cbz").marcado
        f = de_vuelta.fila("Flash 002 (1987).cbz")
        assert (f.numero, f.origen) == ("42", "persona")
        assert de_vuelta.token is not None and de_vuelta.token != token_original      # revisión NUEVA, no la guardada
        assert "Trabajo guardado en otras páginas" not in de_vuelta.visible

    async def test_el_borrador_de_otra_pagina_no_entra_en_el_token_de_la_actual(self, entorno):
        p = await self._dos_paginas(entorno)
        p = await p.reenviar(marcar=["Flash 001 (1987).cbz"])
        segunda = await p.reenviar(ir_a=p.siguiente())
        segunda = await segunda.reenviar(marcar=["Flash 101 (1987).cbz"])
        from zascarr.services.tokens_revision import verificar_token_vinculacion
        firmado = verificar_token_vinculacion(segunda.token, SECRETO)
        assert [a.id for a in firmado.archivos] == [segunda.fila("Flash 101 (1987).cbz").id]

    async def test_un_borrador_que_ya_no_encaja_se_dice_y_no_se_presenta_como_valido(self, entorno):
        p = await self._dos_paginas(entorno)
        segunda = await p.reenviar(ir_a=p.siguiente())                  # se está en la 2.ª; la 1.ª tiene un borrador
        campos = [(k, v) for k, v in segunda.formulario() if k != "borradores"]
        borradores = {"": {"marcados": [str(uuid4())], "numeros": {}, "desde": 1, "hasta": 100}}   # un archivo ajeno
        campos += [("borradores", json.dumps(borradores)), ("ir_a", INICIO)]
        r = await enviar(campos)
        q = Pagina(r.text)
        assert r.status_code == 200 and q.token is None and not any(f.marcado for f in q.filas)
        assert len(q.filas) == LIMITE_ARCHIVOS                         # la página limpia, sin el borrador
        assert "No se ha podido reconstruir" in q.visible and "no cuenta como una revisión válida" in q.visible

    @pytest.mark.parametrize("basura", ["{no es json", "[1,2,3]", json.dumps({"x": "y"}),
                                        json.dumps({"inicio": {"marcados": ["no-uuid"], "numeros": {}}})])
    async def test_un_campo_de_borradores_manipulado_se_ignora_sin_romper_la_pagina(self, entorno, basura):
        p = await self._dos_paginas(entorno)
        campos = [(k, v) for k, v in p.formulario() if k != "borradores"] + [("borradores", basura)]
        r = await enviar(campos)
        q = Pagina(r.text)
        assert r.status_code == 200 and len(q.filas) == LIMITE_ARCHIVOS and q.token is None

    async def test_los_nombres_se_escapan(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "<img src=x onerror=alert(1)> 01.cbz")
        t = (await abrir(serie)).t
        assert "<img src=x" not in t and "&lt;img" in t
