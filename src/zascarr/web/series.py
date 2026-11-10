# ruff: noqa: E501
"""
Ficha de serie (C2, ampliada en C1) — /ui/series/{id}.

C2 dejó solo números presentes/ausentes. C1 añade portada (cascada
unificada de 3 niveles, ver docstring de portada() abajo), editorial y
géneros, y un enlace de vuelta a /ui/biblioteca — sigue sin ser el
diseño final de una ficha de serie, solo deja de estar pelada.
"""
from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zascarr.api.series import huecos_de_serie, numeros_poseidos
from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.models import (
    File,
    Issue,
    MotivoRar,
    ReadingStatus,
    Series,
    Wishlist,
    WishlistOrigin,
    WishlistPolicy,
    WishlistStatus,
)
from zascarr.services.archivos_por_numero import archivos_por_numero
from zascarr.services.comic_vine import es_portada_de_relleno
from zascarr.services.comicinfo_ficha import MAX_TOKEN_COMICINFO, ComicInfoFichaService
from zascarr.services.conversion import ConversionDeArchivo
from zascarr.services.discrepancias import (
    clave_valida,
    mantener_lo_mio,
)
from zascarr.services.discrepancias import (
    entrada as entrada_discrepancia,
)
from zascarr.services.enricher import puede_enlazarse_con_comic_vine
from zascarr.services.enriquecimiento_plan import (
    EnriquecimientoPlanService,
    ErrorDePlan,
)
from zascarr.services.etiquetas import (
    EtiquetaInvalida,
    anadir_etiqueta,
    etiquetas_de_serie,
    quitar_etiqueta,
    sugerencias_etiqueta,
)
from zascarr.services.ficha_numero import (
    ROLES_ES,
    cargar_ficha_numero,
    cargar_ficha_serie,
    etiqueta_rol,
    partir_sinopsis,
)
from zascarr.services.ficha_numero import (
    TEXTOS as TEXTOS_FICHA,
)
from zascarr.services.lectura import (
    TEXTOS_LECTURA,
    EstadoInvalidoError,
    EstadoLectura,
    IssueNoEncontradoError,
    NotaInvalidaError,
    ValoracionInvalidaError,
    lectura_de,
    lecturas_de_serie,
    marcar,
)
from zascarr.services.legal import is_acknowledged
from zascarr.services.politica import (
    horas_minimas,
    pendientes_de_buscar,
    querer_de_serie,
    retirar_de_serie,
    texto_de_cota,
)
from zascarr.services.portada_numero import ANCHO_FICHA, ruta_previa
from zascarr.services.portada_serie import (
    MAX_CANDIDATAS,
    TIPO_ARCHIVO,
    TIPO_EXTERNA,
    archivo_de_portada,
    archivos_de_numero,
    candidatas_de_portada,
    eleccion_de_portada,
    guardar_eleccion,
    quitar_eleccion,
)
from zascarr.services.procedencia import NOMBRE_DE_FUENTE, procedencia_de_serie
from zascarr.services.relacion_confirmada import (
    es_protegida,
    estado_de_relacion,
    relacion_actual,
)
from zascarr.services.series import razon_de_no_calculable
from zascarr.services.tokens_revision import (
    MAX_TOKEN_CONVERSION,
    MAX_TOKEN_MANTENER,
    SIN_PROCEDENCIA,
    MantenerFirmada,
    crear_token_mantener,
    verificar_token_mantener,
)
from zascarr.services.vinculacion import (
    ConflictoDeBloqueoError,
    ResultadoInciertoError,
    TokenCaducadoError,
    TokenInvalidoError,
)
from zascarr.utils.cover import (
    CACHE_VERSION,
    CARPETA_EXTERNA,
    SERIES_COVER_MAX_WIDTH,
    cached_image_response,
    es_candidato_de_portada,
    extract_cover_thumbnail,
    fetch_and_cache_cover,
    mejorar_portada_externa,
    portada_previa_suficiente,
    write_cover_cache,
)
from zascarr.utils.lector_rar import ErrorRar
from zascarr.utils.lector_rar import disponible as lector_rar_disponible
from zascarr.utils.portada_rar import (
    MOTIVOS_DEL_ARCHIVO,
    es_rar_candidato,
    escribir_marca,
    marca_vigente,
    portada_de_rar,
)
from zascarr.web.asistente_vinculacion import FORMATOS_LEGIBLES
from zascarr.web.retorno import volver_segura
from zascarr.web.routes import crear_templates

logger = structlog.get_logger()

#: #419: cuántos archivos «plausibles» (los que `es_candidato_de_portada` acepta) se abren como
#: máximo en una petición fría de portada. Los descartados no se abren ni gastan intento. El
#: fallo no se cachea, así que 3 acota el peor caso (tres aperturas por petición) sin recorrer
#: una serie de cientos de archivos.
MAX_INTENTOS_PORTADA = 3

#: #419: cuántos archivos se EVALÚAN como máximo por petición, los que se descartan por firma o por
#: formato conocido incluidos (leer la firma cuesta disco, y el fallo no se recuerda). Provisional (PO,
#: 2026-11-06). Una serie con más de 50 archivos y el primer legible más allá del 50º no obtiene esa
#: portada hasta que se rellene `formato_contenido` (y el orden los acerque).
MAX_EVALUADOS_PORTADA = 50

#: #418 (FR-17): tiempo total que una petición fría puede gastar abriendo candidatos. Agotado, no se
#: abren más (los siguientes se intentan en las peticiones que vengan: los fallidos quedan marcados).
PRESUPUESTO_PORTADA_S = 20.0

#: #418 (FR-18): generaciones de portada en curso, por serie. Una segunda petición de la misma serie
#: (la ficha y la rejilla se solapan) espera a la primera en vez de abrir otra vez los archivos.
_GENERANDO: dict[UUID, asyncio.Future] = {}
templates = crear_templates()

router = APIRouter(prefix="/ui/series", tags=["ui"])

# U21 (#296): lo que lee la persona junto a la opción «Números que aún no han salido». Texto
# PROPIO de la interfaz, en español llano y sin el valor interno `futuros`;
# `services/politica.py::MOTIVO_POLITICA_FUTUROS` es el motivo técnico del orquestador y de sus
# pruebas, y no se toca.
MOTIVO_FUTUROS_EN_PANTALLA = (
    "las fuentes de datos no avisan de los números antes de que salgan"
)

# D8: lo que el selector OFRECE. `todos` no aparece (reservado hasta que D3 le
# dé significado, ver ficha) y `futuros` se pinta deshabilitado con su motivo —
# una opción que parece funcionar y no hace nada es peor que no ofrecerla.
_POLITICAS_OFRECIDAS = {
    WishlistPolicy.NONE: "No buscar nada por mi cuenta",
    WishlistPolicy.MISSING: "Completar la serie: buscar lo que me falta",
}


#: BL-R1b: por qué un archivo no ofrece «Deshacer esta vinculación», junto al archivo. Desde la
#: revisión de D9 (2026-10-23) solo queda `en_curso`: se desvincula cualquier archivo.
RAZONES_SIN_BOTON = {
    "en_curso": "Ahora mismo ZascArr trabaja con este archivo. Prueba de nuevo en unos minutos.",
}


async def _cuantos_retirados(db: AsyncSession, series: Series) -> int:
    """D8: los items retirados se ocultan del listado de deseos, así que la
    ficha de serie tiene que decir cuántos hay — si no, desaparecen sin rastro."""
    return (await db.execute(
        select(func.count())
        .select_from(Wishlist)
        .where(Wishlist.series_id == series.id)
        .where(Wishlist.origen == WishlistOrigin.POLICY)
        .where(Wishlist.status == WishlistStatus.RETIRADO)
    )).scalar() or 0


def _stmt_archivos_de_portada(series_id: UUID):
    """Archivos candidatos a portada de una serie: no ausentes, por `sort_order` ascendente con los sin
    número al final y `File.id` como desempate, para que dos peticiones frías elijan el mismo archivo."""
    return (
        select(File.id, File.file_path, File.metadata_["formato_contenido"])
        .join(Issue, File.issue_id == Issue.id)
        .where(Issue.series_id == series_id)
        .where(File.is_missing.is_(False))
        .order_by(Issue.sort_order.asc().nulls_last(), File.id.asc())
        .limit(MAX_EVALUADOS_PORTADA)
    )


