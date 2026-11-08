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
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
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
    Series,
    Wishlist,
    WishlistOrigin,
    WishlistPolicy,
    WishlistStatus,
)
from zascarr.services.archivos_por_numero import archivos_por_numero
from zascarr.services.comic_vine import es_portada_de_relleno
from zascarr.services.enricher import puede_enlazarse_con_comic_vine
from zascarr.services.legal import is_acknowledged
from zascarr.services.politica import (
    horas_minimas,
    pendientes_de_buscar,
    querer_de_serie,
    retirar_de_serie,
    texto_de_cota,
)
from zascarr.services.procedencia import procedencia_de_serie
from zascarr.services.series import razon_de_no_calculable
from zascarr.utils.cover import (
    CACHE_VERSION,
    CARPETA_EXTERNA,
    SERIES_COVER_MAX_WIDTH,
    cached_image_response,
    es_candidato_de_portada,
    extract_cover_thumbnail,
    fetch_and_cache_cover,
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
                return result
            logger.info("cover.candidato_sin_portada", intento=intentos)
            continue
        try:
            return portada_de_rar(path, covers, ancho=SERIES_COVER_MAX_WIDTH)
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
    return templates.TemplateResponse(request, "series_detail.html", {
        "series": series, "present": sorted(poseidos),
        "missing": huecos.faltantes, "huecos": huecos,
        **politica,
        # BL-R1b: los archivos de cada número (consulta fija, no una por archivo).
        "archivos_por_numero": await archivos_por_numero(db, series.id),
        "procedencia": procedencia_de_serie(series),
        "volver": volver_segura(volver, series_id),
        "razones_sin_boton": RAZONES_SIN_BOTON,
    })


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


@router.get("/{series_id}/portada")
async def portada(series_id: UUID, request: Request,
                  db: AsyncSession = Depends(get_db)) -> Response:
    """Cascada de portada de serie (BL-PORT1, #300; #435, #418):

    0. Una portada previa con ancho suficiente (`portada_previa_suficiente`: la caché antigua
       `covers/<id>.jpg` o la externa `covers/externa/<id>.jpg`, con >= 300 px, #435) → servirla
       (ETag por su `mtime`, 304) **sin** extraer, sin red, sin escribir y sin copiarla.
    1. `covers/v3/<id>.jpg` ya escrita → servirla (ETag por `mtime`, 304). `v3` guarda SOLO portadas
       sacadas de un archivo; una `v2` anterior se ignora (no se borra).
    2. Si no, el primer `File` no ausente, por `sort_order`, que dé portada (#419): solo los que
       `es_candidato_de_portada` acepta (ZIP por contenido o RAR por firma, #418; ausencia conocida o
       firma ajena se saltan), con un tope de `MAX_INTENTOS_PORTADA` aperturas, de
       `MAX_EVALUADOS_PORTADA` archivos evaluados y de `PRESUPUESTO_PORTADA_S` segundos → extraer su
       primera página a 600, escribir `v3`, servirla. Un RAR que ya falló y no ha cambiado se salta
       sin abrirlo (marca por archivo). Si la escritura falla, se sirve igualmente lo extraído con
       un ETag de sus bytes (FR-11, PR-2). Una sola generación por serie a la vez (FR-18). Si un RAR
       candidato se saltó por falta de turno y sale la portada de un archivo posterior, esa portada se
       sirve sin escribir `v3` y con `no-store` (H-1): la siguiente petición prueba el RAR.
    3. Si no hay archivo utilizable, `covers/<id>.jpg` legada (de menos de 300 px) → servirla
       **sin red y sin copiarla** (respaldo que solo se lee).
    4. Si tampoco, la externa pequeña ya descargada, o `cover_url` → descargar una vez a 600,
       escribir `covers/externa/` (nunca en `v3`), servirla.
    5. Nada de eso → 404: el `<img>` cae al marcador CSS, sin texto nuevo.

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
    legacy_path = covers / f"{series_id}.jpg"
    externa_path = covers / CARPETA_EXTERNA / f"{series_id}.jpg"

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

    # Respaldo: la caché antigua (240/320) se sirve sin red y no se copia. Si hay un archivo
    # utilizable se regenera arriba; esta rama es para archivos ausentes o ilegibles, o series que ya
    # solo conservan la caché vieja (Q-1 del PO).
    if await asyncio.to_thread(legacy_path.exists):
        data = await asyncio.to_thread(legacy_path.read_bytes)
        return cached_image_response(request, data, "image/jpeg", _etag_for(legacy_path))

    # #418: la portada externa vive APARTE de `v3`: mientras no haya portada de archivo se siguen
    # evaluando los candidatos (barato: los fallidos están marcados) y la serie cambia sola cuando uno
    # se hace legible.
    if await asyncio.to_thread(externa_path.exists):
        data = await asyncio.to_thread(externa_path.read_bytes)
        return cached_image_response(request, data, "image/jpeg", _etag_for(externa_path))

    # #311: si guardó la imagen de relleno de Comic Vine («Blank!»), no tiene portada.
    motivo_fallo: list[str] = []
    if (series.cover_url and not es_portada_de_relleno(series.cover_url)
            and await fetch_and_cache_cover(series.cover_url, externa_path,
                                            ancho=SERIES_COVER_MAX_WIDTH,
                                            motivo_fallo=motivo_fallo)):
        data = await asyncio.to_thread(externa_path.read_bytes)
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
