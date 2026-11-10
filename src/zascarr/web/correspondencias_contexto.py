# ruff: noqa: E501
"""MIT-M7 131-b: correspondencias locales y propuestas (solo UI)."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.models import (
    CorrespondenciaContexto,
    DeclaracionCarpeta,
    EstadoRegla,
    Issue,
    Series,
    TipoDestino,
)
from zascarr.services import correspondencias_contexto as svc
from zascarr.services.declaraciones_carpeta import normalizar_ruta
from zascarr.web.routes import crear_templates

router = APIRouter(prefix="/ui/pendientes/carpetas", tags=["ui"])
templates = crear_templates()

MSG_EFECTOS = ("Solo prepara propuestas. No crea series ni publicaciones, no vincula archivos, "
               "no los mueve ni aplica metadatos. La confirmación de una propuesta es otro paso.")
MSG_LISTA = "Solo preparan propuestas; no vinculan archivos ni aplican metadatos."


def _respuesta(request: Request, plantilla: str, contexto: dict, *,
               status_code: int = 200) -> HTMLResponse:
    resp = templates.TemplateResponse(request, plantilla, contexto, status_code=status_code)
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _redir(url: str) -> RedirectResponse:
    resp = RedirectResponse(url, status_code=303)
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _error(request: Request, mensaje: str) -> HTMLResponse:
    return _respuesta(request, "correspondencia_error.html",
                      {"mensaje": mensaje, "volver": "/ui/pendientes/carpetas/contexto"})


def _url_lista() -> str:
    return "/ui/pendientes/carpetas/correspondencias"


def _url_crear(declaracion_id: UUID) -> str:
    return f"{_url_lista()}/crear?declaracion={declaracion_id}"


@dataclass(frozen=True)
class DestinoVista:
    tipo: TipoDestino
    id: UUID
    texto: str
    url: str


async def _destinos_por_id(db: AsyncSession, ids: set[UUID]) -> dict[UUID, DestinoVista]:
    if not ids:
        return {}
    series = {s.id: s for s in (await db.execute(select(Series).where(Series.id.in_(ids)))).scalars().all()}
    issues = {i.id: i for i in (await db.execute(select(Issue).where(Issue.id.in_(ids)))).scalars().all()}
    series_ids = {i.series_id for i in issues.values()}
    series_de_issue = {s.id: s for s in (await db.execute(select(Series).where(Series.id.in_(series_ids)))).scalars().all()}
    salida: dict[UUID, DestinoVista] = {}
    for sid, s in series.items():
        salida[sid] = DestinoVista(TipoDestino.SERIE, sid, f"Serie «{s.title}»" + (f" ({s.start_year})" if s.start_year else ""), f"/ui/series/{sid}")
    for iid, i in issues.items():
        s = series_de_issue.get(i.series_id)
        titulo = f" · «{i.title}»" if i.title else ""
        salida[iid] = DestinoVista(TipoDestino.PUBLICACION, iid,
                                   f"Publicación «{s.title if s else ''}» · Número {i.issue_number}{titulo}",
                                   f"/ui/series/{i.series_id}/numero/{iid}" if s else "")
    return salida


async def _declaraciones(db: AsyncSession) -> tuple[dict[UUID, DeclaracionCarpeta], dict[UUID, DeclaracionCarpeta]]:
    filas = (await db.execute(select(DeclaracionCarpeta))).scalars().all()
    por_id = {f.id: f for f in filas}
    vigente_por_estable = {f.declaracion_id: f for f in filas if f.vigente_hasta is None}
    return por_id, vigente_por_estable


def _correspondencia_vm(c: CorrespondenciaContexto, decl: DeclaracionCarpeta | None,
                        vigente: DeclaracionCarpeta | None,
                        destino: DestinoVista | None) -> dict:
    desactualizada = (decl is None or vigente is None or vigente.id != decl.id
                      or vigente.estado is not EstadoRegla.ACTIVA)
    return {
        "c": c, "destino": destino, "decl": decl, "desactualizada": desactualizada,
        "sin_destino": destino is None,
        "alcance": ("Esta carpeta y sus subcarpetas" if c.incluir_descendientes
                    else "Solo esta carpeta"),
        "registro": {None: "Cualquier registro", "archivo": "Archivos",
                     "serie": "Series", "publicacion": "Publicaciones"}.get(
                         c.tipo_de_registro.value if c.tipo_de_registro else None),
    }


@router.get("/correspondencias", response_class=HTMLResponse)
async def lista(request: Request, aviso: str = Query(default=""),
                db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        filas = await svc.listar(db)
        por_id, vigentes = await _declaraciones(db)
        destinos = await _destinos_por_id(
            db, {c.destino_id for c in filas})
    except Exception as exc:  # noqa: BLE001
        return _error(request, f"No se han podido leer las correspondencias. Vuelve a intentarlo. ({type(exc).__name__})")
    tarjetas = [_correspondencia_vm(c, por_id.get(c.declaracion_version_id),
                                    vigentes.get(por_id.get(c.declaracion_version_id).declaracion_id
                                                  if por_id.get(c.declaracion_version_id) else None),
                                    destinos.get(c.destino_id))
                for c in filas]
    secciones = [(estado, [t for t in tarjetas if t["c"].estado.value == estado])
                 for estado in ("activa", "desactivada", "retirada")]
    # conflicto visible por raíz entre activas locales
    activas_por_raiz: dict[str, int] = {}
    for t in tarjetas:
        if t["c"].estado is EstadoRegla.ACTIVA and not t["desactualizada"]:
            activas_por_raiz[t["c"].contexto_raiz] = activas_por_raiz.get(t["c"].contexto_raiz, 0) + 1
    return _respuesta(request, "correspondencias.html", {
        "secciones": secciones, "todas": tarjetas, "aviso": aviso,
        "volver": "/ui/pendientes/carpetas/contexto", "mensaje_efectos": MSG_LISTA,
        "conflicto": any(n > 1 for n in activas_por_raiz.values()),
        "url_lista": _url_lista()})


async def _hay_correspondencia_activa(db: AsyncSession, raiz: str) -> bool:
    filas = await svc.listar(db)
    return any(c.contexto_raiz == raiz and c.estado is EstadoRegla.ACTIVA for c in filas)


async def _declaracion_activa(db: AsyncSession, declaracion_id: UUID) -> DeclaracionCarpeta | None:
    fila = await db.get(DeclaracionCarpeta, declaracion_id)
    if fila is None or fila.estado is not EstadoRegla.ACTIVA:
        return None
    return fila


@router.get("/correspondencias/crear", response_class=HTMLResponse)
async def crear_form(request: Request, declaracion: UUID, tipo: str = Query(default=""),
                     q: str = Query(default=""), tipo_registro: str = Query(default=""),
                     db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    decl = await _declaracion_activa(db, declaracion)
    if decl is None:
        return _error(request, "Esta declaración ya no está activa; no se puede usar para una correspondencia.")
    if decl.tipo_de_significado.value == "autor":
        return _error(request, "Una carpeta por autor solo orienta; no puede tener un destino único.")
    resultados: list[DestinoVista] = []
    if tipo in ("serie", "publicacion") and q.strip():
        resultados = await _buscar(db, tipo, q.strip())
    return _respuesta(request, "crear_correspondencia.html", {
        "decl": decl, "tipo": tipo, "q": q, "tipo_registro": tipo_registro,
        "resultados": resultados, "mensaje_efectos": MSG_EFECTOS,
        "alcance": "Esta carpeta y sus subcarpetas" if decl.incluir_descendientes else "Solo esta carpeta",
        "aviso_conflicto": await _hay_correspondencia_activa(db, decl.contexto_raiz),
        "error": "", "url_lista": _url_lista(), "url_crear": _url_crear(decl.id)})


async def _buscar(db: AsyncSession, tipo: str, q: str) -> list[DestinoVista]:
    patron = f"%{q}%"
    if tipo == "serie":
        filas = (await db.execute(select(Series).where(
            or_(Series.title.ilike(patron), Series.sort_title.ilike(patron))).limit(20))).scalars().all()
        return [DestinoVista(TipoDestino.SERIE, s.id,
                             f"Serie «{s.title}»" + (f" ({s.start_year})" if s.start_year else ""),
                             f"/ui/series/{s.id}") for s in filas]
    filas = (await db.execute(
        select(Issue, Series).join(Series, Issue.series_id == Series.id)
        .where(or_(Series.title.ilike(patron), Issue.title.ilike(patron),
                   Issue.issue_number.ilike(patron))).limit(20))).all()
    return [DestinoVista(TipoDestino.PUBLICACION, i.id,
                         f"Publicación «{s.title}» · Número {i.issue_number}"
                         + (f" · «{i.title}»" if i.title else ""),
                         f"/ui/series/{s.id}/numero/{i.id}") for i, s in filas]


@router.post("/correspondencias/crear", response_class=HTMLResponse)
async def crear_post(request: Request, declaracion: UUID = Form(...),
                     tipo: str = Form(default=""), destino_id: str = Form(default=""),
                     tipo_registro: str = Form(default=""),
                     confirmado: str = Form(default="0"),
                     db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    decl = await _declaracion_activa(db, declaracion)
    if decl is None:
        return _error(request, "Esta declaración ya no está activa; no se puede usar para una correspondencia.")
    if decl.tipo_de_significado.value == "autor":
        return _error(request, "Una carpeta por autor solo orienta; no puede tener un destino único.")
    if tipo not in ("serie", "publicacion"):
        return _respuesta(request, "crear_correspondencia.html", {
            "decl": decl, "tipo": tipo, "q": "", "tipo_registro": tipo_registro,
            "resultados": [], "mensaje_efectos": MSG_EFECTOS,
            "alcance": "Esta carpeta y sus subcarpetas" if decl.incluir_descendientes else "Solo esta carpeta",
            "error": "Elige si el destino es una serie o una publicación.", "url_lista": _url_lista(), "aviso_conflicto": await _hay_correspondencia_activa(db, decl.contexto_raiz),
            "url_crear": _url_crear(decl.id)})
    if not destino_id:
        return _respuesta(request, "crear_correspondencia.html", {
            "decl": decl, "tipo": tipo, "q": "", "tipo_registro": tipo_registro,
            "resultados": [],
            "mensaje_efectos": MSG_EFECTOS,
            "alcance": "Esta carpeta y sus subcarpetas" if decl.incluir_descendientes else "Solo esta carpeta",
            "error": "Elige una serie o publicación de la lista.", "url_lista": _url_lista(), "aviso_conflicto": await _hay_correspondencia_activa(db, decl.contexto_raiz),
            "url_crear": _url_crear(decl.id)})
    try:
        did = UUID(destino_id)
    except (ValueError, TypeError):
        return _error(request, "El destino elegido ya no existe. Elige otra serie o publicación.")
    destino = (await _destinos_por_id(db, {did})).get(did)
    if destino is None:
        return _error(request, "El destino elegido ya no existe. Elige otra serie o publicación.")
    if confirmado != "1":
        return _respuesta(request, "confirmar_correspondencia.html", {
            "decl": decl, "tipo": tipo, "destino": destino, "tipo_registro": tipo_registro,
            "alcance": "Esta carpeta y sus subcarpetas" if decl.incluir_descendientes else "Solo esta carpeta",
            "mensaje_efectos": MSG_EFECTOS, "volver_url": _url_crear(decl.id),
            "url_lista": _url_lista()})
    try:
        await svc.crear(db, decl.id, destino_tipo=tipo, destino_id=did,
                        tipo_de_registro=tipo_registro or None)
    except svc.CorrespondenciaError as exc:
        return _respuesta(request, "crear_correspondencia.html", {
            "decl": decl, "tipo": tipo, "q": "", "tipo_registro": tipo_registro,
            "resultados": [], "mensaje_efectos": MSG_EFECTOS,
            "alcance": "Esta carpeta y sus subcarpetas" if decl.incluir_descendientes else "Solo esta carpeta",
            "error": str(exc) if "destino" in str(exc).lower() else "No se ha podido crear la correspondencia. No se ha cambiado nada. Vuelve a intentarlo.",
            "url_lista": _url_lista(), "url_crear": _url_crear(decl.id)})
    return _redir(f"{_url_lista()}?aviso=creada")


@router.get("/correspondencias/cambiar/{correspondencia_id}", response_class=HTMLResponse)
async def cambiar_form(request: Request, correspondencia_id: UUID,
                       tipo: str = Query(default=""), q: str = Query(default=""),
                       db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    actual = await _actual(db, correspondencia_id)
    if actual is None:
        return _error(request, "Esa correspondencia ya no existe. Vuelve a «Correspondencias».")
    if actual.estado is EstadoRegla.RETIRADA:
        return _respuesta(request, "correspondencia_error.html", {
            "mensaje": "Una correspondencia retirada no se puede cambiar.",
            "volver": _url_lista()}, status_code=409)
    destino = (await _destinos_por_id(db, {actual.destino_id})).get(actual.destino_id)
    resultados = await _buscar(db, tipo, q.strip()) if tipo in ("serie", "publicacion") and q.strip() else []
    return _respuesta(request, "cambiar_correspondencia.html", {
        "c": actual, "destino": destino, "error": "", "tipo": tipo, "q": q,
        "resultados": resultados,
        "mensaje_efectos": MSG_EFECTOS, "url_lista": _url_lista()})


@router.post("/correspondencias/cambiar/{correspondencia_id}", response_class=HTMLResponse)
async def cambiar_post(request: Request, correspondencia_id: UUID,
                       destino: str = Form(default=""),
                       destino_tipo: str = Form(default=""),
                       destino_id: str = Form(default=""),
                       tipo_registro: str = Form(default=""),
                       confirmado: str = Form(default="0"),
                       db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    actual = await _actual(db, correspondencia_id)
    if actual is None:
        return _error(request, "Esa correspondencia ya no existe. Vuelve a «Correspondencias».")
    if actual.estado is EstadoRegla.RETIRADA:
        return _respuesta(request, "correspondencia_error.html", {
            "mensaje": "Una correspondencia retirada no se puede cambiar.",
            "volver": _url_lista()}, status_code=409)
    if destino:
        try:
            tipo, _, raw_id = destino.partition("|")
            did = UUID(raw_id)
        except (ValueError, TypeError):
            return _error(request, "El destino elegido ya no existe. Elige otra serie o publicación.")
    else:
        tipo = destino_tipo or actual.destino_tipo.value
        try:
            did = UUID(destino_id) if destino_id else actual.destino_id
        except (ValueError, TypeError):
            return _error(request, "El destino elegido ya no existe. Elige otra serie o publicación.")
    tipo_reg = tipo_registro or None
    cambia_destino = tipo != actual.destino_tipo.value or did != actual.destino_id
    if cambia_destino and confirmado != "1":
        nuevo = (await _destinos_por_id(db, {did})).get(did)
        if nuevo is None:
            return _error(request, "El destino elegido ya no existe. Elige otra serie o publicación.")
        return _respuesta(request, "confirmar_cambio_correspondencia.html", {
            "c": actual, "destino": nuevo, "tipo": tipo,
            "tipo_registro": tipo_registro, "url_lista": _url_lista(),
            "mensaje_efectos": MSG_EFECTOS})
    sin_cambio = (not cambia_destino
                  and (tipo_reg is None and actual.tipo_de_registro is None
                       or tipo_reg == (actual.tipo_de_registro.value if actual.tipo_de_registro else None)))
    if sin_cambio:
        destino_vm = (await _destinos_por_id(db, {actual.destino_id})).get(actual.destino_id)
        return _respuesta(request, "cambiar_correspondencia.html", {
            "c": actual, "destino": destino_vm, "error": "No has cambiado nada.",
            "tipo": actual.destino_tipo.value, "q": "", "resultados": [],
            "mensaje_efectos": MSG_EFECTOS, "url_lista": _url_lista()})
    try:
        actualizada = await svc.cambiar(db, correspondencia_id, destino_tipo=tipo,
                                        destino_id=did, tipo_de_registro=(
                                            tipo_reg if tipo_reg is not None else None))
    except svc.CorrespondenciaError as exc:
        destino_vm = (await _destinos_por_id(db, {actual.destino_id})).get(actual.destino_id)
        return _respuesta(request, "cambiar_correspondencia.html", {
            "c": actual, "destino": destino_vm, "error": str(exc),
            "tipo": tipo, "q": "", "resultados": [],
            "mensaje_efectos": MSG_EFECTOS, "url_lista": _url_lista()})
    if actualizada.version == actual.version:
        destino_vm = (await _destinos_por_id(db, {actual.destino_id})).get(actual.destino_id)
        return _respuesta(request, "cambiar_correspondencia.html", {
            "c": actual, "destino": destino_vm, "error": "No has cambiado nada.",
            "tipo": actual.destino_tipo.value, "q": "", "resultados": [],
            "mensaje_efectos": MSG_EFECTOS, "url_lista": _url_lista()})
    return _redir(f"{_url_lista()}?aviso=actualizada")


@router.post("/correspondencias/desactivar/{correspondencia_id}", response_class=HTMLResponse)
async def desactivar(request: Request, correspondencia_id: UUID,
                     db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    actual = await _actual(db, correspondencia_id)
    if actual is None:
        return _error(request, "Esa correspondencia ya no existe. Vuelve a «Correspondencias».")
    if actual.estado is EstadoRegla.RETIRADA:
        return _respuesta(request, "correspondencia_error.html", {
            "mensaje": "Una correspondencia retirada no se puede desactivar.",
            "volver": _url_lista()}, status_code=409)
    await svc.desactivar(db, correspondencia_id)
    return _redir(f"{_url_lista()}?aviso=desactivada")


@router.post("/correspondencias/reactivar/{correspondencia_id}", response_class=HTMLResponse)
async def reactivar(request: Request, correspondencia_id: UUID,
                    db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    actual = await _actual(db, correspondencia_id)
    if actual is None:
        return _error(request, "Esa correspondencia ya no existe. Vuelve a «Correspondencias».")
    if actual.estado is EstadoRegla.RETIRADA:
        return _respuesta(request, "correspondencia_error.html", {
            "mensaje": "Una correspondencia retirada no se puede reactivar.",
            "volver": _url_lista()}, status_code=409)
    try:
        await svc.activar(db, correspondencia_id)
    except svc.CorrespondenciaRetiradaError:
        return _respuesta(request, "correspondencia_error.html", {
            "mensaje": "Una correspondencia retirada no se puede reactivar.",
            "volver": _url_lista()}, status_code=409)
    except svc.CorrespondenciaError:
        return _respuesta(request, "correspondencia_error.html", {
            "mensaje": "La declaración ya no está activa; no se puede reactivar esta correspondencia.",
            "volver": _url_lista()}, status_code=409)
    return _redir(f"{_url_lista()}?aviso=reactivada")


@router.get("/correspondencias/retirar/{correspondencia_id}", response_class=HTMLResponse)
async def retirar_form(request: Request, correspondencia_id: UUID,
                       db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    actual = await _actual(db, correspondencia_id)
    if actual is None:
        return _error(request, "Esa correspondencia ya no existe. Vuelve a «Correspondencias».")
    if actual.estado is EstadoRegla.RETIRADA:
        return _respuesta(request, "correspondencia_error.html", {
            "mensaje": "Una correspondencia retirada no se puede retirar otra vez.",
            "volver": _url_lista()}, status_code=409)
    destino = (await _destinos_por_id(db, {actual.destino_id})).get(actual.destino_id)
    return _respuesta(request, "retirar_correspondencia.html", {
        "c": actual, "destino": destino, "url_lista": _url_lista()})


@router.post("/correspondencias/retirar/{correspondencia_id}", response_class=HTMLResponse)
async def retirar_post(request: Request, correspondencia_id: UUID,
                       db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    if await _actual(db, correspondencia_id) is None:
        return _error(request, "Esa correspondencia ya no existe. Vuelve a «Correspondencias».")
    await svc.retirar(db, correspondencia_id)
    return _redir(f"{_url_lista()}?aviso=retirada")


async def _actual(db: AsyncSession, correspondencia_id: UUID):
    filas = await svc.listar(db, incluir_historial=True)
    return next((c for c in filas if c.correspondencia_id == correspondencia_id
                 and c.vigente_hasta is None), None)


@router.get("/contexto/propuesta", response_class=HTMLResponse)
async def propuesta(request: Request, clave: str = Query(default=""),
                    db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    if not clave.strip():
        return _error(request, "No sabemos qué carpeta quieres consultar. Vuelve a «Pendientes por carpeta».")
    try:
        ruta = normalizar_ruta(clave)
        resultado = await svc.evaluar(db, svc.RegistroContextual(tipo="archivo", carpeta=ruta))
    except svc.CorrespondenciaError as exc:
        return _error(request, str(exc))
    destino = None
    reglas = []
    if resultado.destino_id is not None and resultado.destino_tipo is not None:
        destino = (await _destinos_por_id(db, {resultado.destino_id})).get(resultado.destino_id)
    for regla in resultado.reglas_involucradas:
        rid = UUID(regla["destino_id"]) if regla.get("destino_id") else None
        reglas.append({**regla, "destino": (await _destinos_por_id(db, {rid})).get(rid) if rid else None})
    return _respuesta(request, "propuesta_contexto.html", {
        "resultado": resultado, "ruta": ruta, "destino": destino, "reglas": reglas,
        "volver": "/ui/pendientes/carpetas", "url_lista": _url_lista()})