def _primera_portada(archivos: list[tuple[UUID, str, dict | None]], covers: Path,
                     *, presupuesto_s: float = PRESUPUESTO_PORTADA_S,
                     estado: dict | None = None) -> tuple[bytes, str] | None:
    """Portada del primer archivo de `archivos` (ya ordenados y acotados) que la dé; todo en un solo
    hilo. Solo gasta intento el que se llega a abrir (ZIP por firma o formato guardado; RAR por
    firma); un fallo se registra sin ruta ni nombre de archivo (CLAUDE.md §5.4).

    #418: un RAR se lee con `utils/portada_rar`. Un RAR cuya portada ya falló y no ha cambiado (marca
    vigente en `covers/<CACHE_VERSION>/fallos`) se salta SIN abrirlo y sin gastar intento; un fallo del archivo deja
    marca, uno del entorno (herramienta ausente, error inesperado) no. Los ZIP se reintentan siempre.

    Si el lector está ocupado (otra generación tiene el turno) no se gasta intento ni se marca nada, se
    dejan de abrir RAR en esta petición (los ZIP siguientes sí se evalúan) y `estado["ocupado"]` lo dice
    (dictamen SecOps M-2 y N-2)."""
    marcas = covers / CACHE_VERSION
    intentos = 0
    limite = time.monotonic() + presupuesto_s
    # Con el interruptor apagado (`LECTOR_RAR_ENABLED=false`) ningún RAR se envía a `unar`: no es candidato,
    # no gasta intento y no deja marca; la herramienta ni se busca. Si no, se comprueba una sola vez y solo
    # si aparece un RAR.
    herramienta = None if get_settings().lector_rar_enabled else False
    rar_ocupado = False         # tras un turno vencido no se abren más RAR en esta petición, pero sí los ZIP
    for file_id, ruta, formato in archivos:
        path = Path(ruta)
        es_rar = es_rar_candidato(path, formato)
        if not es_rar and not es_candidato_de_portada(path, formato):
            continue
        if es_rar:
            if herramienta is None:
                herramienta = lector_rar_disponible()
            if rar_ocupado or not herramienta or marca_vigente(marcas, file_id, path):
                continue
        if intentos >= MAX_INTENTOS_PORTADA:
            break
        if time.monotonic() >= limite:
            logger.info("cover.presupuesto_agotado", intento=intentos)
            break
        intentos += 1
        if not es_rar:
            result = extract_cover_thumbnail(path, formato, ancho=SERIES_COVER_MAX_WIDTH)
            if result:
                if estado is not None:
                    # BL-INF6: la elección guarda QUÉ archivo dio la portada, no solo el número.
                    estado["file_id"] = file_id
                return result
            logger.info("cover.candidato_sin_portada", intento=intentos)
            continue
        try:
            resultado = portada_de_rar(path, covers, ancho=SERIES_COVER_MAX_WIDTH)
            if estado is not None:
                estado["file_id"] = file_id
            return resultado
        except ErrorRar as exc:
            if exc.motivo is MotivoRar.OCUPADO:
                # sin turno: este RAR no gastó intento y los siguientes se saltan en esta petición; los ZIP
                # que vengan después sí se evalúan (no necesitan el lector). Nada que recordar.
                logger.info("cover.lector_ocupado", intento=intentos)
                intentos -= 1
                rar_ocupado = True
                if estado is not None:
                    estado["ocupado"] = True
                continue
            logger.info("cover.candidato_sin_portada", intento=intentos, motivo=exc.motivo.value)
            if exc.motivo in MOTIVOS_DEL_ARCHIVO:
                escribir_marca(marcas, file_id, path, exc.motivo)
        except Exception as exc:      # error de entorno inesperado: se reintentará, sin marca
            logger.warning("cover.candidato_sin_portada", intento=intentos,
                           motivo=MotivoRar.INESPERADO.value, tipo=type(exc).__name__)
    return None


#: Resultado de una generación que no pudo ni intentarse porque el lector tenía otro turno: la ausencia es
#: pasajera (la respuesta no se cachea) y no hay nada que recordar.
LECTOR_OCUPADO = "ocupado"


def _generar_portada(archivos: list[tuple[UUID, str, dict | None]], covers: Path,
                     destino: Path) -> tuple[bytes, str, bool, bool] | str | None:
    """Saca la portada de los archivos y la escribe en `destino` (`v3`). `(bytes, tipo, escrita, efimera)`:
    si la caché no se puede escribir, `escrita` es `False` y se sirve igualmente lo extraído. `None`:
    no hay; `LECTOR_OCUPADO`: no la hay *ahora* por falta de turno del lector.

    H-1 (SecOps y QA): si se saltó un RAR candidato por falta de turno y aun así sale la portada de un
    archivo POSTERIOR, esa portada es **efímera**: se sirve pero NO se escribe en `v3` (ni se cachea en el
    navegador), para que la siguiente petición, con el lector libre, pruebe el RAR y guarde la correcta."""
    estado: dict = {}
    result = _primera_portada(archivos, covers, estado=estado)
    if result is None:
        return LECTOR_OCUPADO if estado.get("ocupado") else None
    data, content_type = result
    if estado.get("ocupado"):
        logger.info("cover.portada_efimera_por_lector_ocupado")
        return data, content_type, False, True
    try:
        write_cover_cache(destino, data)
    except OSError as exc:
        # FR-11 (#300): disco lleno, permiso denegado… El nombre del evento se conserva
        # (`cover.cache_sin_espacio`) porque hay alertas montadas sobre él.
        logger.warning("cover.cache_sin_espacio", motivo=type(exc).__name__,
                       errno=getattr(exc, "errno", None))
        return data, content_type, False, False
    return data, content_type, True, False


async def _portada_de_archivos(series_id: UUID, archivos: list[tuple[UUID, str, dict | None]],
                               covers: Path, destino: Path) -> tuple[bytes, str, bool, bool] | str | None:
    """Una sola generación por serie a la vez (FR-18): quien llega con otra en curso espera su
    resultado. Los fallos de la primera no se propagan a las que esperan (la siguiente petición
    reintenta)."""
    en_curso = _GENERANDO.get(series_id)
    if en_curso is not None:
        return await asyncio.shield(en_curso)
    futuro = asyncio.get_running_loop().create_future()
    _GENERANDO[series_id] = futuro
    try:
        resultado = await asyncio.to_thread(_generar_portada, archivos, covers, destino)
        futuro.set_result(resultado)
        return resultado
    finally:
        if not futuro.done():
            futuro.set_result(None)
        _GENERANDO.pop(series_id, None)


async def _veredicto(db: AsyncSession, series: Series, querer, politica: WishlistPolicy,
                     aviso_pendiente: bool) -> dict:
    """Qué dice el veredicto de la política (C6, FR-09/27/28/29). Precedencia con la política ACTIVA, donde cada nivel
    anula los siguientes: aviso legal pendiente > R = 0 > serie no calculable > cota de tiempo."""
    k = len(querer.numeros)
    r = get_settings().politica_busquedas_por_hora
    if politica == WishlistPolicy.NONE:
        return {"tipo": "ninguno", "no_calculable": razon_de_no_calculable(series) is not None}
    if k >= 1 and aviso_pendiente:
        return {"tipo": "aviso_legal", "k": k}
    if k >= 1 and r == 0:
        return {"tipo": "r_cero", "k": k}
    if querer.motivo:
        # Efecto diferido (FR-13): el enriquecedor podría enlazar la serie con Comic Vine y darle total. Solo si hay
        # búsquedas posibles (R > 0 y aviso aceptado); en condicional y sin nombrar la fuente.
        diferido = (not querer.computable and r > 0 and not aviso_pendiente
                    and politica in (WishlistPolicy.MISSING, WishlistPolicy.ALL)
                    and puede_enlazarse_con_comic_vine(series, get_settings().comicvine_enabled))
        return {"tipo": "motivo", "fuente": querer.fuente if not querer.computable else None,
                "diferido": diferido}
    if k >= 1:
        n = await pendientes_de_buscar(db, series, querer)
        if n >= 1:
            return {"tipo": "cota", "k": k, "r": r, "n": n, "cota": texto_de_cota(horas_minimas(n, r))}
        return {"tipo": "faltan", "k": k}
    return {"tipo": "completa"}


async def _contexto_politica(db: AsyncSession, series: Series,
                             querer=None, retirados_ahora: int | None = None,
                             aviso_legal_pendiente: bool | None = None) -> dict:
    """Lo que la ficha de serie enseña sobre D8.

    Usa el MISMO predicado que genera (`services/politica.querer_de_serie`) — si
    la página recalculara por su cuenta, podría decir una cosa y hacerse otra —
    y `lote` para no prometer más búsquedas de las que caben en un ciclo.

    `retirados` es SIEMPRE el total de la serie (no lo que retiró este
    guardado): lo que acaba de retirarse va aparte, en `retirados_ahora`, para
    que la confirmación no se confunda con el acumulado.

    `aviso_legal_pendiente`: si el manejador ya consultó el acuse (puerta legal), se reutiliza;
    `None` = consultarlo aquí.
    """
    if querer is None:
        querer = await querer_de_serie(db, series)
    pendiente_de_aviso = (
        not await is_acknowledged(db) if aviso_legal_pendiente is None else aviso_legal_pendiente)
    politica_actual = series.wishlist_policy or WishlistPolicy.NONE
    return {
        "veredicto": await _veredicto(db, series, querer, politica_actual, pendiente_de_aviso),
        "querer": querer,
        "politica_actual": politica_actual,
        "politicas_ofrecidas": _POLITICAS_OFRECIDAS,
        "motivo_futuros": MOTIVO_FUTUROS_EN_PANTALLA,
        "lote": get_settings().orchestrator_politica_lote,
        # D8 + blindaje legal: el ciclo no genera ni busca sin acuse, así que
        # prometer búsquedas sin decirlo sería engañar.
        "aviso_legal_pendiente": pendiente_de_aviso,
        "retirados": await _cuantos_retirados(db, series),
        "retirados_ahora": retirados_ahora,
    }


