# ruff: noqa: E501
"""
Router de la auditoría de biblioteca (B16) — /ui/auditoria.

Enseña el informe de LibraryAudit y, solo desde aquí y solo a mano,
deja disparar la adopción (B11). El orden importa y es la historia
entera: primero el coleccionista ve qué hay repetido en su disco,
después decide adoptar. Hasta v1.4.8 la adopción saltaba sola en el
primer arranque y el dedupe elegía copia por orden alfabético sin que
nadie se enterara.

Esta pantalla NO borra ni mueve nada, ni ofrece hacerlo: las rutas
duplicadas se muestran para que el coleccionista actúe en su disco con
sus herramientas. Sugerir un borrado desde aquí sería justo la clase de
decisión irreversible que la historia se propone no tomar sola.
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zascarr import database
from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.models import (
    ApartadoEstado,
    ApartadoOperacion,
    File,
    ImportRun,
    Issue,
    Series,
)
from zascarr.services import registro_biblioteca, rescan_biblioteca
from zascarr.services.aceptacion_adopcion import MAX_ILEGIBLES, aceptar, evaluar
from zascarr.services.apartado_duplicados import (
    ApartadoDuplicadosService,
    ApartadoError,
    GrupoEntrada,
    TokenApartadoInvalido,
)
from zascarr.services.conversion import ConversionDeArchivo
from zascarr.services.library_adopter import EstadoAdopcion, InventarioBiblioteca, LibraryAdopter
from zascarr.services.library_audit import LibraryAudit
from zascarr.utils.naming import parse_comic_filename
from zascarr.web.disponibilidad import registrar_filtros
from zascarr.web.routes import crear_templates

templates = crear_templates()
registrar_filtros(templates)


def _tamano(num_bytes: int | None) -> str:
    """Tamaño en la unidad que le sirve a una persona. Sin esto, la
    plantilla fijaba GB/MB y enseñaba "0.0 GB" o "0 MB cada uno" en
    cuanto los archivos eran pequeños — un número que no informa de
    nada y que además hace dudar de si el resto del informe es fiable."""
    b = num_bytes or 0
    if b >= 1024 ** 3:
        return f"{b / 1024 ** 3:.1f} GB"
    if b >= 1024 ** 2:
        return f"{b / 1024 ** 2:.0f} MB"
    if b >= 1024:
        return f"{b / 1024:.0f} KB"
    return f"{b} bytes"


templates.env.filters["tamano"] = _tamano


def _motivo_apartado(motivo: str | None) -> str:
    """Motivos internos del servicio A en lenguaje llano (sin códigos)."""
    return {
        "contenido_cambiado": "El contenido de una copia cambió; no se ha apartado.",
        "catalogo_ambiguo": "El catálogo tiene más de una ficha para este grupo; no se ha movido nada.",
        "sitio_ocupado": "El sitio original está ocupado; no se ha sobrescrito nada.",
        "cuarentena_ausente": "La copia apartada ya no está en la cuarentena.",
        "montura_distinta": "La cuarentena está en otra montura; no se ha copiado nada.",
        "no_existe": "Alguna copia ya no está.",
        "destino_ocupado": "La cuarentena ya tiene esa ruta; no se ha sobrescrito nada.",
        "compensacion_fallida": "No se pudo devolver una copia ya movida; hace falta revisarlo.",
        "error_disco": "Hubo un problema de disco; la operación no se ha completado.",
    }.get(motivo or "", "No se ha completado la operación.")


templates.env.filters["motivo_apartado"] = _motivo_apartado

router = APIRouter(prefix="/ui/auditoria", tags=["ui"])


async def _ultimo_informe(db: AsyncSession) -> dict | None:
    run = (await db.execute(
        select(ImportRun)
        .where(ImportRun.details["kind"].astext == "audit")
        .order_by(ImportRun.started_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if not run:
        return None
    detalles = dict(run.details or {})
    detalles["started_at"] = run.started_at
    detalles["files_scanned"] = run.files_scanned
    return detalles




async def _fragmento_registro(request: Request, db: AsyncSession, *, inc: InventarioBiblioteca | None = None,
                              cambio: bool = False, recien_aceptado: bool = False,
                              conflicto: bool = False) -> HTMLResponse:
    """Lo que el coleccionista debe ver del registro AHORA: progreso, resultado o inventario previo.
    `inc` (#326) es el inventario de archivos NUEVOS que se acaba de calcular a petición suya; `cambio`, que al confirmar la carpeta
    ya no era la que revisó; `recien_aceptado`, que la petición acaba de aceptar (para el foco); `conflicto`, que el intento
    no era válido y hay que enseñar el estado fresco."""
    reg = registro_biblioteca.estado_actual()
    contexto: dict = {"reg": reg, "estado": EstadoAdopcion.HECHA, "inv": None, "series": 0, "inc": inc,
                      "cambio": cambio, "adopcion": await evaluar(db, en_marcha=reg.en_marcha),
                      "recien_aceptado": recien_aceptado, "conflicto": conflicto}
    if reg.fase is registro_biblioteca.FaseRegistro.INACTIVO:
        adopter = LibraryAdopter(db)
        contexto["estado"] = await adopter.estado()
        if contexto["estado"] in (EstadoAdopcion.PENDIENTE, EstadoAdopcion.CATALOGO_PREVIO):
            contexto["inv"] = await adopter.inventario()
            contexto["series"] = (await db.execute(select(func.count(Series.id)))).scalar() or 0
    return templates.TemplateResponse(request, "_auditoria_registro.html", contexto)


@router.get("/registro", response_class=HTMLResponse)
async def registro(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Inventario previo, progreso o resultado del registro de la biblioteca. Solo lectura."""
    return await _fragmento_registro(request, db)


@router.post("/adoptar", response_class=HTMLResponse)
async def adoptar(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """B11, explícito: registra la biblioteca SIN mover ni renombrar nada, aunque ya haya series.

    Lanza el registro en segundo plano (ver `services/registro_biblioteca.py`) y devuelve el progreso; la
    página lo vuelve a pedir hasta que termina. Si ya hay uno en marcha no lanza otro. Repetirlo tras un
    fallo continúa donde se quedó."""
    en_marcha = registro_biblioteca.estado_actual().fase is registro_biblioteca.FaseRegistro.CORRIENDO
    if not en_marcha and await LibraryAdopter(db).puede_registrar():
        registro_biblioteca.iniciar(database.async_session_factory)
    return await _fragmento_registro(request, db)


@router.post("/aceptar-ilegibles", response_class=HTMLResponse)
async def aceptar_ilegibles(request: Request, run_id: UUID = Form(...),
                            count: int = Form(..., ge=1, le=MAX_ILEGIBLES),
                            db: AsyncSession = Depends(get_db)):
    """#332 residual 4: aceptación explícita de una adopción inicial incompleta.

    HTMX no intercambia 4xx: si el intento no vale, se devuelve el fragmento actualizado con 200 y
    el conflicto visible. Un cliente normal recibe 409/404 con el motivo, sin escribir nada."""
    resultado = await aceptar(db, run_id, count,
                              en_marcha=registro_biblioteca.estado_actual().en_marcha)
    if request.headers.get("HX-Request") == "true":
        return await _fragmento_registro(
            request, db, recien_aceptado=resultado.reason == "accepted",
            conflicto=not resultado.ok)
    if not resultado.ok:
        return JSONResponse({"reason": resultado.reason}, status_code=resultado.status)
    return await _fragmento_registro(request, db, recien_aceptado=True)


@router.get("/nuevos", response_class=HTMLResponse)
async def nuevos(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """#326: busca los archivos NUEVOS de la biblioteca ya registrada. Solo lectura: recorre nombres y rutas de la carpeta y las cruza con las
    registradas; no abre ningún archivo, no escribe en el catálogo y no pide nada a internet. Registrarlos es otro paso, con confirmación."""
    if registro_biblioteca.estado_actual().en_marcha or not await LibraryAdopter(db).ofrece_registro_incremental():
        return await _fragmento_registro(request, db)
    return await _fragmento_registro(request, db, inc=await LibraryAdopter(db).inventario())


@router.post("/registrar-nuevos", response_class=HTMLResponse)
async def registrar_nuevos(request: Request, huella: str = Form(...), db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """#326, explícito: registra SOLO los archivos nuevos que la persona vio y confirmó (la `huella` de esa lista). Si la carpeta ya no da la
    misma huella —apareció o desapareció algo desde que la revisó— no registra nada y enseña la lista de ahora. Sin mover ni renombrar nada,
    sin tocar lo ya registrado y sin repetir el registro inicial. Una sola ejecución a la vez, compartida con el registro inicial."""
    if registro_biblioteca.estado_actual().en_marcha:
        return await _fragmento_registro(request, db)
    adopter = LibraryAdopter(db)
    if not await adopter.ofrece_registro_incremental():
        return await _fragmento_registro(request, db)
    inv = await adopter.inventario()
    if not inv.se_puede_confirmar:       # carpeta ilegible, recorrido incompleto o nada que registrar: no se confirma nada global
        return await _fragmento_registro(request, db, inc=inv)
    if inv.huella != huella:
        return await _fragmento_registro(request, db, inc=inv, cambio=True)
    registro_biblioteca.iniciar(database.async_session_factory, alcance=inv.rutas_nuevas)
    return await _fragmento_registro(request, db)


# ── BL-R9: rescan de la biblioteca (a demanda; el periódico corre en main.py) ──

_CAMPOS_RESUMEN = (
    "files_scanned", "sin_cambios", "ya_registrados", "nuevos_entregados",
    "nuevos_registrados", "nuevos_a_revisar", "repetidos", "reenlazados",
    "re_triados", "re_triados_igual", "re_triados_cambiado",
    "re_triados_a_revisar", "re_triados_descartado", "copias_de_otra",
    "re_triados_protegidos", "discrepancias_registradas",
    "desaparecidos", "reaparecidos", "errores", "omitidos", "ambiguos",
    "no_revisado", "unreadable", "por_comprobar", "resultado_biblioteca",
)


def _resumen(informe) -> dict | None:
    """Normaliza el informe —en memoria (`RescanReport`) o persistido (dict de `_ultimo_rescan`)—
    a un dict para la plantilla. Un informe persistido debe pintarse igual que uno en memoria:
    tras un reinicio del proceso el estado en memoria ya no existe y la pantalla lee el `ImportRun`."""
    if informe is None:
        return None
    fuente = informe.get if isinstance(informe, dict) else (lambda c: getattr(informe, c, None))
    out: dict = {}
    for c in _CAMPOS_RESUMEN:
        v = fuente(c)
        if c in ("errores", "omitidos", "ambiguos") or isinstance(v, (list, tuple)):
            out[c] = list(v) if v else []
        elif isinstance(v, bool):
            out[c] = v
        elif isinstance(v, (int, float)):
            out[c] = v or 0
        else:
            out[c] = v or ""
    out["disparador"] = fuente("disparador") or "manual"
    out["started_at"] = fuente("started_at")
    return out


async def _ultimo_rescan(db: AsyncSession) -> dict | None:
    """El último rescan persistido (`kind="rescan"`), para una página recién cargada."""
    run = (await db.execute(
        select(ImportRun)
        .where(ImportRun.details["kind"].astext == "rescan")
        .order_by(ImportRun.started_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if not run:
        return None
    detalles = dict(run.details or {})
    detalles["started_at"] = run.started_at
    detalles["files_scanned"] = run.files_scanned
    detalles["errores"] = detalles.get("errores") or []
    return detalles


def _texto_cadencia() -> str:
    minutos = get_settings().rescan_interval_minutes
    if minutos <= 0:
        return "El rescan automático está apagado."
    if minutos == 1440:
        return "Además, ZascArr lo hace solo una vez al día."
    if minutos % 1440 == 0:
        return f"Además, ZascArr lo hace solo cada {minutos // 1440} días."
    if minutos % 60 == 0:
        return f"Además, ZascArr lo hace solo cada {minutos // 60} horas."
    return f"Además, ZascArr lo hace solo cada {minutos} minutos."


async def _contexto_rescan(db: AsyncSession, *, recien_lanzada: bool = False,
                           ya_en_curso: bool = False) -> dict:
    """Contexto común de página y fragmento; solo lee."""
    estado = rescan_biblioteca.estado_actual()
    resumen = _resumen(estado.informe)
    if resumen is None:
        resumen = await _ultimo_rescan(db)
    return {
        "estado_rescan": estado,
        "resumen": resumen,
        "cadencia": _texto_cadencia(),
        "recien_lanzada": recien_lanzada,
        "ya_en_curso": ya_en_curso,
        "recien_terminada": rescan_biblioteca.consumir_foco_resultado()
        if estado.fase is rescan_biblioteca.FaseRescan.TERMINADO else False,
    }


@router.get("/rescanear", response_class=HTMLResponse)
async def rescanear_estado(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Fragmento de estado del rescan. GET no lanza nada ni escribe: solo lee memoria e ImportRun."""
    contexto = await _contexto_rescan(db)
    respuesta = templates.TemplateResponse(request, "_rescan_biblioteca.html", contexto)
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.post("/rescanear", response_class=HTMLResponse)
async def rescanear(request: Request, db: AsyncSession = Depends(get_db)):
    """Lanza el rescan en segundo plano y responde ya. No espera a la operación."""
    lanzada = rescan_biblioteca.iniciar_manual(database.async_session_factory)
    if request.headers.get("HX-Request") != "true":
        return RedirectResponse("/ui/auditoria", status_code=303)
    contexto = await _contexto_rescan(db, recien_lanzada=lanzada, ya_en_curso=not lanzada)
    respuesta = templates.TemplateResponse(request, "_rescan_biblioteca.html", contexto)
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta

# ── BL-DUP1 (#264 B): apartar duplicados idénticos, con vista previa y deshacer ──

def _no_store(respuesta):
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@dataclass
class CopiaDuplicado:
    ruta_rel: str
    carpeta: str
    mtime: str
    catalogo: str
    nombre: str
    fila: bool = False


@dataclass
class GrupoDuplicado:
    sha256: str
    size_bytes: int
    bytes_recuperables: int
    copias: list[CopiaDuplicado]


def _texto_fecha(segundos: float | None) -> str:
    if not segundos:
        return "sin fecha"
    return datetime.fromtimestamp(segundos).strftime("%d/%m/%Y %H:%M")


def _pista_nombre(nombre: str) -> str:
    """Pista de nombre entendible; nunca preselecciona ni puntúa una copia."""
    try:
        parsed = parse_comic_filename(nombre)
    except Exception:  # noqa: BLE001 — un nombre raro no debe romper la pantalla
        return "No se entiende el nombre"
    if parsed.series and parsed.issue_number:
        return f'Parece «{parsed.series} #{parsed.issue_number}»'
    if parsed.series:
        return f'Parece «{parsed.series}»; no se ve el número'
    return "No se entiende el nombre"


async def _filas_catalogo(db: AsyncSession, rutas: list[str]) -> dict[str, tuple[File, Issue | None, Series | None]]:
    """File(s) de las rutas, con su Issue/Series. Si el doble de pruebas no
    implementa `scalars`, se devuelve vacío: la pantalla sigue funcionando."""
    if not rutas:
        return {}
    try:
        resultado = await db.execute(
            select(File, Issue, Series)
            .outerjoin(Issue, File.issue_id == Issue.id)
            .outerjoin(Series, Issue.series_id == Series.id)
            .where(File.file_path.in_(rutas))
        )
        filas = resultado.all()
    except (AttributeError, TypeError):
        return {}
    return {fila[0].file_path: (fila[0], fila[1], fila[2]) for fila in filas}


def _texto_catalogo(fila: tuple[File, Issue | None, Series | None] | None) -> str:
    if fila is None:
        return "No está en el catálogo"
    _f, issue, series = fila
    if issue is None:
        return "En el catálogo, sin número vinculado"
    numero = f"#{issue.issue_number}" if issue.issue_number else "sin número"
    if series is not None and series.title:
        return f"Vinculada a «{series.title}» {numero}"
    return f"Vinculada a un número {numero}"


def _rutas_grupo(d) -> list[str]:
    return list(d.get("rutas") or []) if isinstance(d, dict) else list(getattr(d, "rutas", []) or [])


def _sha_grupo(d) -> str:
    return str(d.get("sha256") or "") if isinstance(d, dict) else str(getattr(d, "sha256", "") or "")


def _size_grupo(d) -> int:
    return int(d.get("size_bytes") or 0) if isinstance(d, dict) else int(getattr(d, "size_bytes", 0) or 0)


def _ruta_relativa(ruta: str) -> str:
    try:
        raiz = get_settings().library_path.resolve()
        p = Path(ruta).resolve()
        return p.relative_to(raiz).as_posix()
    except (OSError, ValueError):
        return Path(ruta).name


async def _contexto_duplicados(db: AsyncSession, informe: dict | None) -> dict:
    """Enriquece los grupos de la auditoría para decidir. Solo lee."""
    grupos: list[GrupoDuplicado] = []
    if informe:
        crudos = informe.get("mismo_contenido") or []
        todas = [str(r) for d in crudos for r in _rutas_grupo(d)]
        catalogo = await _filas_catalogo(db, todas)
        for d in crudos:
            rutas = sorted(_rutas_grupo(d))
            sha = _sha_grupo(d)
            size = _size_grupo(d)
            copias = []
            for ruta in rutas:
                p = Path(ruta)
                try:
                    mtime = p.stat().st_mtime
                except OSError:
                    mtime = None
                rel = _ruta_relativa(ruta)
                carpeta = Path(rel).parts[0] if len(Path(rel).parts) > 1 else "Raíz"
                fila = catalogo.get(str(p))
                copias.append(CopiaDuplicado(
                    ruta_rel=rel, carpeta=carpeta, mtime=_texto_fecha(mtime),
                    catalogo=_texto_catalogo(fila), nombre=_pista_nombre(p.name),
                    fila=fila is not None,
                ))
            grupos.append(GrupoDuplicado(sha, size, size * max(0, len(rutas) - 1), copias))
    cuarentena = await asyncio.to_thread(_resumen_cuarentena)
    operaciones = await _operaciones_apartadas(db)
    return {"grupos": grupos, "cuarentena": cuarentena, "operaciones": operaciones}


def _resumen_cuarentena() -> dict:
    base = Path(get_settings().library_path) / ".zascarr" / "apartados"
    archivos = 0
    bytes_ = 0
    try:
        for raiz, _dirs, ficheros in os.walk(base, followlinks=False):
            for nombre in ficheros:
                try:
                    archivos += 1
                    bytes_ += (Path(raiz) / nombre).stat().st_size
                except OSError:
                    continue
    except OSError:
        pass
    return {"ruta": str(base), "archivos": archivos, "bytes": bytes_}


async def _operaciones_apartadas(db: AsyncSession) -> list[dict]:
    try:
        resultado = await db.execute(
            select(ApartadoOperacion)
            .options(selectinload(ApartadoOperacion.grupos))
            .where(ApartadoOperacion.estado == ApartadoEstado.CONFIRMADA)
            .order_by(ApartadoOperacion.creada.desc())
            .limit(10)
        )
        ops = list(resultado.scalars().all())
    except (AttributeError, TypeError):
        return []
    return [{"id": str(op.id), "creada": _texto_fecha(op.creada.timestamp() if op.creada else None),
             "grupos": len(op.grupos or []), "archivos": op.total_archivos,
             "bytes": op.total_bytes} for op in ops]


def _servicio_apartado(db: AsyncSession) -> ApartadoDuplicadosService:
    return ApartadoDuplicadosService(db, secret=get_settings().secret_key)


def _informe_en_dict(informe) -> dict | None:
    if informe is None:
        return None
    return informe if isinstance(informe, dict) else None


async def _contexto_pagina(db: AsyncSession) -> dict:
    informe = await _ultimo_informe(db)
    return {"informe": informe, "duplicados": await _contexto_duplicados(db, informe)}


@router.get("", response_class=HTMLResponse)
async def index(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    return _no_store(templates.TemplateResponse(request, "auditoria.html", await _contexto_pagina(db)))


@router.post("/analizar", response_class=HTMLResponse)
async def analizar(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Relanza el análisis. Solo lectura del disco (ver LibraryAudit)."""
    await LibraryAudit(db).run()
    return _no_store(templates.TemplateResponse(
        request, "_auditoria_informe.html", await _contexto_pagina(db)))


@router.post("/duplicados/previsualizar", response_class=HTMLResponse)
async def previsualizar_duplicados(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Prepara uno o varios grupos elegidos. Valida con el servicio A y NO escribe."""
    informe = await _ultimo_informe(db)
    datos = await request.form()
    seleccion: dict[str, str] = {}
    for clave, valor in datos.multi_items():
        if clave.startswith("keep_"):
            seleccion[clave[5:]] = str(valor)
    crudos = informe.get("mismo_contenido") if informe else []
    servicio = _servicio_apartado(db)
    items = []
    rechazos = []
    if not seleccion:
        return _no_store(templates.TemplateResponse(
            request, "_duplicados_previsualizacion.html",
            {"previsualizacion": {"entradas": [], "bytes": 0, "rechazos": [], "archivos": 0,
                                  "sin_eleccion": True,
                                  "cuarentena": await asyncio.to_thread(_resumen_cuarentena)}}))
    for d in crudos or []:
        sha = _sha_grupo(d)
        if sha not in seleccion:
            continue
        rutas = sorted(_rutas_grupo(d))
        relativas = [_ruta_relativa(r) for r in rutas]
        try:
            keep = relativas.index(seleccion[sha])
        except ValueError:
            rechazos.append({"grupo": sha, "motivo": "La copia elegida ya no está en la lista."})
            continue
        try:
            vista = await servicio.previsualizar(sha, rutas, keep)
        except (ApartadoError, OSError, ValueError) as exc:
            rechazos.append({"grupo": sha, "motivo": str(exc)})
            continue
        relativas = [_ruta_relativa(str(p)) for p in vista.rutas]
        movidas = [r for i, r in enumerate(relativas) if i != vista.keep_index]
        filas = await _filas_catalogo(db, [str(p) for p in vista.rutas])
        if len(filas) > 1:
            cambio = "El catálogo tiene más de una ficha para este grupo: no se podrá apartar hasta resolverlo."
        elif not filas:
            cambio = "Sin cambios en el catálogo: ninguna de estas copias está vinculada."
        elif str(vista.rutas[vista.keep_index]) in filas:
            cambio = "Sin cambios en el catálogo: la copia que se queda ya es la vinculada."
        else:
            cambio = "El catálogo pasará a apuntar a la copia que se queda; conservará su serie y número."
        items.append({
            "token": vista.token, "sha256": sha,
            "grupo_json": json.dumps({"sha256": sha, "rutas": relativas,
                                      "keep_index": vista.keep_index}, ensure_ascii=False),
            "rutas_apartadas": movidas, "bytes": vista.bytes_liberados,
            "catalogo_cambio": cambio,
        })
    contexto = {"previsualizacion": {
        "entradas": items, "bytes": sum(i["bytes"] for i in items), "rechazos": rechazos,
        "archivos": sum(len(i["rutas_apartadas"]) for i in items), "sin_eleccion": False,
        "cuarentena": await asyncio.to_thread(_resumen_cuarentena),
    }}
    return _no_store(templates.TemplateResponse(request, "_duplicados_previsualizacion.html", contexto))


@router.post("/duplicados/confirmar", response_class=HTMLResponse)
async def confirmar_duplicados(request: Request, token: list[str] = Form(default=[]),
                               grupos: list[str] = Form(default=[]),
                               db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Confirma cada grupo previsualizado; un grupo rechazado no tumba los demás."""
    servicio = _servicio_apartado(db)
    resultados = []
    for token_firmado, crudo in zip(token, grupos, strict=False):
        try:
            datos = json.loads(crudo)
            entrada = GrupoEntrada(datos["sha256"], tuple(datos["rutas"]), int(datos["keep_index"]))
            resultados.append(await servicio.confirmar(token_firmado, [entrada]))
        except (ApartadoError, TokenApartadoInvalido, ValueError, KeyError, TypeError) as exc:
            resultados.append({"error": str(exc)})
    contexto = {"resultados": resultados, "operaciones": await _operaciones_apartadas(db),
                "cuarentena": await asyncio.to_thread(_resumen_cuarentena)}
    return _no_store(templates.TemplateResponse(request, "_duplicados_resultado.html", contexto))


@router.post("/duplicados/deshacer", response_class=HTMLResponse)
async def deshacer_duplicados(request: Request, operacion: str = Form(...),
                              db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Deshace una operación confirmada; nunca sobrescribe."""
    servicio = _servicio_apartado(db)
    try:
        resultado = await servicio.deshacer(operacion)
        contexto = {"resultado_deshacer": resultado, "operaciones": await _operaciones_apartadas(db),
                    "cuarentena": await asyncio.to_thread(_resumen_cuarentena)}
    except (ApartadoError, TokenApartadoInvalido, ValueError) as exc:
        contexto = {"error_deshacer": str(exc), "operaciones": await _operaciones_apartadas(db),
                    "cuarentena": await asyncio.to_thread(_resumen_cuarentena)}
    return _no_store(templates.TemplateResponse(request, "_duplicados_resultado.html", contexto))


# ── BL-CNV2b: originales apartados de las conversiones ───────────────────────

#: Tope de originales que se liberan por pulsación (el resto se indica y se repite).
LOTE_LIBERAR = 500


def _servicio_originales(db):
    return ConversionDeArchivo(db, secret=get_settings().secret_key)


async def _contexto_originales(db, *, borrados: int | None = None,
                               error: str | None = None) -> dict:
    servicio = _servicio_originales(db)
    cuantos, bytes_ = await servicio.resumen_originales()
    return {"originales": cuantos, "bytes": bytes_, "borrados": borrados,
            "error": error, "lote": LOTE_LIBERAR}


@router.get("/originales", response_class=HTMLResponse)
async def originales(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Fragmento «Originales guardados»: dónde están, cuánto ocupan y liberar. Solo lee."""
    respuesta = templates.TemplateResponse(
        request, "_originales_guardados.html", await _contexto_originales(db))
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.post("/originales/vaciar", response_class=HTMLResponse)
async def originales_vaciar(request: Request, confirmado: str = Form(""),
                            db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Borra originales por tandas. Sin la casilla marcada no se toca nada."""
    if confirmado not in ("1", "true", "on"):
        contexto = await _contexto_originales(
            db, error="Marca la casilla para confirmar que no necesitas deshacer esas conversiones.")
    else:
        borrados = await _servicio_originales(db).vaciar_originales(LOTE_LIBERAR)
        contexto = await _contexto_originales(db, borrados=borrados)
        if borrados == 0 and contexto["originales"]:
            contexto["error"] = ("No se ha liberado nada ahora mismo: hay otra tarea usando la "
                                 "biblioteca. Inténtalo en un momento.")
    respuesta = templates.TemplateResponse(request, "_originales_guardados.html", contexto)
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta
