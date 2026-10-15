# ruff: noqa: E501, F401, F811
"""U20 (#207) — «Marcar de una vez todo lo vinculable y leer la revisión en mi idioma», sobre Postgres real.

Dos mecanismos de la revisión de #119/#120 que la historia cambia:

1. **Marcar / desmarcar todos** (criterios 1, 2 y 3): una carpeta como `Flash (1987)` tiene 155 archivos en páginas de
   20..100 y solo había una casilla por fila. La acción es una petición al servidor (`POST /revisar` con `accion`), sin
   JavaScript propio, que marca SOLO lo que el servicio da por marcable y devuelve el recuento.
2. **Sin jerga del contrato** (criterios 4, 5 y 6): «token», «lote» y «motivo: x» llegaban a la persona. El texto sale ahora de
   la capa web, por código, y una regresión falla si vuelve.

Los nombres de las pruebas dicen el mecanismo del fallo que evitan. Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import html
import os
import re
import time

import pytest

from tests.test_asistente_confirmar_pg import (  # noqa: F401  (ayudas compartidas)
    DOS,
    UNO,
    Resultado,
    confirmar,
    formulario_de_confirmacion,
    formulario_de_confirmacion_de_fallo,
    listo,
)
from tests.test_asistente_confirmar_pg import enviar as enviar_confirmacion
from tests.test_asistente_vinculacion_pg import (  # noqa: F401
    CLAVE,
    INICIO,
    LIMITE_ARCHIVOS,
    Pagina,
    _secreto_en_el_asistente,
    abrir,
    archivos,
    cliente,
    entorno,
    enviar,
    estado_de_la_base,
    huella_disco,
    serie_de_prueba,
    url_bd,
)
from tests.test_vinculacion_pg import ent, firmar  # noqa: F401

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)"),
]

#: Lo que la persona NO debe leer (criterio 4). `\bmotivo:` no coincide con «Otros motivos:».
JERGA = re.compile(r"\btoken\b|\blotes?\b|\bmotivo:", re.I)


def jerga_en(visible: str) -> list[str]:
    return [m.group(0) for m in JERGA.finditer(visible)]


async def accionar(p: Pagina, accion: str, *, htmx: bool = True, **kw) -> Pagina:
    """Lo que envía el navegador al pulsar «Marcar todos…» / «Desmarcar todos»: el formulario y el botón pulsado."""
    r = await enviar(p.formulario(**kw) + [("accion", accion)], htmx=htmx)
    assert r.status_code == 200, r.text
    return Pagina(r.text, p.clave)


def aviso_de_accion(p: Pagina) -> dict:
    m = re.search(r'<div class="vinc-accion-resultado"[^>]*data-accion="([^"]+)" data-n="(\d+)"(?: data-repetidos="(\d+)")?', p.t)
    assert m, "la respuesta no trae el recuento de la acción"
    return {"accion": m.group(1), "n": int(m.group(2)), "repetidos": int(m.group(3)) if m.group(3) else None}


def nombres_marcados(p: Pagina) -> list[str]:
    return sorted(f.nombre for f in p.filas if f.marcado)


# ── 1. Marcar todos los que se pueden vincular ──────────────────────────────────────────────────

class TestMarcarTodos:

    async def test_marca_solo_los_marcables_y_el_servidor_devuelve_el_recuento(self, entorno):
        """Mecanismo: marcar a ciegas todas las casillas bloquearía los que no tienen número."""
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz", "Flash 03 (1987).cbz", "Sin numero.cbz")
        p = await abrir(serie)
        assert not p.fila("Sin numero.cbz").marcable
        q = await accionar(p, "marcar_todos")
        assert nombres_marcados(q) == ["Flash 01 (1987).cbz", "Flash 02 (1987).cbz", "Flash 03 (1987).cbz"]
        assert not q.fila("Sin numero.cbz").marcado                  # el bloqueado NO se marca
        assert aviso_de_accion(q) == {"accion": "marcar_todos", "n": 3, "repetidos": 0}
        assert "Se marcaron 3 archivos que se pueden vincular" in q.visible
        assert q.total("a_vincular") == 3 and q.total("marcados_bloqueados") == 0 and q.token is not None

    async def test_no_marca_ni_toca_lo_de_otras_paginas_ni_sus_borradores(self, entorno):
        """Mecanismo: la acción actúa sobre la página que se ve; lo de las demás son borradores de la persona."""
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(1, LIMITE_ARCHIVOS + 6)))
        p1 = await abrir(serie)
        p2 = await p1.reenviar(ir_a=p1.siguiente())
        p2 = await p2.reenviar(marcar=["Flash 103 (1987).cbz"])       # un borrador en la segunda página
        vuelta = await p2.reenviar(ir_a=INICIO)
        marcada = await accionar(vuelta, "marcar_todos")
        assert len(marcada.filas) == LIMITE_ARCHIVOS and all(f.marcado for f in marcada.filas)
        assert aviso_de_accion(marcada)["n"] == LIMITE_ARCHIVOS
        segunda = await marcada.reenviar(ir_a=marcada.siguiente())
        assert nombres_marcados(segunda) == ["Flash 103 (1987).cbz"]  # solo su borrador; las otras 4 siguen sin marcar
        assert len(segunda.filas) == 5

    async def test_no_elige_entre_numeros_repetidos_y_los_deja_sin_marcar(self, entorno):
        """Mecanismo: dos marcados con el mismo número se bloquean ambos, y elegir uno sería decidir por la persona."""
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 03 (1987).cbz", "Flash 03 (copia).cbz", "Flash 04 (1987).cbz")
        p = await abrir(serie)
        q = await accionar(p, "marcar_todos")
        assert nombres_marcados(q) == ["Flash 04 (1987).cbz"]
        assert aviso_de_accion(q) == {"accion": "marcar_todos", "n": 1, "repetidos": 2}
        assert "2 archivos comparten el número con otro y no se marcó" in q.visible
        assert q.total("marcados_bloqueados") == 0                    # nada marcado quedó bloqueado
        # y la persona puede elegir uno: ese sí queda marcado y vinculable
        r = await q.reenviar(marcar=["Flash 03 (1987).cbz"])
        assert r.fila("Flash 03 (1987).cbz").incluido and not r.fila("Flash 03 (copia).cbz").marcado

    async def test_un_repetido_de_algo_ya_marcado_por_la_persona_no_se_marca(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 03 (1987).cbz", "Flash 03 (copia).cbz", "Flash 04 (1987).cbz")
        p = await abrir(serie)
        p = await p.reenviar(marcar=["Flash 03 (1987).cbz"])
        q = await accionar(p, "marcar_todos")
        assert nombres_marcados(q) == ["Flash 03 (1987).cbz", "Flash 04 (1987).cbz"]
        assert q.fila("Flash 03 (1987).cbz").incluido                 # lo que marcó la persona sigue vinculable

    async def test_sin_nada_marcable_lo_dice_y_no_inventa_un_recuento(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Sin numero.cbz")
        q = await accionar(await abrir(serie), "marcar_todos")
        assert nombres_marcados(q) == [] and q.token is None
        assert aviso_de_accion(q)["n"] == 0
        assert "No hay ningún archivo más que se pueda marcar en esta página" in q.visible

    async def test_respeta_el_numero_que_la_persona_acaba_de_escribir(self, entorno):
        """Mecanismo: «marcable» depende del número; se evalúa con lo que hay en el formulario, no con el del nombre."""
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Sin numero.cbz", "Flash 01 (1987).cbz")
        p = await abrir(serie)
        q = await accionar(p, "marcar_todos", numeros={"Sin numero.cbz": "7"})
        assert nombres_marcados(q) == ["Flash 01 (1987).cbz", "Sin numero.cbz"]
        assert q.fila("Sin numero.cbz").numero == "7" and q.fila("Sin numero.cbz").incluido

    async def test_una_marca_que_acaba_bloqueada_no_se_cuenta_ni_se_deja_caer_en_silencio(self, entorno, monkeypatch):
        """Mecanismo (benchmark U20, Kapowarr): su «seleccionar todo» incluye filas que luego se descartan sin decirlo.
        Aquí el recuento sale de la evaluación FINAL: si algo marcado ya no se puede vincular, se dice y no suma."""
        from zascarr.web import asistente_vinculacion as web
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz", "Sin numero.cbz")
        p = await abrir(serie)
        bloqueado = p.fila("Sin numero.cbz").id
        real = web.elegir_para_marcar_todos

        def con_deriva(r):                       # entre las dos evaluaciones, uno «cambia»: se marca un bloqueado
            elegidos, repetidos = real(r)
            return elegidos + [bloqueado], repetidos
        monkeypatch.setattr(web, "elegir_para_marcar_todos", con_deriva)
        q = await accionar(p, "marcar_todos")
        assert aviso_de_accion(q)["n"] == 1                          # solo el que de verdad se puede vincular
        assert "Se marcaron 1 archivo que se pueden vincular" in q.visible
        assert "1 archivo marcado cambió al revisarlos y ya no se pueden vincular" in q.visible
        assert q.fila("Sin numero.cbz").marcado and not q.fila("Sin numero.cbz").incluido

    async def test_sin_htmx_devuelve_la_pagina_entera(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        r = await enviar((await abrir(serie)).formulario() + [("accion", "marcar_todos")], htmx=False)
        assert "<html" in r.text and 'lang="es"' in r.text
        assert nombres_marcados(Pagina(r.text)) == ["Flash 01 (1987).cbz"]


# ── 2. Desmarcar todos ──────────────────────────────────────────────────────────────────────────

class TestDesmarcarTodos:

    async def test_quita_todas_las_marcas_de_la_pagina_y_conserva_los_numeros_escritos(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz", "Sin numero.cbz")
        p = await abrir(serie)
        p = await p.reenviar(marcar=["Flash 01 (1987).cbz", "Sin numero.cbz"], numeros={"Sin numero.cbz": "9"})
        assert len(nombres_marcados(p)) == 2
        q = await accionar(p, "desmarcar_todos")
        assert nombres_marcados(q) == [] and q.token is None
        assert aviso_de_accion(q) == {"accion": "desmarcar_todos", "n": 2, "repetidos": None}
        assert "Se quitaron las marcas de 2 archivos de esta página" in q.visible
        assert q.fila("Sin numero.cbz").numero == "9" and q.fila("Sin numero.cbz").origen == "persona"

    async def test_no_toca_los_borradores_de_otras_paginas(self, entorno):
        """Mecanismo: «desmarcar todos» de una página no puede vaciar lo que la persona dejó en otra."""
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(1, LIMITE_ARCHIVOS + 4)))
        p1 = await abrir(serie)
        p2 = await p1.reenviar(ir_a=p1.siguiente())
        p2 = await p2.reenviar(marcar=["Flash 102 (1987).cbz"])
        p1 = await p2.reenviar(ir_a=INICIO)
        p1 = await accionar(p1, "marcar_todos")
        p1 = await accionar(p1, "desmarcar_todos")
        assert nombres_marcados(p1) == []
        segunda = await p1.reenviar(ir_a=p1.siguiente())
        assert nombres_marcados(segunda) == ["Flash 102 (1987).cbz"]

    async def test_sin_marcas_dice_que_no_habia_nada_que_quitar(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        q = await accionar(await abrir(serie), "desmarcar_todos")
        assert aviso_de_accion(q)["n"] == 0 and "No había ningún archivo marcado" in q.visible


# ── 3. Sin efectos y sin JavaScript propio ──────────────────────────────────────────────────────

class TestSinEfectosYSinJs:

    async def test_marcar_y_desmarcar_no_escriben_en_la_base_ni_en_el_disco(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(1, 8)))
        antes = (await estado_de_la_base(entorno.banco), huella_disco(entorno.lib))
        n = len(entorno.banco.sentencias)
        p = await accionar(await abrir(serie), "marcar_todos")
        p = await accionar(p, "desmarcar_todos")
        escrituras = [q for q in entorno.banco.sentencias[n:] if re.match(r"\s*(INSERT|UPDATE|DELETE)\b", q, re.I)]
        assert escrituras == [] and (await estado_de_la_base(entorno.banco), huella_disco(entorno.lib)) == antes

    async def test_una_accion_desconocida_o_con_cambio_de_pagina_no_marca_nada(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(1, LIMITE_ARCHIVOS + 3)))
        p = await abrir(serie)
        desconocida = Pagina((await enviar(p.formulario() + [("accion", "borrar_todo")])).text)
        assert nombres_marcados(desconocida) == [] and "vinc-accion-resultado" not in desconocida.t
        con_pagina = Pagina((await enviar(p.formulario(ir_a=p.siguiente()) + [("accion", "marcar_todos")])).text)
        assert nombres_marcados(con_pagina) == [] and "vinc-accion-resultado" not in con_pagina.t

    async def test_los_botones_son_formulario_del_servidor_y_la_plantilla_no_trae_script_propio(self, entorno):
        """Criterio 3 / ADR 0005 decisión 3: peticiones HTMX, ningún `<script>` ni `onclick`."""
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        p = await abrir(serie)
        assert re.search(r'<button type="submit" name="accion" value="marcar_todos"[^>]*>Marcar todos los que se pueden vincular</button>', p.t)
        assert re.search(r'<button type="submit" name="accion" value="desmarcar_todos"[^>]*disabled[^>]*>Desmarcar todos</button>', p.t)
        cuerpo = re.search(r'<div id="revision".*?</form>', p.t, re.S).group(0)
        assert "<script" not in cuerpo and "onclick" not in cuerpo
        assert 'hx-post="/ui/pendientes/carpetas/asistente/vinculacion/revisar"' in cuerpo

    async def test_el_boton_de_marcar_se_desactiva_cuando_no_hay_nada_que_marcar(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        q = await accionar(await abrir(serie), "marcar_todos")
        assert re.search(r'value="marcar_todos"[^>]*disabled', q.t)
        assert not re.search(r'value="desmarcar_todos"[^>]*disabled', q.t)


# ── 4. Sin jerga del contrato: «token», «lote», «motivo: x» ─────────────────────────────────────

class TestSinJergaEnLaRevision:
    """Criterios 4 y 6: ninguna pantalla de la revisión dice «token», «lote» ni «motivo:»."""

    async def _estados(self, entorno) -> dict[str, Pagina]:
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(1, LIMITE_ARCHIVOS + 4)),
                       "Sin numero.cbz", "Flash 003 (copia).cbz")
        abierta = await abrir(serie)
        marcada = await accionar(abierta, "marcar_todos")
        con_token = await abierta.reenviar(marcar=["Flash 001 (1987).cbz", "Flash 002 (1987).cbz"])
        bloqueado = await abierta.reenviar(marcar=["Sin numero.cbz", "Flash 001 (1987).cbz"])
        segunda = await con_token.reenviar(ir_a=con_token.siguiente())
        return {"abierta": abierta, "marcada": marcada, "con_token": con_token, "con_bloqueado": bloqueado,
                "segunda_con_borradores": segunda,
                "desmarcada": await accionar(marcada, "desmarcar_todos")}

    async def test_ninguna_revision_enseña_token_lote_ni_motivo(self, entorno):
        estados = await self._estados(entorno)
        assert estados["con_token"].token is not None and "Listo para vincular" in estados["con_token"].visible
        assert "Trabajo guardado en otras páginas" in estados["segunda_con_borradores"].visible
        con_jerga = {k: jerga_en(p.visible) for k, p in estados.items() if jerga_en(p.visible)}
        assert not con_jerga, f"jerga del contrato en la revisión: {con_jerga}"

    async def test_los_otros_motivos_salen_en_palabras_nunca_como_codigo(self, entorno):
        """Mecanismo: «Otros motivos: requiere_numero» pintaba el código interno. Un archivo sin número y que ya no está
        en su ruta tiene dos impedimentos: el primero es el estado y el segundo sale en «Otros motivos»."""
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Sin numero.cbz", en_disco=False)
        p = await abrir(serie)
        fila = p.fila("Sin numero.cbz")
        assert fila.estado == "origen_no_encontrado"
        assert "Otros motivos: falta el número." in p.visible
        assert not re.search(r"\b[a-z]+_[a-z_]+\b", re.sub(r"<[^>]+>", " ", p.t.split('<ul class="vinculacion-lista">')[1]))

    async def test_las_explicaciones_de_pagina_y_borrador_caben_en_una_linea_y_el_detalle_va_plegado(self, entorno):
        """Criterio 5: la frase visible es corta; lo demás, dentro de un `<details>`."""
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, *(f"Flash {i:03d} (1987).cbz" for i in range(1, LIMITE_ARCHIVOS + 4)))
        p = await abrir(serie)
        segunda = await (await p.reenviar(marcar=["Flash 001 (1987).cbz"])).reenviar(ir_a=p.siguiente())
        for pagina in (p, segunda):
            fuera = re.sub(r"<details.*?</details>", "", pagina.t, flags=re.S)
            frases = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", x))).strip()
                      for x in re.findall(r'<p class="vinc-alcance">(.*?)</p>', fuera, re.S)]
            assert frases, "falta la frase de alcance"
            assert all(len(f) <= 75 for f in frases), frases
        assert re.search(r"<details class=\"vinc-detalle\"><summary>Más detalle de las páginas</summary>", p.t)
        assert re.search(r"<details class=\"vinc-detalle\"><summary>Más detalle de los borradores</summary>", segunda.t)
        assert "máximo 100 por página" in p.visible                  # el detalle sigue ahí, solo plegado


class TestSinJergaEnElResultado:
    """Criterios 4 y 6, en el resultado de la confirmación y en cada fallo."""

    async def test_el_resultado_completo_y_el_parcial_no_dicen_lote(self, ent):
        p = await listo(ent, UNO, DOS)
        completo = await confirmar(p)
        assert completo.estado == "vinculados_todos" and not jerga_en(completo.visible), jerga_en(completo.visible)
        assert "Hecho: todos los archivos quedaron vinculados" in completo.visible

    async def test_el_parcial_dice_cuantos_no_se_vincularon_sin_jerga(self, ent):
        from tests.test_vinculacion_pg import archivos as _  # noqa: F401
        serie = await serie_de_prueba(ent, "Flash", 1987)
        await archivos(ent, UNO, DOS)
        p = await (await abrir(serie)).reenviar(marcar=[UNO, DOS])
        (ent.lib / "Comics/Flash (1987)" / DOS).write_bytes(b"otro contenido" * 20)
        r = await confirmar(p)
        assert r.estado == "vinculados_parcialmente" and not jerga_en(r.visible), jerga_en(r.visible)
        assert "de los que preparaste no se vincularon" in r.visible

    @pytest.mark.parametrize("edad_h", [16 / 60, 25])
    async def test_el_token_caducado_dice_la_causa_y_la_accion_sin_decir_token(self, ent, edad_h):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO)
        token = await firmar(ent, serie, [(ids[UNO], "1")], ahora=time.time() - edad_h * 3600)
        r = Resultado((await enviar_confirmacion([("token", token)])).text)
        assert "La preparación caducó" in r.visible and "Vuelve a revisar los archivos" in r.visible
        assert not jerga_en(r.visible), r.visible

    async def test_un_token_que_no_es_valido_no_se_cita(self, ent):
        r = Resultado((await enviar_confirmacion([("token", "esto-no-es-un-token-firmado")])).text)
        assert "no es válida" in r.visible and "no se ha vinculado nada" in r.visible
        assert not jerga_en(r.visible), r.visible

    async def test_resultado_incierto_habla_en_llano(self, ent, monkeypatch):
        from sqlalchemy.ext.asyncio import AsyncSession
        p = await listo(ent, UNO)
        real = AsyncSession.commit

        async def commit_y_luego_falla(self):
            await real(self)
            raise ConnectionError("se perdió la conexión")
        monkeypatch.setattr(AsyncSession, "commit", commit_y_luego_falla)
        incierto = Resultado((await enviar_confirmacion(formulario_de_confirmacion(p.t))).text)
        monkeypatch.setattr(AsyncSession, "commit", real)
        assert "No se sabe si se llegó a vincular" in incierto.visible and not jerga_en(incierto.visible)
        assert "no lo des por hecho ni por fallido" in incierto.visible and "Comprobar el resultado" in incierto.visible

    async def test_serie_borrada_antes_de_confirmar_habla_en_llano(self, ent):
        from sqlalchemy import text
        p = await listo(ent, UNO)
        async with ent.banco.fabrica() as s:
            await s.execute(text("DELETE FROM series"))
            await s.commit()
        r = Resultado((await enviar_confirmacion(formulario_de_confirmacion(p.t))).text)
        assert "La serie ya no existe" in r.visible and "Hecho" not in r.visible and not jerga_en(r.visible)

    async def test_un_codigo_de_fallo_o_de_motivo_desconocido_sale_sin_su_identificador(self, ent, monkeypatch):
        """Mecanismo: «No se pudo vincular (motivo: x)» enseñaba el código del contrato."""
        from zascarr.web import asistente_vinculacion as web
        assert "motivo:" not in web.TEXTO_DE_MOTIVO_DESCONOCIDO.lower()
        assert "{" not in web.TEXTO_DE_MOTIVO_DESCONOCIDO and "{" not in web.MENSAJE_DE_FALLO_DESCONOCIDO
        for codigo, texto in web.MENSAJES_DE_FALLO.items():
            assert not jerga_en(texto), (codigo, texto)
        assert not jerga_en(web.MENSAJE_CADUCADO_SIN_INFORME)


class TestSinCodigosInternosDeFormato:

    def test_el_formato_se_dice_como_lo_dice_el_coleccionista(self):
        """Mecanismo: «ya existe como otra edición (single_issue)» enseñaba el valor interno del enum (capturado en el
        ensayo con la propia pantalla). Se traduce en la capa web; el texto del servicio no cambia."""
        from zascarr.models import IssueFormat
        from zascarr.web.asistente_vinculacion import FORMATOS_LEGIBLES, texto_legible
        assert set(FORMATOS_LEGIBLES) == {f.value for f in IssueFormat}, "falta o sobra un formato"
        assert texto_legible("El número 12 ya existe en la serie como otra edición (single_issue).") == (
            "El número 12 ya existe en la serie como otra edición (grapa).")
        assert texto_legible("Sin formatos aquí.") == "Sin formatos aquí." and texto_legible(None) == ""
        assert not any("_" in etiqueta for etiqueta in FORMATOS_LEGIBLES.values())

    async def test_la_pantalla_no_enseña_el_valor_interno_del_formato(self, entorno):
        from tests.test_asistente_vinculacion_pg import sembrar_issue
        from zascarr.models import IssueFormat
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 12 (1987).cbz")
        await sembrar_issue(entorno.banco, serie, "12", formato=IssueFormat.OMNIBUS)
        p = await abrir(serie)
        assert "ya existe en la serie como otra edición" in p.visible
        assert not re.search(r"\b(single_issue|trade_paperback|omnibus|graphic_novel|manga_tankobon)\b", p.visible)