@router.get("/{series_id}", response_class=HTMLResponse)
async def detalle(series_id: UUID, request: Request, volver: str = Query(default=""),
                  db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    series = (await db.execute(
        select(Series)
        .options(selectinload(Series.publisher), selectinload(Series.genres))
        .where(Series.id == series_id)
    )).scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Serie no encontrada")

    poseidos = await numeros_poseidos(db, series.id)
    huecos = await huecos_de_serie(db, series, poseidos)

    politica = await _contexto_politica(db, series)
    archivos = await archivos_por_numero(db, series.id)
    # Las consultas de la ficha van AL FINAL: no desplazan las colas de los dobles de prueba
    # que ya consumían las consultas históricas de esta ruta.
    ficha = await cargar_ficha_serie(db, series_id)
    lecturas = await lecturas_de_serie(db, series_id)
    sinopsis_visible, sinopsis_resto = partir_sinopsis(ficha.sinopsis) if ficha else ("", "")
    serie_vacia = bool(ficha) and not (ficha.sinopsis or series.publisher or series.start_year
                                       or series.end_year or ficha.autores)
    respuesta = templates.TemplateResponse(request, "series_detail.html", {
        "series": series, "present": sorted(poseidos),
        "ficha": ficha, "textos_ficha": TEXTOS_FICHA, "roles_ficha": ROLES_ES,
        "lecturas": lecturas,
        "sinopsis_visible": sinopsis_visible, "sinopsis_resto": sinopsis_resto,
        "serie_vacia": serie_vacia,
        "missing": huecos.faltantes, "huecos": huecos,
        **politica,
        # BL-R1b: los archivos de cada número (consulta fija, no una por archivo).
        "archivos_por_numero": archivos,
        "formatos_legibles": FORMATOS_LEGIBLES,
        "procedencia": procedencia_de_serie(series),
        "volver": volver_segura(volver, series_id),
        "razones_sin_boton": RAZONES_SIN_BOTON,
        # BL-INF6: separador de caché del navegador de la portada; cambia al elegir otra.
        "portada_version": await _version_de_portada(db, series),
    })
    # #233/BL-R4: el aviso de una propuesta sin aplicar y sus acciones no se sirven de caché.
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


# ── BL-R4 (#233): «Mantener lo mío» sobre una discrepancia concreta ───────────────────────────────

_FALLOS_MANTENER: dict[str, str] = {
    "token_invalido": "Esa confirmación no es válida. No se ha cambiado nada: vuelve a abrirla desde la serie.",
    "token_caducado": "Esa confirmación ha caducado. No se ha cambiado nada: vuelve a abrirla desde la serie.",
    "resultado_incierto": "No sabemos si se llegó a guardar. Repite la operación: es segura y no duplica.",
    "conflicto_de_bloqueo": "Ahora mismo ZascArr está trabajando con este archivo. No se ha cambiado nada: vuelve a intentarlo.",
    "error_inesperado": "No se ha podido completar. No se ha cambiado nada.",
}


async def _archivo_e_issue(db: AsyncSession, series_id: UUID, file_id: UUID):
    """El archivo, su número y la relación D3 ACTUAL. Solo lectura."""
    f = (await db.execute(select(
        File.id, File.file_name, File.file_format, File.issue_id, File.metadata_source, File.metadata_,
    ).where(File.id == file_id))).first()
    if f is None:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    issue = None
    if f.issue_id is not None:
        issue = (await db.execute(select(Issue.series_id, Issue.issue_number, Issue.format)
                                  .where(Issue.id == f.issue_id))).first()
    if issue is None or str(issue.series_id) != str(series_id):
        raise HTTPException(status_code=404, detail="Ese archivo no pertenece a esta serie")
    archivo = SimpleNamespace(issue_id=f.issue_id, metadata_source=f.metadata_source, metadata_=f.metadata_)
    issue_obj = SimpleNamespace(series_id=issue.series_id, issue_number=issue.issue_number, format=issue.format)
    return f, issue, archivo, issue_obj


async def _discrepancia_pendiente(db: AsyncSession, series_id: UUID, file_id: UUID, clave: str):
    """La entrada de D4 que se puede mantener: clave válida, existe, está pendiente y es de la relación actual."""
    if not clave_valida(clave):
        raise HTTPException(status_code=404, detail="Propuesta no encontrada")
    f, issue, archivo, issue_obj = await _archivo_e_issue(db, series_id, file_id)
    if not es_protegida(estado_de_relacion(archivo, issue_obj)):
        raise HTTPException(status_code=404, detail="Ese archivo no tiene una relación protegida")
    relacion = relacion_actual(archivo, issue_obj)
    d = entrada_discrepancia(f.metadata_, clave)
    if d is None or d.get("estado") != "pendiente" or d.get("relacion") != relacion:
        raise HTTPException(status_code=404, detail="Esa propuesta ya no está pendiente en esta ficha")
    return f, issue, d, relacion


def _mantener_no_store(resp: HTMLResponse) -> HTMLResponse:
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.get("/{series_id}/archivos/{file_id}/discrepancias/{clave}/mantener", response_class=HTMLResponse)
async def mantener_discrepancia(
    series_id: UUID, file_id: UUID, clave: str, request: Request,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Confirmación explícita de «Mantener lo mío»: qué se mantiene y el token firmado; no escribe."""
    series = await _serie_o_404(db, series_id)
    f, issue, d, relacion = await _discrepancia_pendiente(db, series_id, file_id, clave)
    secreto = get_settings().secret_key
    if not secreto:
        raise HTTPException(status_code=503, detail="ZascArr no tiene clave para firmar; reinícialo.")
    token = crear_token_mantener(MantenerFirmada(
        file_id=str(f.id), clave=clave, issue_id=relacion["issue_id"], serie_id=relacion["serie_id"],
        vinculo_operacion=relacion["operacion_id"] or SIN_PROCEDENCIA, operacion=str(uuid4()),
    ), secreto)
    return _mantener_no_store(templates.TemplateResponse(request, "mantener_discrepancia.html", {
        "serie": series, "archivo": f, "issue": issue, "discrepancia": d, "fase": "vista_previa",
        "formatos_legibles": FORMATOS_LEGIBLES, "token": token, "r": None, "fallo": None,
    }))


@router.post("/{series_id}/archivos/{file_id}/discrepancias/{clave}/mantener", response_class=HTMLResponse)
async def confirmar_mantener_discrepancia(
    series_id: UUID, file_id: UUID, clave: str, request: Request,
    token: str = Form(..., min_length=1, max_length=MAX_TOKEN_MANTENER),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Ejecuta «Mantener lo mío» con SU token. No cambia la publicación ni toca archivos."""
    series = await _serie_o_404(db, series_id)
    base = {"serie": series, "archivo": None, "discrepancia": None, "fase": "resultado",
            "token": token, "r": None, "fallo": None}
    secreto = get_settings().secret_key
    firmado = verificar_token_mantener(token, secreto, ignorar_caducidad=True) if secreto else None
    if (firmado is None or firmado.file_id != str(file_id) or firmado.serie_id != str(series_id)
            or firmado.clave != clave):
        return _mantener_no_store(templates.TemplateResponse(request, "mantener_discrepancia.html", {
            **base, "fallo": _FALLOS_MANTENER["token_invalido"]}))
    try:
        r = await mantener_lo_mio(db, token, secret=secreto)
    except TokenInvalidoError:
        return _mantener_no_store(templates.TemplateResponse(request, "mantener_discrepancia.html",
                                                             {**base, "fallo": _FALLOS_MANTENER["token_invalido"]}))
    except TokenCaducadoError:
        return _mantener_no_store(templates.TemplateResponse(request, "mantener_discrepancia.html",
                                                             {**base, "fallo": _FALLOS_MANTENER["token_caducado"]}))
    except ResultadoInciertoError:
        return _mantener_no_store(templates.TemplateResponse(request, "mantener_discrepancia.html",
                                                             {**base, "fallo": _FALLOS_MANTENER["resultado_incierto"], "token": token}))
    except ConflictoDeBloqueoError:
        return _mantener_no_store(templates.TemplateResponse(request, "mantener_discrepancia.html",
                                                             {**base, "fallo": _FALLOS_MANTENER["conflicto_de_bloqueo"]}))
    return _mantener_no_store(templates.TemplateResponse(request, "mantener_discrepancia.html", {**base, "r": r}))


async def _serie_o_404(db: AsyncSession, series_id: UUID) -> Series:
    series = await db.get(Series, series_id)
    if series is None:
        raise HTTPException(status_code=404, detail="Serie no encontrada")
    return series


@router.post("/{series_id}/enriquecimiento/previsualizar", response_class=HTMLResponse)
async def previsualizar_enriquecimiento(
    series_id: UUID, request: Request, db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """#128: construye y firma un plan por campo; no escribe ni aplica nada."""
    series = await _serie_o_404(db, series_id)
    servicio = EnriquecimientoPlanService(db, get_settings().secret_key)
    try:
        plan = await servicio.previsualizar(series_id)
    except ErrorDePlan as exc:
        return templates.TemplateResponse(
            request, "enriquecimiento_previa.html",
            {"series": series, "plan": None, "error": str(exc)},
        )
    return templates.TemplateResponse(
        request, "enriquecimiento_previa.html",
        {"series": series, "plan": plan, "error": None},
    )


@router.post("/{series_id}/enriquecimiento/aplicar", response_class=HTMLResponse)
async def aplicar_enriquecimiento(
    series_id: UUID, request: Request, token: str = Form(...),
    campos: list[str] | None = Form(None), db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """#128: aplica el MISMO plan firmado y solo los campos seleccionados."""
    series = await _serie_o_404(db, series_id)
    servicio = EnriquecimientoPlanService(db, get_settings().secret_key)
    try:
        resultado = await servicio.aplicar(token, campos or [], series_id)
    except ErrorDePlan as exc:
        return templates.TemplateResponse(
            request, "enriquecimiento_resultado.html",
            {"series": series, "resultado": None, "error": str(exc)},
        )
    return templates.TemplateResponse(
        request, "enriquecimiento_resultado.html",
        {"series": series, "resultado": resultado, "error": None},
    )


@router.get("/{series_id}/etiquetas", response_class=HTMLResponse)
async def panel_etiquetas(series_id: UUID, request: Request,
                          db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Panel perezoso de etiquetas de la ficha (BL-ETQ1a)."""
    series = await _serie_o_404(db, series_id)
    etiquetas = await etiquetas_de_serie(db, series.id)
    respuesta = templates.TemplateResponse(
        request, "_etiquetas_serie.html",
        {"series": series, "etiquetas": etiquetas, "mensaje": None, "error": None},
    )
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.get("/{series_id}/etiquetas/sugerir", response_class=HTMLResponse)
async def sugerir_etiqueta(series_id: UUID, request: Request, etiqueta: str = "",
                           db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    if not etiqueta.strip():
        return HTMLResponse("")
    series = await _serie_o_404(db, series_id)
    sugerencias = await sugerencias_etiqueta(db, etiqueta, series_id=series.id)
    respuesta = templates.TemplateResponse(
        request, "_sugerencias_etiqueta_serie.html",
        {"series": series, "sugerencias": sugerencias},
    )
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.post("/{series_id}/etiquetas", response_class=HTMLResponse)
async def anadir_etiqueta_web(series_id: UUID, request: Request,
                              etiqueta: str = Form(""),
                              db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    series = await _serie_o_404(db, series_id)
    mensaje = error = None
    try:
        resultado = await anadir_etiqueta(db, series.id, etiqueta)
        mensaje = resultado.mensaje
    except EtiquetaInvalida as exc:
        error = str(exc)
    etiquetas = await etiquetas_de_serie(db, series.id)
    respuesta = templates.TemplateResponse(
        request, "_etiquetas_serie.html",
        {"series": series, "etiquetas": etiquetas, "mensaje": mensaje, "error": error},
    )
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.post("/{series_id}/etiquetas/quitar", response_class=HTMLResponse)
async def quitar_etiqueta_web(series_id: UUID, request: Request,
                              etiqueta: str = Form(""),
                              db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    series = await _serie_o_404(db, series_id)
    mensaje = error = None
    try:
        resultado = await quitar_etiqueta(db, series.id, etiqueta)
        mensaje = resultado.mensaje
    except EtiquetaInvalida as exc:
        error = str(exc)
    etiquetas = await etiquetas_de_serie(db, series.id)
    respuesta = templates.TemplateResponse(
        request, "_etiquetas_serie.html",
        {"series": series, "etiquetas": etiquetas, "mensaje": mensaje, "error": error},
    )
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.post("/{series_id}/politica", response_class=HTMLResponse)
async def cambiar_politica(series_id: UUID, request: Request,
                           wishlist_policy: str = Form(...),
                           db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """D8: el selector de la ficha de serie.

    Mismo blindaje que el resto de escrituras de la UI: el valor del formulario
    se valida contra una lista blanca explícita, nunca se escribe el body tal
    cual. `futuros`/`todos` se rechazan aquí también, no solo ocultos en el
    `<select>` — un formulario manipulado no puede fijar un valor reservado.

    Efecto **asimétrico** a propósito (revisión de PR): la generación espera al
    siguiente ciclo, pero la retirada se aplica aquí mismo y solo para esta
    serie. Cuando el coleccionista pide parar, no puede seguir buscándose hasta
    una hora. Es el mismo `UPDATE` atómico del ciclo
    (`services/politica.py::retirar_de_serie`), así que da igual quién llegue
    antes.
    """
    series = (await db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Serie no encontrada")
    try:
        politica = WishlistPolicy(wishlist_policy)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Política de búsqueda no válida") from exc
    if politica not in _POLITICAS_OFRECIDAS:
        raise HTTPException(
            status_code=422,
            detail="Esa política todavía no se puede aplicar — no hace nada",
        )
    # Puerta legal (C6, FR-20/21): SOLO al activar; desactivar nunca la exige. Va después del 404 y
    # del 422 y antes de escribir. Se responde 2xx (htmx no intercambia los 4xx) con el fragmento
    # SIN CAMBIOS, el aviso y el enlace.
    acuse = None
    if politica != WishlistPolicy.NONE:
        acuse = await is_acknowledged(db)
        if not acuse:
            contexto = await _contexto_politica(db, series, aviso_legal_pendiente=True)
            contexto["activacion_bloqueada_por_aviso"] = True
            return templates.TemplateResponse(
                request, "_politica_serie.html", {"series": series, **contexto}
            )
    series.wishlist_policy = politica
    await db.flush()

    querer = await querer_de_serie(db, series)
    retirados_ahora = await retirar_de_serie(db, series, querer)
    contexto = await _contexto_politica(
        db, series, querer=querer, retirados_ahora=retirados_ahora,
        aviso_legal_pendiente=None if acuse is None else not acuse)
    return templates.TemplateResponse(
        request, "_politica_serie.html", {"series": series, **contexto}
    )


@router.get("/{series_id}/numero/{issue_id}", response_class=HTMLResponse)
async def detalle_numero(series_id: UUID, issue_id: UUID, request: Request,
                         db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Ficha de un número: solo lectura, sin red y sin escrituras (#447)."""
    ficha = await cargar_ficha_numero(db, series_id, issue_id)
    if ficha is None:
        raise HTTPException(status_code=404, detail="Número no encontrado")
    autores = [
        {"etiqueta": etiqueta_rol(rol), "nombres": ficha.autores[rol]}
        for rol, _ in ROLES_ES if ficha.autores.get(rol)
    ]
    sinopsis_visible, sinopsis_resto = partir_sinopsis(ficha.sinopsis)
    respuesta = templates.TemplateResponse(request, "issue_detail.html", {
        "series": ficha.serie, "issue": ficha.issue, "ficha": ficha,
        "autores": autores, "textos": TEXTOS_FICHA,
        "sinopsis_visible": sinopsis_visible, "sinopsis_resto": sinopsis_resto,
        "lectura": await lectura_de(db, issue_id), "textos_lectura": TEXTOS_LECTURA,
        "estados_lectura": ((ReadingStatus.UNREAD, "Sin leer"),
                            (ReadingStatus.READING, "Leyendo"),
                            (ReadingStatus.COMPLETED, "Leído")),
    })
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.post("/{series_id}/numero/{issue_id}/lectura")
@router.post("/{series_id}/numero/{issue_id}/leido")
async def marcar_leido(series_id: UUID, issue_id: UUID, request: Request,
                       estado: str = Form(...), rating: str | None = Form(default=None),
                       nota: str | None = Form(default=None),
                       origen: str = Form(default="fila"),
                       db: AsyncSession = Depends(get_db)) -> Response:
    """Marca el número; 303 sin JS y fragmento completo (fila o bloque) con HTMX."""
    modo = "bloque" if origen == "numero" else "fila"
    extras = {}
    if rating is not None:
        extras["rating"] = rating
    if nota is not None:
        extras["nota"] = nota
    try:
        lectura = await marcar(db, issue_id, estado, series_id=series_id, **extras)
    except IssueNoEncontradoError:
        raise HTTPException(status_code=404, detail="Número no encontrado") from None
    except (EstadoInvalidoError, ValoracionInvalidaError, NotaInvalidaError) as exc:
        if request.headers.get("HX-Request") == "true":
            try:
                estado_enum = ReadingStatus(estado)
            except ValueError:
                estado_enum = ReadingStatus.UNREAD
            try:
                rating_int = int(rating) if rating not in (None, "") else None
            except (TypeError, ValueError):
                rating_int = None
            borrador = EstadoLectura(str(issue_id), estado_enum, rating_int, nota, None, None)
            respuesta = templates.TemplateResponse(
                request, "_lectura_control.html",
                {"series": SimpleNamespace(id=series_id), "issue_id": str(issue_id),
                 "lectura": borrador, "textos_lectura": TEXTOS_LECTURA, "modo": modo,
                 "error": str(exc), "origen": origen,
                 "estados_lectura": ((ReadingStatus.UNREAD, "Sin leer"),
                                     (ReadingStatus.READING, "Leyendo"),
                                     (ReadingStatus.COMPLETED, "Leído"))})
            respuesta.headers["Cache-Control"] = "no-store"
            return respuesta
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if request.headers.get("HX-Request") == "true":
        respuesta = templates.TemplateResponse(
            request, "_lectura_control.html",
            {"series": SimpleNamespace(id=series_id), "issue_id": str(issue_id),
             "lectura": lectura, "textos_lectura": TEXTOS_LECTURA, "modo": modo,
             "guardado": lectura.estado_es, "origen": origen,
             "estados_lectura": (
                 (ReadingStatus.UNREAD, "Sin leer"), (ReadingStatus.READING, "Leyendo"),
                 (ReadingStatus.COMPLETED, "Leído"))})
    else:
        destino = (f"/ui/series/{series_id}/numero/{issue_id}" if modo == "bloque"
                   else f"/ui/series/{series_id}#archivos-por-numero")
        respuesta = RedirectResponse(url=destino, status_code=303)
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.get("/{series_id}/numero/{issue_id}/previa", response_class=HTMLResponse)
async def previa_numero(series_id: UUID, issue_id: UUID, request: Request,
                        db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """BL-INF4: fragmento con la miniatura de la portada del número (hover/foco). Sin caché: es
    diminuto; la imagen y la miniatura en disco ya se cachean."""
    issue = await db.get(Issue, issue_id)
    if issue is None or issue.series_id != series_id:
        # htmx 4 intercambia también los 4xx: un chip obsoleto inyectaría el JSON del error en el
        # hueco de la previa. En una petición HTMX, vacío; en una visita directa, 404.
        if request.headers.get("HX-Request") == "true":
            return HTMLResponse("", headers={"Cache-Control": "no-store"})
        raise HTTPException(status_code=404, detail="Número no encontrado")
    ruta = await ruta_previa(db, series_id, issue_id)
    if ruta is None:
        respuesta: Response = HTMLResponse("")
    else:
        respuesta = templates.TemplateResponse(
            request, "_previa_numero.html",
            {"series_id": series_id, "issue_id": issue_id,
             "numero": issue.issue_number or "", "titulo": issue.title or ""})
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.get("/{series_id}/numero/{issue_id}/previa.jpg")
async def previa_numero_imagen(series_id: UUID, issue_id: UUID, request: Request,
                               db: AsyncSession = Depends(get_db)) -> Response:
    """BL-INF4: la miniatura en sí (240 px), con ETag y caché privada de un día."""
    issue = await db.get(Issue, issue_id)
    if issue is None or issue.series_id != series_id:
        return Response(status_code=404, headers={"Cache-Control": "no-store"})
    ruta = await ruta_previa(db, series_id, issue_id)
    if ruta is None:
        return Response(status_code=404, headers={"Cache-Control": "no-store"})
    try:
        datos = await asyncio.to_thread(ruta.read_bytes)
        etag = f'"{ruta.stat().st_mtime_ns}"'
    except OSError:      # la caché desapareció entre leer y medir: sin previa, no 500
        return Response(status_code=404, headers={"Cache-Control": "no-store"})
    return cached_image_response(request, datos, "image/jpeg", etag)


@router.get("/{series_id}/numero/{issue_id}/portada.jpg")
async def portada_numero_imagen(series_id: UUID, issue_id: UUID, request: Request,
                                db: AsyncSession = Depends(get_db)) -> Response:
    """BL-INF8: la portada del número para su ficha (600 px), con ETag y caché privada."""
    issue = await db.get(Issue, issue_id)
    if issue is None or issue.series_id != series_id:
        return Response(status_code=404, headers={"Cache-Control": "no-store"})
    ruta = await ruta_previa(db, series_id, issue_id, ancho=ANCHO_FICHA)
    if ruta is None:
        return Response(status_code=404, headers={"Cache-Control": "no-store"})
    try:
        datos = await asyncio.to_thread(ruta.read_bytes)
        etag = f'"{ruta.stat().st_mtime_ns}"'
    except OSError:
        return Response(status_code=404, headers={"Cache-Control": "no-store"})
    return cached_image_response(request, datos, "image/jpeg", etag)


@router.get("/{series_id}/portada")
async def portada(series_id: UUID, request: Request,
                  db: AsyncSession = Depends(get_db)) -> Response:
    """Cascada de portada de serie (BL-PORT1, #300; #435, #418; #592, #600):

    0. La portada ELEGIDA a mano (BL-INF6): manda sobre todo lo demás —también sobre la previa con
       ancho suficiente de #435—; se materializa en `covers/v3/<id>.jpg` al elegir y se vuelve a
       materializar si el archivo cambió. Si ya no da portada, se sigue con la cascada sin borrar
       la elección. Ver `_portada_elegida`.
    1. Una portada previa con ancho suficiente (`portada_previa_suficiente`: la caché antigua
       `covers/<id>.jpg` o la externa `covers/externa/<id>.jpg`, con >= 300 px, #435) → servirla
       (ETag por su `mtime`, 304) **sin** extraer, sin red, sin escribir y sin copiarla.
    2. `covers/v3/<id>.jpg` ya escrita → servirla (ETag por `mtime`, 304). `v3` guarda SOLO portadas
       sacadas de un archivo; una `v2` anterior se ignora (no se borra).
    3. Si no, el primer `File` no ausente, por `sort_order`, que dé portada (#419): solo los que
       `es_candidato_de_portada` acepta (ZIP por contenido o RAR por firma, #418; ausencia conocida o
       firma ajena se saltan), con un tope de `MAX_INTENTOS_PORTADA` aperturas, de
       `MAX_EVALUADOS_PORTADA` archivos evaluados y de `PRESUPUESTO_PORTADA_S` segundos → extraer su
       primera página a 600, escribir `v3`, servirla. Un RAR que ya falló y no ha cambiado se salta
       sin abrirlo (marca por archivo). Si la escritura falla, se sirve igualmente lo extraído con
       un ETag de sus bytes (FR-11, PR-2). Una sola generación por serie a la vez (FR-18). Si un RAR
       candidato se saltó por falta de turno y sale la portada de un archivo posterior, esa portada se
       sirve sin escribir `v3` y con `no-store` (H-1): la siguiente petición prueba el RAR.
    4. Si no hay archivo utilizable, `covers/<id>.jpg` legada (de menos de 300 px) → servirla
       **sin red y sin copiarla** (respaldo que solo se lee).
    5. Si tampoco, la externa pequeña ya descargada, o `cover_url` → descargar una vez a 600,
       escribir `covers/externa/` (nunca en `v3`), servirla.
    6. Nada de eso → 404: el `<img>` cae al marcador CSS, sin texto nuevo.

    La regeneración es **perezosa**: solo al pedir la imagen; el HTML de
    Biblioteca/Inicio/ficha no extrae ni escribe nada (FR-16). Una ausencia de portada
    no se cachea (los archivos se reintentan), salvo los RAR que fallaron por una causa suya.
    Todo el trabajo bloqueante (zipfile, Pillow, disco, subprocesos, red) va en
    `asyncio.to_thread` o en un cliente async, para no congelar el event loop.
    """
    series = await db.get(Series, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Serie no encontrada")

    covers = get_settings().covers_cache_path
    v3_path = covers / CACHE_VERSION / f"{series_id}.jpg"
    v2_path = covers / "v2" / f"{series_id}.jpg"
    legacy_path = covers / f"{series_id}.jpg"
    externa_path = covers / CARPETA_EXTERNA / f"{series_id}.jpg"

    # BL-INF6 (#592): la portada elegida a mano manda sobre la cascada. Su caché es la que regenera
    # la elección; si ya no está, `_portada_elegida` prueba a recuperarla y, si no, se sigue abajo.
    elegida = await _portada_elegida(series, db, covers, request)
    if elegida is not None:
        return elegida

    # #435 (BL-PORT5): una portada previa con resolución suficiente (la caché antigua o la externa, >=
    # 300 px) se conserva: se sirve ANTES que `v3` y que los archivos, sin extraer, sin red y sin
    # escribir ni copiar nada. Una `v2` ya escrita queda en disco, sin uso (#418).
    previa = await asyncio.to_thread(portada_previa_suficiente, covers, series_id)
    if previa is not None:
        try:
            etag = _etag_for(previa.ruta)
        except OSError:       # desapareció entre leerla y servirla: el ETag sale de los bytes
            etag = _etag_de_bytes(previa.datos)
        return cached_image_response(request, previa.datos, "image/jpeg", etag)

    if await asyncio.to_thread(v3_path.exists):
        data = await asyncio.to_thread(v3_path.read_bytes)
        return cached_image_response(request, data, "image/jpeg", _etag_for(v3_path))

    # B7 (revisión de PR, 2026-09-26): un File con is_missing=True ya no
    # está en disco — sin este filtro, la portada podía intentar (y
    # fallar) extraer de un CBZ borrado en vez de probar el siguiente
    # número disponible o caer al cover_url externo.
    archivos = [(a[0], a[1], a[2]) for a in (await db.execute(_stmt_archivos_de_portada(series_id))).all()]
    result = await _portada_de_archivos(series_id, archivos, covers, v3_path)
    ocupado = result == LECTOR_OCUPADO
    if result and not ocupado:
        data, content_type, escrita, efimera = result
        if efimera:
            # H-1: salió de un archivo posterior porque un RAR anterior no tuvo turno; no se cachea
            return Response(content=data, media_type=content_type, headers={"Cache-Control": "no-store"})
        etag = _etag_for(v3_path) if escrita else _etag_de_bytes(data)
        return cached_image_response(request, data, content_type, etag)

    # #506: si no hay archivo disponible que dé portada, una `v2` ya extraída de un archivo real
    # sigue siendo mejor que el marcador y que el respaldo viejo. Se sirve sin copiarla ni borrarla.
    # Con el lector ocupado es un sustituto pasajero: no se cachea (la próxima petición puede
    # generar la `v3` correcta).
    if await asyncio.to_thread(v2_path.exists):
        data = await asyncio.to_thread(v2_path.read_bytes)
        if ocupado:
            return Response(content=data, media_type="image/jpeg",
                            headers={"Cache-Control": "no-store"})
        return cached_image_response(request, data, "image/jpeg", _etag_for(v2_path))

    # Respaldo: la caché antigua (240/320) se sirve sin red y no se copia. Si hay un archivo
    # utilizable se regenera arriba; esta rama es para archivos ausentes o ilegibles, o series que ya
    # solo conservan la caché vieja (Q-1 del PO).
    if await asyncio.to_thread(legacy_path.exists):
        data = await asyncio.to_thread(legacy_path.read_bytes)
        if ocupado:
            return Response(content=data, media_type="image/jpeg",
                            headers={"Cache-Control": "no-store"})
        return cached_image_response(request, data, "image/jpeg", _etag_for(legacy_path))

    # #418: la portada externa vive APARTE de `v3`: mientras no haya portada de archivo se siguen
    # evaluando los candidatos (barato: los fallidos están marcados) y la serie cambia sola cuando uno
    # se hace legible.
    if await asyncio.to_thread(externa_path.exists):
        data = await asyncio.to_thread(externa_path.read_bytes)
        if ocupado:
            return Response(content=data, media_type="image/jpeg",
                            headers={"Cache-Control": "no-store"})
        return cached_image_response(request, data, "image/jpeg", _etag_for(externa_path))

    # #311: si guardó la imagen de relleno de Comic Vine («Blank!»), no tiene portada.
    motivo_fallo: list[str] = []
    if (series.cover_url and not es_portada_de_relleno(series.cover_url)
            and await fetch_and_cache_cover(series.cover_url, externa_path,
                                            ancho=SERIES_COVER_MAX_WIDTH,
                                            motivo_fallo=motivo_fallo)):
        data = await asyncio.to_thread(externa_path.read_bytes)
        if ocupado:
            return Response(content=data, media_type="image/jpeg",
                            headers={"Cache-Control": "no-store"})
        return cached_image_response(request, data, "image/jpeg", _etag_for(externa_path))

    # Una espera de cortesía no es un «no hay portada» definitivo: el navegador no debe
    # cachear la ausencia (mañana podría descargarse).
    # Tampoco lo es un lector ocupado (#418): la portada puede salir en cuanto quede libre.
    cabeceras = {"Cache-Control": "no-store"} if ("cortesia" in motivo_fallo or ocupado) else None
    raise HTTPException(status_code=404, detail="Sin portada disponible", headers=cabeceras)


def _etag_for(path: Path) -> str:
    return f'"{path.stat().st_mtime}"'


def _etag_de_bytes(data: bytes) -> str:
    """ETag de una imagen servida sin caché en disco (FR-11, #300): deriva de los bytes
    servidos, así que el mismo dato da el mismo ETag y la segunda petición recibe un 304,
    sin depender del `mtime` de un fichero que no llegó a escribirse."""
    return f'"{hashlib.sha256(data).hexdigest()}"'


# ── BL-INF6 (#592): elegir la portada de la serie entre varias ───────────────────────────────────

#: El aviso que ve la persona cuando la candidata ya no está (archivo retirado, URL cambiada) o el
#: formulario llegó manipulado. Nunca se distingue el caso: no hay nada que la persona pueda hacer
#: distinto en uno u otro, y el detalle técnico no va a superficie (CLAUDE.md §6).
AVISO_PORTADA_YA_NO_ESTA = (
    "Esa portada ya no está disponible. No se ha cambiado nada: abre «Elegir portada» otra vez "
    "y elige una de las que aparecen ahora."
)
#: Frase única de confirmación: la garantía va junto a la acción, no en la cabecera (§6).
MENSAJE_PORTADA_ELEGIDA = (
    "Portada cambiada. Solo en ZascArr: no se ha escrito, movido ni renombrado ningún archivo."
)
MENSAJE_PORTADA_LECTOR_OCUPADO = (
    "Ahora mismo ZascArr está abriendo otro CBR. Espera unos segundos y vuelve a probar: no se ha "
    "cambiado nada."
)
MENSAJE_PORTADA_NO_SALIO = (
    "No se ha podido sacar la portada de ese archivo. Prueba con otro número: no se ha cambiado nada."
)
MENSAJE_PORTADA_SIN_ESPACIO = (
    "No se ha podido guardar la portada en la caché de ZascArr (espacio o permisos). No se ha "
    "cambiado nada."
)
MENSAJE_PORTADA_EXTERNA_PERDIDA = (
    "Esa portada externa ya no está en la caché de ZascArr. No se ha cambiado nada: vuelve a abrir "
    "la serie para que ZascArr la pueda volver a preparar."
)
MENSAJE_PORTADA_AUTOMATICA = (
    "Portada automática otra vez: ZascArr la vuelve a elegir como antes. No se ha tocado ningún "
    "archivo."
)
AVISO_SIN_ELECCION = (
    "No hay una portada elegida a mano que quitar: ZascArr ya la elige automáticamente."
)


async def _version_de_portada(db: AsyncSession, series: Series) -> str:
    """Separador de caché del navegador de la portada de la ficha. Cambia al elegir una portada,
    para que el `<img>` con `?v=` no siga 24 h con la anterior (R-01 de BL-PORT1), y también si el
    archivo elegido se reemplazó: la elección es una referencia, no bytes congelados. Sin elección,
    el `2` de siempre."""
    eleccion = eleccion_de_portada(series)
    if eleccion is None:
        return "2"
    base = str(eleccion.get("fecha") or "")
    if eleccion.get("tipo") == TIPO_ARCHIVO:
        archivos = await archivo_de_portada(db, series.id, UUID(str(eleccion["file_id"])))
        if archivos:
            base += f":{archivos[0][3]}"      # mtime del archivo: cambia si se reemplaza
    return hashlib.sha256(base.encode()).hexdigest()[:8]


def _url_de_portada(series: Series, version: str) -> str:
    return f"/ui/series/{series.id}/portada?v={version}"


def _nombre_de_fuente(series: Series) -> str:
    """El nombre de la fuente de la portada externa en llano («Comic Vine»), para el origen de la
    candidata. Sin fuente registrada no se inventa una: «una fuente externa»."""
    if not series.metadata_source:
        return "una fuente externa"
    return NOMBRE_DE_FUENTE.get(str(series.metadata_source), "una fuente externa")


def _archivo_mas_nuevo_que_la_cache(ruta: Path, cache: Path, mtime_ns: int | None) -> bool:
    """¿El archivo de la elección cambió después de materializar la portada en `cache`?

    La elección guarda una REFERENCIA al archivo, no una copia congelada: si el CBZ se sustituye,
    la portada se vuelve a sacar del archivo nuevo. El instante sale de `File.file_mtime_ns` (lo
    escribe el rescan) y, si la fila no lo tiene, del propio disco; si no se puede leer, se sirve la
    caché que hay (la caché manda mientras el archivo no demuestre ser más nuevo)."""
    try:
        de_cache = cache.stat().st_mtime_ns
    except OSError:
        return True
    if mtime_ns is not None:
        return mtime_ns > de_cache
    try:
        return ruta.stat().st_mtime_ns > de_cache
    except OSError:
        return False


async def _portada_elegida(series: Series, db: AsyncSession, covers: Path,
                           request: Request) -> Response | None:
    """La portada elegida a mano (prioridad 0), o `None` para seguir la cascada de siempre.

    La elección GANA a todo, también a la «previa con ancho suficiente» de #435 que hoy se sirve
    antes de `covers/v3/<serie>.jpg`: si no, una externa previa taparía la elección. Es una
    referencia al archivo: si el archivo se reemplazó, se materializa otra vez (una sola escritura
    de 600 px) antes de servirlo. Si ya no da portada (archivo desaparecido, RAR con marca de
    fallo), se cae a la cascada SIN borrar la elección ni marcar un error falso."""
    eleccion = eleccion_de_portada(series)
    if eleccion is None:
        return None
    v3_path = covers / CACHE_VERSION / f"{series.id}.jpg"
    if eleccion["tipo"] == TIPO_EXTERNA:
        externa_path = covers / CARPETA_EXTERNA / f"{series.id}.jpg"
        if await asyncio.to_thread(externa_path.is_file):
            data = await asyncio.to_thread(externa_path.read_bytes)
            return cached_image_response(request, data, "image/jpeg", _etag_for(externa_path))
        # La externa desapareció: la cascada la puede volver a intentar desde `cover_url`.
        return None
    archivos = await archivo_de_portada(db, series.id, UUID(str(eleccion["file_id"])))
    if not archivos:
        # El archivo elegido ya no está en la biblioteca: fallback, la elección se conserva por si
        # vuelve (un disco desconectado, un reescaneo posterior).
        return None
    file_id, ruta, formato, mtime_ns = archivos[0]
    if (await asyncio.to_thread(v3_path.is_file)
            and not await asyncio.to_thread(_archivo_mas_nuevo_que_la_cache,
                                            Path(ruta), v3_path, mtime_ns)):
        data = await asyncio.to_thread(v3_path.read_bytes)
        return cached_image_response(request, data, "image/jpeg", _etag_for(v3_path))
    # El archivo cambió (o no hay caché): se materializa de nuevo; la caché vieja no se sirve.
    resultado = await asyncio.to_thread(_primera_portada, [(file_id, ruta, formato)], covers)
    if resultado is None:
        return None
    data, content_type = resultado
    escrita = True
    try:
        await asyncio.to_thread(write_cover_cache, v3_path, data)
    except OSError:
        escrita = False
    etag = _etag_for(v3_path) if escrita else _etag_de_bytes(data)
    return cached_image_response(request, data, content_type, etag)


async def _respuesta_panel_portada(series: Series, request: Request, db: AsyncSession, candidatas,
                                   *, mensaje: str | None, error: str | None,
                                   actualizar_cabecera: bool = False) -> HTMLResponse:
    """El panel «Elegir portada» completo (lo pinta el GET perezoso y lo repinta el POST)."""
    version = await _version_de_portada(db, series)
    respuesta = templates.TemplateResponse(request, "_elegir_portada.html", {
        "series": series,
        "candidatas": ([candidatas.externa] if candidatas.externa else []) + list(candidatas.numeros),
        "hay_mas": candidatas.hay_mas,
        "siguiente_desde": MAX_CANDIDATAS,
        "portada_actual": (_url_de_portada(series, version)
                           if candidatas.hay_portada_actual else None),
        "nombre_fuente": _nombre_de_fuente(series),
        "eleccion": eleccion_de_portada(series),
        "mensaje": mensaje,
        "error": error,
        "actualizar_cabecera": actualizar_cabecera,
    })
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


async def _candidatas_para_panel(db: AsyncSession, series: Series, *, desde: int = 0):
    return await candidatas_de_portada(db, series, desde=desde)


@router.get("/{series_id}/portada/elegir", response_class=HTMLResponse)
async def panel_elegir_portada(series_id: UUID, request: Request,
                               db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """BL-INF6: panel «Elegir portada». Se pide al desplegar (lazy): la ficha no genera ni pide
    miniaturas hasta entonces."""
    series = await _serie_o_404(db, series_id)
    candidatas = await _candidatas_para_panel(db, series)
    return await _respuesta_panel_portada(series, request, db, candidatas, mensaje=None, error=None)


@router.get("/{series_id}/portada/candidatas", response_class=HTMLResponse)
async def mas_candidatas_de_portada(series_id: UUID, request: Request,
                                    desde: int = Query(default=MAX_CANDIDATAS, ge=0),
                                    db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """BL-INF6: la siguiente tanda de números para el «Ver más números» del panel."""
    series = await _serie_o_404(db, series_id)
    candidatas = await _candidatas_para_panel(db, series, desde=desde)
    respuesta = templates.TemplateResponse(request, "_portada_candidatas.html", {
        "series": series,
        "candidatas": candidatas.numeros,
        "hay_mas": candidatas.hay_mas,
        "siguiente_desde": desde + MAX_CANDIDATAS,
        "nombre_fuente": _nombre_de_fuente(series),
    })
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.post("/{series_id}/portada/elegir", response_class=HTMLResponse)
async def elegir_portada_serie(series_id: UUID, request: Request,
                               tipo: str = Form(""), issue_id: str = Form(""),
                               file_id: str = Form(""), url: str = Form(""),
                               db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """BL-INF6: guarda la portada elegida y regenera SU caché (600 px).

    Seguridad sin token, por identidad del candidato: un `file_id` solo vale si es un archivo no
    ausente de un número de ESTA serie, y una `url` externa solo vale si es la `cover_url` que la
    serie ya tenía (la única externa que el panel ofrece). La acción es idempotente y reversible
    eligiendo otra; lo peor que consigue un formulario manipulado es volver a elegir una portada
    que ya estaba disponible. No se escribe en los archivos de la biblioteca.
    """
    series = await _serie_o_404(db, series_id)
    covers = get_settings().covers_cache_path
    mensaje = error = None

    if tipo == TIPO_ARCHIVO:
        try:
            issue_uuid, file_uuid = UUID(issue_id), UUID(file_id)
        except (ValueError, TypeError, AttributeError):
            error = AVISO_PORTADA_YA_NO_ESTA
        else:
            archivos = await archivos_de_numero(db, series.id, issue_uuid, file_id=file_uuid)
            if not archivos:
                error = AVISO_PORTADA_YA_NO_ESTA
            else:
                estado: dict = {}
                resultado = await asyncio.to_thread(
                    _primera_portada, archivos, covers, estado=estado)
                v3_path = covers / CACHE_VERSION / f"{series.id}.jpg"
                if resultado is None:
                    error = (MENSAJE_PORTADA_LECTOR_OCUPADO if estado.get("ocupado")
                             else MENSAJE_PORTADA_NO_SALIO)
                else:
                    datos, _tipo_imagen = resultado
                    try:
                        await asyncio.to_thread(write_cover_cache, v3_path, datos)
                    except OSError:
                        logger.warning("cover.eleccion_sin_espacio", serie=series.id)
                        error = MENSAJE_PORTADA_SIN_ESPACIO
                    else:
                        guardar_eleccion(series, tipo=TIPO_ARCHIVO,
                                         file_id=estado.get("file_id", file_uuid))
                        await db.flush()
                        mensaje = MENSAJE_PORTADA_ELEGIDA
    elif tipo == TIPO_EXTERNA:
        elegible = (series.cover_url and not es_portada_de_relleno(series.cover_url)
                    and url and url == series.cover_url)
        if not elegible:
            error = AVISO_PORTADA_YA_NO_ESTA
        else:
            ruta = await asyncio.to_thread(mejorar_portada_externa, covers, series.id)
            if ruta is None:
                error = MENSAJE_PORTADA_EXTERNA_PERDIDA
            else:
                guardar_eleccion(series, tipo=TIPO_EXTERNA, url=series.cover_url)
                await db.flush()
                mensaje = MENSAJE_PORTADA_ELEGIDA
    else:
        error = AVISO_PORTADA_YA_NO_ESTA

    candidatas = await _candidatas_para_panel(db, series)
    return await _respuesta_panel_portada(
        series, request, db, candidatas, mensaje=mensaje, error=error,
        actualizar_cabecera=mensaje is not None)


@router.post("/{series_id}/portada/quitar", response_class=HTMLResponse)
async def quitar_portada_serie(series_id: UUID, request: Request,
                               db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """BL-INF6: quita la elección y devuelve la serie a la portada automática.

    No borra ningún archivo de la biblioteca. De la caché de archivo (`v3`) solo retira la
    generada por la elección: si se quedara, la cascada seguiría sirviendo la portada elegida y
    «volver a la automática» no sería verdad. La `v3` se regenera sola (perezosa) cuando haga falta."""
    series = await _serie_o_404(db, series_id)
    covers = get_settings().covers_cache_path
    mensaje = error = None
    eleccion = eleccion_de_portada(series)
    if eleccion is None:
        error = AVISO_SIN_ELECCION
    else:
        quitar_eleccion(series)
        if eleccion["tipo"] == TIPO_ARCHIVO:
            v3_path = covers / CACHE_VERSION / f"{series.id}.jpg"
            try:
                await asyncio.to_thread(v3_path.unlink, missing_ok=True)
            except OSError:
                logger.warning("cover.eleccion_cache_no_borrada", serie=series.id)
        await db.flush()
        mensaje = MENSAJE_PORTADA_AUTOMATICA
    candidatas = await _candidatas_para_panel(db, series)
    return await _respuesta_panel_portada(
        series, request, db, candidatas, mensaje=mensaje, error=error,
        actualizar_cabecera=mensaje is not None)


@router.get("/{series_id}/portada/externa.jpg")
async def portada_externa_imagen(series_id: UUID, request: Request,
                                 db: AsyncSession = Depends(get_db)) -> Response:
    """BL-INF6: la portada externa cacheada como miniatura del selector. Solo lectura: si no
    existe, 404 sin caché (el marcador de `ui.portada` cubre el hueco)."""
    series = await db.get(Series, series_id)
    if series is None:
        return Response(status_code=404, headers={"Cache-Control": "no-store"})
    ruta = get_settings().covers_cache_path / CARPETA_EXTERNA / f"{series_id}.jpg"
    if not await asyncio.to_thread(ruta.is_file):
        return Response(status_code=404, headers={"Cache-Control": "no-store"})
    datos = await asyncio.to_thread(ruta.read_bytes)
    return cached_image_response(request, datos, "image/jpeg", f'"{ruta.stat().st_mtime_ns}"')


# ── #478/BL-CNV1: conversión CBR→CBZ (vista previa + confirmación) ───────────────────────────────

def _servicio_conversion(db):
    return ConversionDeArchivo(db, secret=get_settings().secret_key)


def _plantilla_conversion(request: Request) -> str:
    """Fragmento para HTMX; página completa cuando la piden navegando (enlace, URL a mano)."""
    if request.headers.get("HX-Request") == "true":
        return "_conversion_previa.html"
    return "conversion_pagina.html"


async def _serie_para_conversion(db, series_id, file_id):
    series = await _serie_o_404(db, series_id)
    return series


@router.get("/{series_id}/archivos/{file_id}/convertir", response_class=HTMLResponse)
async def convertir_vista_previa(series_id: UUID, file_id: UUID, request: Request,
                                 db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        series = await _serie_para_conversion(db, series_id, file_id)
    except HTTPException:
        if request.headers.get("HX-Request") == "true":
            return _sin_cache_conversion(HTMLResponse(""))
        raise
    try:
        vista = await _servicio_conversion(db).previsualizar(series_id, file_id)
    except Exception as exc:  # noqa: BLE001 — archivo/serie no encontrado
        if exc.__class__.__name__ in ("TokenInvalidoError", "SerieNoEncontrada"):
            raise HTTPException(status_code=404, detail="Archivo no encontrado") from None
        raise
    return _sin_cache_conversion(templates.TemplateResponse(
        request, _plantilla_conversion(request), {
            "series": series, "vista": vista, "modo": "convertir"}))


@router.post("/{series_id}/archivos/{file_id}/convertir", response_class=HTMLResponse)
async def convertir_confirmar(series_id: UUID, file_id: UUID, request: Request,
                              token: str = Form(..., max_length=MAX_TOKEN_CONVERSION),
                              forzar_compartido: str = Form(default=""),
                              db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    series = await _serie_o_404(db, series_id)
    try:
        resultado = await _servicio_conversion(db).confirmar(
            token, forzar_compartido=bool(forzar_compartido),
            file_id_esperado=file_id, serie_id_esperado=series_id)
    except Exception as exc:  # noqa: BLE001
        if exc.__class__.__name__ in ("TokenCaducadoError", "TokenInvalidoError"):
            if request.headers.get("HX-Request") == "true":
                # Un error en una petición HTMX no se pinta: se devuelve un fragmento con aviso.
                return _sin_cache_conversion(templates.TemplateResponse(
                    request, "_conversion_error.html",
                    {"series": series, "file_id": file_id, "mensaje": str(exc)}))
            codigo = 410 if exc.__class__.__name__ == "TokenCaducadoError" else 400
            raise HTTPException(status_code=codigo, detail=str(exc)) from None
        raise
    return _sin_cache_conversion(templates.TemplateResponse(
        request, "conversion_resultado.html", {"series": series, "resultado": resultado}))


@router.get("/{series_id}/archivos/{file_id}/convertir/deshacer", response_class=HTMLResponse)
async def deshacer_conversion_previa(series_id: UUID, file_id: UUID, request: Request,
                                     db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        series = await _serie_o_404(db, series_id)
    except HTTPException:
        if request.headers.get("HX-Request") == "true":
            return _sin_cache_conversion(HTMLResponse(""))
        raise
    try:
        vista = await _servicio_conversion(db).previsualizar_deshacer(series_id, file_id)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=404, detail="No hay conversión que deshacer") from None
    return _sin_cache_conversion(templates.TemplateResponse(
        request, _plantilla_conversion(request), {
            "series": series, "vista": vista, "modo": "deshacer"}))


@router.post("/{series_id}/archivos/{file_id}/convertir/deshacer", response_class=HTMLResponse)
async def deshacer_conversion_confirmar(series_id: UUID, file_id: UUID, request: Request,
                                        token: str = Form(..., max_length=MAX_TOKEN_CONVERSION),
                                        forzar_compartido: str = Form(default=""),
                                        db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    series = await _serie_o_404(db, series_id)
    try:
        resultado = await _servicio_conversion(db).deshacer(
            token, forzar_compartido=bool(forzar_compartido),
            file_id_esperado=file_id, serie_id_esperado=series_id)
    except Exception as exc:  # noqa: BLE001
        if exc.__class__.__name__ in ("TokenCaducadoError", "TokenInvalidoError"):
            if request.headers.get("HX-Request") == "true":
                # Un error en una petición HTMX no se pinta: se devuelve un fragmento con aviso.
                return _sin_cache_conversion(templates.TemplateResponse(
                    request, "_conversion_error.html",
                    {"series": series, "file_id": file_id, "mensaje": str(exc)}))
            codigo = 410 if exc.__class__.__name__ == "TokenCaducadoError" else 400
            raise HTTPException(status_code=codigo, detail=str(exc)) from None
        raise
    return _sin_cache_conversion(templates.TemplateResponse(
        request, "conversion_resultado.html", {"series": series, "resultado": resultado}))


@router.get("/{series_id}/convertir", response_class=HTMLResponse)
async def convertir_lote_previa(series_id: UUID, request: Request,
                                db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    series = await _serie_o_404(db, series_id)
    lote = await _servicio_conversion(db).previsualizar_lote(series_id)
    return _sin_cache_conversion(templates.TemplateResponse(request, "_conversion_lote.html", {
        "series": series, "lote": lote, "resultado": None}))


@router.post("/{series_id}/convertir", response_class=HTMLResponse)
async def convertir_lote_confirmar(series_id: UUID, request: Request,
                                   db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    series = await _serie_o_404(db, series_id)
    servicio = _servicio_conversion(db)
    resultado = await servicio.convertir_lote(series_id)
    lote = await servicio.previsualizar_lote(series_id)
    return _sin_cache_conversion(templates.TemplateResponse(request, "_conversion_lote.html", {
        "series": series, "lote": lote, "resultado": resultado}))


def _sin_cache_conversion(respuesta: HTMLResponse) -> HTMLResponse:
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


# ── #480/BL-CNV3: ComicInfo desde la ficha (mismo plan de B6) ────────────────────────────────────

def _servicio_comicinfo(db):
    return ComicInfoFichaService(db)


def _sin_cache_comicinfo(respuesta: HTMLResponse) -> HTMLResponse:
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.get("/{series_id}/archivos/{file_id}/comicinfo", response_class=HTMLResponse)
async def comicinfo_vista_previa(series_id: UUID, file_id: UUID, request: Request,
                                 db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    series = await _serie_o_404(db, series_id)
    try:
        vista = await _servicio_comicinfo(db).previsualizar(series_id, file_id)
    except Exception as exc:  # noqa: BLE001
        if exc.__class__.__name__ == "TokenInvalidoError":
            raise HTTPException(status_code=404, detail="Archivo no encontrado") from None
        raise
    return _sin_cache_comicinfo(templates.TemplateResponse(
        request, "_comicinfo_previa.html", {"series": series, "vista": vista, "file_id": file_id}))


@router.post("/{series_id}/archivos/{file_id}/comicinfo", response_class=HTMLResponse)
async def comicinfo_guardar(series_id: UUID, file_id: UUID, request: Request,
                            token: str = Form(..., max_length=MAX_TOKEN_COMICINFO),
                            forzar_compartido: str = Form(default=""),
                            db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    series = await _serie_o_404(db, series_id)
    try:
        resultado = await _servicio_comicinfo(db).aplicar(
            token, forzar_compartido=bool(forzar_compartido),
            file_id_esperado=file_id, serie_id_esperado=series_id)
    except Exception as exc:  # noqa: BLE001
        if exc.__class__.__name__ == "TokenCaducadoError":
            raise HTTPException(status_code=410, detail=str(exc),
                                headers={"Cache-Control": "no-store"}) from None
        if exc.__class__.__name__ == "TokenInvalidoError":
            raise HTTPException(status_code=400, detail=str(exc),
                                headers={"Cache-Control": "no-store"}) from None
        raise
    plantilla = ("comicinfo_resultado.html"
                 if request.headers.get("HX-Request") == "true"
                 else "comicinfo_resultado_pagina.html")
    return _sin_cache_comicinfo(templates.TemplateResponse(
        request, plantilla, {"series": series, "resultado": resultado}))
