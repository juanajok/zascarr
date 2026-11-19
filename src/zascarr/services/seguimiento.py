"""#993 — seguir series: detectar números nuevos en el foro y Prowlarr.

El disparador son las **fuentes de descarga** (subforo `showforum=5` y Prowlarr),
nunca la fecha del catálogo de Novedades. Este módulo solo detecta y crea deseos;
la descarga/importación sigue por el ciclo existente. Sin red en las funciones
puras; los adaptadores son inyectables para las pruebas.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from html import unescape
from urllib.parse import parse_qs, unquote_plus, urlsplit
from uuid import UUID

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.core.matcher import normalize_title
from zascarr.models import (
    EstadoAlias,
    File,
    Issue,
    LocalAlias,
    SeguimientoVisto,
    Series,
    SeriesKind,
    Wishlist,
    WishlistOrigin,
    WishlistStatus,
)
from zascarr.services.legal import is_acknowledged
from zascarr.services.series import numero_de_grapa
from zascarr.utils.naming import normalize_series_name, parse_comic_filename

logger = structlog.get_logger()

PRIORIDAD_DE_SEGUIMIENTO = 6
ESTADOS_VIVOS = (
    WishlistStatus.WANTED, WishlistStatus.SEARCHING, WishlistStatus.DOWNLOADING,
    WishlistStatus.DOWNLOADED, WishlistStatus.FAILED,
)
PLANTILLA_CLAVE_FORO = "tema:{tema_id}"
PLANTILLA_CLAVE_RELEASE = "release:{huella}"


@dataclass(frozen=True)
class TemaForo:
    id: int
    titulo: str
    url: str
    ultima_actividad: str | None


@dataclass(frozen=True)
class Hallazgo:
    fuente: str
    clave: str
    serie_id: UUID
    numero: int
    titulo: str | None


@dataclass
class InformeSeguimiento:
    desde_cache: int = 0
    temas: int = 0
    hallazgos: int = 0
    deseos: int = 0
    avisados: int = 0
    errores: list[str] = field(default_factory=list)


def _norm_alias(valor: str) -> str:
    return normalize_title(valor or "")


#: Marcadores de recopilatorio que el parser de nombres no siempre marca como
#: edición («One Piece 01 - Edición 3 en 1»): no identifican UNA grapa.
_RECOPILATORIO = re.compile(
    r"\b(?:\d+\s*en\s*1|integral|omnibus|omnigold|deluxe|colecci[oó]n|collection|pack)\b",
    re.IGNORECASE)


def casar_fichero(nombre: str, serie: Series, alias: set[str]) -> int | None:
    """Número de una grapa si el nombre de fichero casa con la serie, o None.

    Regla de identidad (la misma de `_candidato_es_del_numero`): parsear el
    NOMBRE DE FICHERO, rechazar tomos/ómnibus/anuales/especiales/packs y números
    no enteros, y exigir igualdad del nombre normalizado con el título o un alias
    local. Falla cerrado; nunca usa el título del hilo ni el título del release.
    """
    if _RECOPILATORIO.search(nombre or ""):
        return None
    parsed = parse_comic_filename(nombre)
    if parsed.edition_kind is not None:
        return None
    if parsed.is_annual or parsed.is_special or parsed.is_pack:
        return None
    texto = (parsed.issue_number or "").strip()
    if not texto.isdigit():
        return None
    candidato = normalize_series_name(parsed.series or "")
    if not candidato:
        return None
    titulo = normalize_series_name(serie.title or "")
    if titulo and candidato == titulo:
        return int(texto)
    alias_norm = {normalize_title(a) for a in (alias or set())}
    return int(texto) if candidato in alias_norm else None


def elegir_serie(parsed, series_seguidas: list[Series],
                 alias_por_serie: dict[UUID, set[str]]) -> tuple[Series, int] | None:
    """Elige una única serie seguida para el nombre/parseo; ambigüedad ⇒ None.

    Acepta tanto el nombre de fichero como el `ParsedComicName` ya parseado, para
    que los adaptadores no tengan que volver a parsear. Se registra
    `seguimiento.ambiguo` sin el nombre completo del release (solo número y series).
    """
    candidatas: list[tuple[Series, int]] = []
    for serie in series_seguidas:
        if isinstance(parsed, str):
            numero = casar_fichero(parsed, serie, alias_por_serie.get(serie.id, set()))
        else:
            parsed.edition_kind = getattr(parsed, "edition_kind", None)
            texto = (getattr(parsed, "issue_number", "") or "").strip()
            if (parsed.edition_kind is not None or getattr(parsed, "is_annual", False)
                    or getattr(parsed, "is_special", False) or getattr(parsed, "is_pack", False)
                    or not texto.isdigit()):
                numero = None
            else:
                candidato = normalize_series_name(getattr(parsed, "series", "") or "")
                titulo = normalize_series_name(serie.title or "")
                aliases = {normalize_title(a) for a in alias_por_serie.get(serie.id, set())}
                numero = (int(texto) if candidato and
                          (candidato == titulo or candidato in aliases) else None)
        if numero is not None:
            candidatas.append((serie, numero))
    if not candidatas:
        return None
    if len(candidatas) > 1:
        logger.warning("seguimiento.ambiguo", numero=candidatas[0][1],
                       series=[str(s.id) for s, _ in candidatas])
        return None
    return candidatas[0]


def nombres_de_enlaces(ed2k: list[str], magnet: list[str]) -> list[str]:
    """Nombres de fichero contenidos en enlaces eD2K/magnet (sin guardar enlaces)."""
    nombres: list[str] = []
    for enlace in [*(ed2k or []), *(magnet or [])]:
        enlace = unescape(enlace)
        if enlace.lower().startswith("ed2k://|file|"):
            partes = enlace.split("|")
            if len(partes) > 2 and partes[2]:
                nombres.append(unquote_plus(partes[2]))
        elif enlace.lower().startswith("magnet:?"):
            try:
                dn = parse_qs(urlsplit(enlace).query).get("dn", [])
            except ValueError:
                dn = []
            if dn and dn[0]:
                nombres.append(unquote_plus(dn[0]))
    return list(dict.fromkeys(n for n in nombres if n))


_MESES_ACTIVIDAD = {nombre: i for i, nombre in enumerate(
    ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
     "septiembre", "octubre", "noviembre", "diciembre"), start=1)}
_MESES_ACTIVIDAD.update({nombre: i for i, nombre in enumerate(
    ("january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"), start=1)})
_MESES_ACTIVIDAD.update({nombre[:3]: i for nombre, i in list(_MESES_ACTIVIDAD.items())})


def _fecha_con_mes(limpio: str) -> datetime | None:
    """Fecha IPB en inglés o español («5th August 2026 - 18:24», «Nov 14 2019, 14:38»)."""
    import re

    # Quita ordinales ingleses y normaliza el separador fecha/hora.
    normal = re.sub(r"(\d{1,2})(?:st|nd|rd|th)\b", r"\1", limpio, flags=re.I)
    normal = normal.replace("–", " ").replace(" - ", " ").replace(",", " ")
    normal = re.sub(r"\s+", " ", normal).strip()
    patrones = (
        re.compile(r"^(\d{1,2}) ([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+) (\d{4})(?: (\d{1,2}):(\d{2}))?$"),
        re.compile(r"^([A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+) (\d{1,2}) (\d{4})(?: (\d{1,2}):(\d{2}))?$"),
    )
    for i, patron in enumerate(patrones):
        m = patron.match(normal)
        if not m:
            continue
        if i == 0:
            dia, mes_txt, anio, hora, minuto = m.groups()
        else:
            mes_txt, dia, anio, hora, minuto = m.groups()
        mes = _MESES_ACTIVIDAD.get(mes_txt.lower())
        if mes is None:
            continue
        try:
            return datetime(int(anio), mes, int(dia),
                            int(hora or 0), int(minuto or 0), tzinfo=UTC)
        except ValueError:
            continue
    return None


def _fecha_de_actividad(texto: str | None, ahora: datetime) -> datetime | None:
    if not texto:
        return None
    limpio = texto.strip()
    bajo = limpio.lower()
    if bajo.startswith(("hoy", "today")):
        return ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    if bajo.startswith(("ayer", "yesterday")):
        return (ahora - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        return datetime.fromisoformat(limpio.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        pass
    con_mes = _fecha_con_mes(limpio)
    if con_mes is not None:
        return con_mes
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(limpio).astimezone(UTC)
    except (TypeError, ValueError):
        pass
    for formato in ("%d/%m/%Y", "%d/%m/%Y %H:%M", "%d-%m-%Y", "%d-%m-%Y %H:%M",
                    "%d.%m.%Y", "%d.%m.%Y %H:%M", "%Y-%m-%d", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(limpio, formato).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _huella_release(indexer: str, titulo: str, size: int) -> str:
    return hashlib.sha256(f"{indexer}|{titulo}|{size}".encode()).hexdigest()[:32]


async def _serie_por_id(db: AsyncSession, serie_id: UUID) -> Series | None:
    return await db.get(Series, serie_id)


async def cargar_series_seguidas(db: AsyncSession) -> tuple[list[Series], dict[UUID, set[str]]]:
    series = list((await db.execute(
        select(Series)
        .where(Series.follow_new_issues.is_(True))
        .where(Series.kind != SeriesKind.ONE_SHOT)
    )).scalars().all())
    alias: dict[UUID, set[str]] = {}
    if series:
        filas = (await db.execute(
            select(LocalAlias.series_id, LocalAlias.pattern_norm)
            .where(LocalAlias.series_id.in_([s.id for s in series]))
            .where(LocalAlias.estado == EstadoAlias.ACTIVO)
        )).all()
        for serie_id, patron in filas:
            alias.setdefault(serie_id, set()).add(patron)
    return series, alias


async def _marcar_visto(db: AsyncSession, fuente: str, clave: str, huella: str | None,
                        ahora: datetime, *, procesado: bool = True) -> None:
    fila = (await db.execute(
        select(SeguimientoVisto).where(SeguimientoVisto.fuente == fuente,
                                       SeguimientoVisto.clave == clave)
    )).scalar_one_or_none()
    if fila is None:
        db.add(SeguimientoVisto(fuente=fuente, clave=clave, huella=huella,
                                visto_en=ahora,
                                procesado_en=ahora if procesado else None))
    else:
        fila.huella = huella
        fila.procesado_en = ahora if procesado else fila.procesado_en


async def crear_deseos(db: AsyncSession, hallazgos: list[Hallazgo]) -> list[Hallazgo]:
    """Crea deseos de seguimiento, aplicando el dedupe de la spec.

    Un hallazgo se descarta si ya hay un File no desaparecido, un deseo vivo de
    cualquier origen, un RETIRADO o un deseo manual de toda la serie. Devuelve
    solo los deseos realmente creados (máximo lo decide quien llama).
    """
    creados: list[Hallazgo] = []
    vistos: set[tuple[UUID, int]] = set()
    por_serie: dict[UUID, list[Hallazgo]] = {}
    for hallazgo in hallazgos:
        clave = (hallazgo.serie_id, hallazgo.numero)
        if clave in vistos:
            continue
        vistos.add(clave)
        por_serie.setdefault(hallazgo.serie_id, []).append(hallazgo)

    for serie_id, grupo in por_serie.items():
        series = await _serie_por_id(db, serie_id)
        if series is None:
            continue
        issues = (await db.execute(
            select(Issue.id, Issue.issue_number, Issue.format)
            .where(Issue.series_id == serie_id)
        )).all()
        numeros_issue: dict[int, UUID] = {}
        for issue_id, issue_number, formato in issues:
            numero = numero_de_grapa(issue_number, formato)
            if numero is not None:
                numeros_issue[numero] = issue_id
        con_fichero: set[int] = set()
        if numeros_issue:
            ids = list(numeros_issue.values())
            filas = (await db.execute(
                select(File.issue_id)
                .where(File.issue_id.in_(ids))
                .where(File.is_missing.is_(False))
            )).all()
            for (issue_id,) in filas:
                for numero, iid in numeros_issue.items():
                    if iid == issue_id:
                        con_fichero.add(numero)
        deseos = (await db.execute(
            select(Wishlist.id, Wishlist.issue_id, Wishlist.numero, Wishlist.status)
            .where(Wishlist.series_id == serie_id)
        )).all()
        vivo_serie = any(issue_id is None and numero is None and status not in
                         (WishlistStatus.IMPORTED, WishlistStatus.RETIRADO)
                         for _, issue_id, numero, status in deseos)
        ocupados: set[int] = set()
        retirados: set[int] = set()
        for _, issue_id, numero, status in deseos:
            n = numero
            if n is None and issue_id is not None:
                n = next((k for k, v in numeros_issue.items() if v == issue_id), None)
            if n is None:
                continue
            if status == WishlistStatus.RETIRADO:
                retirados.add(n)
            elif status in ESTADOS_VIVOS:
                ocupados.add(n)
        if vivo_serie:
            logger.info("seguimiento.deseo_de_serie_vivo", serie=str(serie_id))
            continue
        for hallazgo in grupo:
            numero = hallazgo.numero
            if numero in con_fichero or numero in ocupados or numero in retirados:
                continue
            db.add(Wishlist(
                series_id=serie_id, status=WishlistStatus.WANTED,
                origen=WishlistOrigin.SEGUIMIENTO, priority=PRIORIDAD_DE_SEGUIMIENTO,
                numero=numero, added_at=datetime.now(UTC),
            ))
            creados.append(hallazgo)
    if creados:
        await db.flush()
    return creados


async def avisar(novedades: list[Hallazgo], *, notifier=None) -> int:
    """Un único aviso por pasada, después del commit y de mejor esfuerzo."""
    if not novedades:
        return 0
    if notifier is None:
        from zascarr.services.notifier import Notifier
        notifier = Notifier()
    textos = [(n.titulo or str(n.serie_id), n.numero) for n in novedades]
    try:
        resultado = await notifier.notify_novedades(textos)
    except Exception as exc:          # mejor esfuerzo: no revierte los deseos
        logger.warning("seguimiento.aviso_fallido", error=type(exc).__name__)
        return 0
    return len(novedades) if getattr(resultado, "ok", False) else 0


async def _procesar_foro(
    db: AsyncSession, foro, series: list[Series], alias: dict[UUID, set[str]],
    ahora: datetime, informe: InformeSeguimiento, *, max_temas: int,
    limite_deseos: int, desde_cache: int,
) -> tuple[list[Hallazgo], int, int]:
    """Foro: una lista y solo temas nuevos/actualizados; nunca la búsqueda IPB."""
    hallazgos: list[Hallazgo] = []
    temas = list(await foro.listar_temas(foro_id=getattr(get_settings(), "seguimiento_foro_id", 5),
                                          limite=max_temas))
    informe.temas = min(len(temas), max_temas)
    for tema in temas[:max_temas]:
        clave = PLANTILLA_CLAVE_FORO.format(tema_id=tema.id)
        fila = (await db.execute(
            select(SeguimientoVisto).where(SeguimientoVisto.fuente == "foro",
                                           SeguimientoVisto.clave == clave)
        )).scalar_one_or_none()
        if fila is not None and fila.huella == tema.ultima_actividad:
            desde_cache += 1
            continue
        actividad = _fecha_de_actividad(tema.ultima_actividad, ahora)
        # #1017 (O-2): en un tema ya visto, la referencia de frontera es la
        # actividad que tenía cuando se procesó (la huella guardada), no la
        # nueva. Así, la actualización de un tema viejo no crea deseos
        # históricos de una serie activada después. La huella se capturó en
        # `visto_en`: una fecha relativa («Hoy/Ayer») se resuelve contra ese
        # momento, no contra la pasada actual. Si no es fechable, `visto_en`
        # (cuándo lo vimos) es una cota superior conservadora.
        referencia = actividad
        if fila is not None:
            referencia = _fecha_de_actividad(fila.huella, fila.visto_en) or fila.visto_en
        if fila is None:
            # Primera pasada: solo se abre un tema si ALGUNA serie seguida ya
            # existía en la fecha del tema. El filtro definitivo es por serie
            # (abajo), no un min() global que mezclaría fronteras.
            elegibles = [s for s in series
                         if s.follow_new_issues_since is not None
                         and actividad is not None
                         and actividad >= s.follow_new_issues_since]
            if not elegibles:
                await _marcar_visto(db, "foro", clave, tema.ultima_actividad, ahora,
                                    procesado=False)
                desde_cache += 1
                continue
        try:
            resultado = await foro.leer_tema(tema.url)
        except Exception as exc:
            informe.errores.append(f"foro:{type(exc).__name__}")
            logger.warning("seguimiento.foro_tema_fallido", error=type(exc).__name__)
            break
        nombres = nombres_de_enlaces(resultado.ed2k_links, resultado.magnet_links)
        for nombre in nombres:
            elegido = elegir_serie(nombre, series, alias)
            if elegido is None:
                continue
            serie, numero = elegido
            # #993/#1017: cada serie tiene su propia frontera. Un tema anterior
            # a la activación de ESTA serie no puede generar su deseo, aunque
            # otra serie más antigua permita abrir el tema. En un tema ya visto,
            # la referencia es su actividad anterior (no la nueva).
            if (serie.follow_new_issues_since is not None
                    and referencia is not None
                    and referencia < serie.follow_new_issues_since):
                continue
            hallazgos.append(Hallazgo(
                fuente="foro", clave=f"tema:{tema.id}:{numero}", serie_id=serie.id,
                numero=numero, titulo=serie.title))
        await _marcar_visto(db, "foro", clave, tema.ultima_actividad, ahora)
        if len(hallazgos) >= limite_deseos:
            break
    return hallazgos, desde_cache, informe.temas


async def _procesar_prowlarr(
    db: AsyncSession, prowlarr, series: list[Series], alias: dict[UUID, set[str]],
    ahora: datetime, informe: InformeSeguimiento, *, max_series: int,
    limite_deseos: int,
) -> list[Hallazgo]:
    """Prowlarr: rotación por serie (clave `serie:<uuid>`), una consulta por serie."""
    if prowlarr is None or max_series <= 0:
        return []
    rotacion = (await db.execute(
        select(SeguimientoVisto)
        .where(SeguimientoVisto.fuente == "prowlarr")
        .where(SeguimientoVisto.clave.like("serie:%"))
        .order_by(SeguimientoVisto.visto_en.asc())
        .limit(max_series * 3)
    )).scalars().all()
    ultima: dict[str, SeguimientoVisto] = {r.clave: r for r in rotacion}

    def _turno(s: Series) -> tuple[datetime, str]:
        fila = ultima.get(f"serie:{s.id}")
        return (fila.visto_en if fila is not None else datetime.min.replace(tzinfo=UTC),
                str(s.id))

    ordenadas = sorted(series, key=_turno)[:max_series]
    hallazgos: list[Hallazgo] = []
    for serie in ordenadas:
        since = serie.follow_new_issues_since
        if since is None:
            # Sin frontera no se puede distinguir lo nuevo de lo histórico: no se toca.
            continue
        try:
            from zascarr.services.prowlarr import (
                COMIC_CATEGORIES,
                prowlarr_indexers_seleccionados,
            )
            seleccionados = prowlarr_indexers_seleccionados(get_settings())
            opciones = {"categories": COMIC_CATEGORIES}
            if seleccionados:
                opciones["indexer_ids"] = seleccionados
            resultados = await prowlarr.search(serie.title, **opciones)
        except Exception as exc:
            informe.errores.append(f"prowlarr:{type(exc).__name__}")
            logger.warning("seguimiento.prowlarr_fallido", error=type(exc).__name__)
            continue
        clave_serie = f"serie:{serie.id}"
        fila = ultima.get(clave_serie)
        if fila is None:
            fila = SeguimientoVisto(fuente="prowlarr", clave=clave_serie,
                                    visto_en=ahora, procesado_en=ahora)
            db.add(fila)
        else:
            fila.visto_en = ahora
            fila.procesado_en = ahora
        for resultado in resultados:
            fecha = _fecha_de_actividad(getattr(resultado, "publish_date", None), ahora)
            # AC-8: sin fecha o anterior a la frontera no es un número nuevo.
            if fecha is None or (since is not None and fecha < since):
                continue
            elegido = elegir_serie(resultado.title, series, alias)
            if elegido is None:
                continue
            serie_elegida, numero = elegido
            if serie_elegida.id != serie.id:
                continue
            huella = _huella_release(
                getattr(resultado, "indexer", ""), resultado.title,
                int(getattr(resultado, "size_bytes", 0) or 0))
            clave = PLANTILLA_CLAVE_RELEASE.format(huella=huella)
            visto = (await db.execute(
                select(SeguimientoVisto).where(SeguimientoVisto.fuente == "prowlarr",
                                               SeguimientoVisto.clave == clave)
            )).scalar_one_or_none()
            if visto is not None:
                informe.desde_cache += 1
                continue
            db.add(SeguimientoVisto(fuente="prowlarr", clave=clave, huella=fecha.isoformat()
                                    if fecha else None, visto_en=ahora,
                                    procesado_en=ahora))
            hallazgos.append(Hallazgo(fuente="prowlarr", clave=clave,
                                      serie_id=serie.id, numero=numero,
                                      titulo=serie.title))
            if len(hallazgos) >= limite_deseos:
                break
        if len(hallazgos) >= limite_deseos:
            break
    return hallazgos


async def ejecutar_pasada(
    db: AsyncSession, *, ahora: datetime | None = None, foro=None, prowlarr=None,
    notifier=None,
) -> InformeSeguimiento:
    """Una pasada completa: detecta, crea deseos, commit y avisa (una vez)."""
    ahora = ahora or datetime.now(UTC)
    informe = InformeSeguimiento()
    settings = get_settings()
    if not await is_acknowledged(db):
        logger.info("seguimiento.sin_legal")
        return informe
    series, alias = await cargar_series_seguidas(db)
    if not series:
        logger.info("seguimiento.sin_seguidos")
        return informe

    foro_configurado = bool(
        getattr(settings, "forum_enabled", False)
        and getattr(settings, "forum_url", "")
        and getattr(settings, "forum_username", ""))
    if foro is None and foro_configurado:
        from zascarr.services.forum_scraper import ForumScraper
        foro = ForumScraper(base_url=settings.forum_url,
                            rate_limit=settings.forum_rate_limit)
        try:
            if not await foro.login(settings.forum_username, settings.forum_password):
                informe.errores.append("foro:login")
                foro = None
        except Exception as exc:
            informe.errores.append(f"foro:{type(exc).__name__}")
            foro = None
    if foro is not None:
        try:
            hallazgos, informe.desde_cache, informe.temas = await _procesar_foro(
                db, foro, series, alias, ahora, informe,
                max_temas=getattr(settings, "seguimiento_max_temas", 10),
                limite_deseos=getattr(settings, "seguimiento_max_deseos", 10),
                desde_cache=informe.desde_cache)
            informe.hallazgos += len(hallazgos)
        except Exception as exc:
            informe.errores.append(f"foro:{type(exc).__name__}")
            logger.warning("seguimiento.foro_fallido", error=type(exc).__name__)
            hallazgos = []
    else:
        hallazgos = []

    if prowlarr is None and bool(getattr(settings, "prowlarr_enabled", False)
                                 and getattr(settings, "prowlarr_url", "")
                                 and getattr(settings, "prowlarr_api_key", "")):
        from zascarr.services.prowlarr import ProwlarrClient
        prowlarr = ProwlarrClient()
    if prowlarr is not None:
        try:
            de_prowlarr = await _procesar_prowlarr(
                db, prowlarr, series, alias, ahora, informe,
                max_series=getattr(settings, "seguimiento_max_series_prowlarr", 10),
                limite_deseos=getattr(settings, "seguimiento_max_deseos", 10))
            informe.hallazgos += len(de_prowlarr)
            hallazgos.extend(de_prowlarr)
        except Exception as exc:
            informe.errores.append(f"prowlarr:{type(exc).__name__}")
            logger.warning("seguimiento.prowlarr_fallido", error=type(exc).__name__)

    # Un deseo por (serie, número), como mucho el cupo de la pasada.
    unicos: list[Hallazgo] = []
    vistos: set[tuple[UUID, int]] = set()
    for h in hallazgos:
        clave = (h.serie_id, h.numero)
        if clave not in vistos:
            vistos.add(clave)
            unicos.append(h)
    creados = await crear_deseos(db, unicos[:getattr(settings, "seguimiento_max_deseos", 10)])
    informe.deseos = len(creados)
    await db.commit()

    if creados:
        informe.avisados = await avisar(
            creados[:getattr(settings, "seguimiento_max_avisos", 5)], notifier=notifier)
    try:
        await purgar_vistos(db, ahora=ahora,
                            dias=getattr(settings, "seguimiento_retencion_dias", 90))
        await db.commit()
    except Exception as exc:
        logger.warning("seguimiento.purga_fallida", error=type(exc).__name__)
    logger.info("seguimiento.pass_done", desde_cache=informe.desde_cache,
                temas=informe.temas, hallazgos=informe.hallazgos,
                deseos=informe.deseos, avisados=informe.avisados,
                errores=len(informe.errores))
    return informe


async def purgar_vistos(db: AsyncSession, *, ahora: datetime | None = None,
                        dias: int = 90) -> int:
    """Borra lo visto hace más de `dias`; no guarda enlaces ni títulos."""
    ahora = ahora or datetime.now(UTC)
    limite = ahora - timedelta(days=dias)
    resultado = await db.execute(
        delete(SeguimientoVisto).where(SeguimientoVisto.visto_en < limite))
    return int(resultado.rowcount or 0)
