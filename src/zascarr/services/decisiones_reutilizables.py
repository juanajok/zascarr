"""MIT-M7-US03 (#132-b): inventario de decisiones reutilizables (SOLO lectura).

Une las cuatro fuentes —declaraciones de carpeta, correspondencias, alias
aprendidos y alias importados— con tipo, origen, estado, alcance, versión,
efectos, precedencia y conflictos visibles. No decide precedencias: las pinta.

Las acciones de ciclo viven en los servicios de cada fuente (`declaraciones_carpeta`,
`correspondencias_contexto`, `alias_decisiones`); este módulo no escribe.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import EstadoAlias, EstadoRegla, OrigenRegla, Series
from zascarr.services import alias_decisiones as alias_svc
from zascarr.services import correspondencias_contexto as corr_svc
from zascarr.services import declaraciones_carpeta as decl_svc

LIMITE_MAXIMO = 500

TIPOS = ("declaracion", "correspondencia", "alias_aprendido", "alias_importado")
TIPO_ES = {
    "declaracion": "Declaración de carpeta",
    "correspondencia": "Correspondencia",
    "alias_aprendido": "Alias aprendido",
    "alias_importado": "Alias importado",
}
ESTADO_ES = {
    "activa": "Activa", "desactivada": "Desactivada", "retirada": "Retirada",
    "propuesto": "Pendiente de activar", "activo": "Activo",
    "desactivado": "Desactivado", "retirado": "Retirado",
}
ORIGEN_ES = {"local": "Local", "importacion": "Importación",
             "importado": "Importación", "aprendido": "Aprendido", "manual": "Manual"}
ORDEN_ESTADO = {"activa": 0, "activo": 0, "propuesto": 1, "desactivada": 2,
                "desactivado": 2, "retirada": 3, "retirado": 3}


@dataclass(frozen=True)
class Decision:
    tipo: str
    id: UUID
    fila_id: UUID
    origen: str
    estado: str
    version: int
    contexto: str
    alcance: str
    destino: str
    efectos: str
    precedencia: str
    conflictos: tuple[str, ...] = ()
    historial: tuple[dict, ...] = ()
    acciones: tuple[str, ...] = ()
    es_importada: bool = False

    @property
    def tipo_es(self) -> str:
        return TIPO_ES[self.tipo]

    @property
    def origen_es(self) -> str:
        return ORIGEN_ES.get(self.origen, self.origen)

    @property
    def estado_es(self) -> str:
        return ESTADO_ES.get(self.estado, self.estado)


def _normalizar(texto: str) -> str:
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", texto)
                         if not unicodedata.combining(c))
    return " ".join(sin_tildes.casefold().split())


def _destino_serie(series: dict[UUID, str], destino_id: UUID) -> str:
    return series.get(destino_id) or "Serie no encontrada"


def _efectos_aprendido(estado: EstadoAlias) -> str:
    if estado is EstadoAlias.ACTIVO:
        return ("Se aplica a nuevas interpretaciones del matcher, si no lo bloquea una "
                "decisión local; no cambia lo ya decidido.")
    if estado is EstadoAlias.PROPUESTO:
        return "No se aplica hasta que lo actives."
    return "No se aplica."


def _efectos_importado(estado: EstadoAlias) -> str:
    if estado is EstadoAlias.ACTIVO:
        return ("Sugerencia importada activa: subordinada a la declaración local. "
                "No se aplica automáticamente en esta entrega.")
    if estado is EstadoAlias.PROPUESTO:
        return "Sugerencia importada pendiente de activar; no se aplica."
    return "No se aplica."


def _acciones_alias(estado: EstadoAlias, *, importado: bool) -> tuple[str, ...]:
    if estado is EstadoAlias.RETIRADO:
        return ()
    if estado is EstadoAlias.PROPUESTO:
        return ("activar", "retirar")
    if estado is EstadoAlias.ACTIVO:
        return ("desactivar", "retirar")
    return ("reactivar", "retirar")


def _precedencia(tipo: str, origen: str) -> str:
    if tipo in ("declaracion", "correspondencia"):
        return ("Capa 1 · manda sobre alias. Solo orienta: no vincula ni crea nada."
                if origen == "local"
                else "Importación: se muestra; no se gestiona desde aquí.")
    if tipo == "alias_importado":
        return "Capa 2 · subordinado a las decisiones locales; no las pisa."
    return "Capa 3 · no pisa decisiones locales ni alias importados."


async def _series_por_id(db: AsyncSession, ids: set[UUID]) -> dict[UUID, str]:
    if not ids:
        return {}
    filas = (await db.execute(
        select(Series.id, Series.title).where(Series.id.in_(list(ids)))
    )).all()
    return {f.id: f.title for f in filas}


def _texto_busqueda(d: Decision) -> str:
    return _normalizar(" ".join((d.contexto, d.alcance, d.destino, d.tipo_es)))


async def listar_decisiones(
        db: AsyncSession, *, tipo: str = "", estado: str = "", origen: str = "",
        carpeta: str = "", incluir_historial: bool = False,
) -> list[Decision]:
    """Las cuatro fuentes, en orden de precedencia y estado. Cuatro consultas fijas."""
    declaraciones = await decl_svc.listar(db, incluir_historial=incluir_historial)
    correspondencias = await corr_svc.listar(db, incluir_historial=incluir_historial)
    aprendidos = await alias_svc.listar_aprendidos(db, incluir_historial=incluir_historial)
    importados = await alias_svc.listar_importados(db, incluir_historial=incluir_historial)

    series = await _series_por_id(db, {
        c.destino_id for c in correspondencias if c.destino_tipo.value == "serie"
    } | {a.series_id for a in aprendidos} | {a.series_id for a in importados})

    # Decisiones locales activas, para marcar los alias globales (capa 3) que quedan
    # bajo su paraguas sin inventar una resolución.
    raices_locales = {
        _normalizar(d.contexto_raiz) for d in declaraciones
        if d.origen is OrigenRegla.LOCAL and d.estado is EstadoRegla.ACTIVA
    }
    raices_correspondencia = {
        _normalizar(c.contexto_raiz) for c in correspondencias
        if c.origen is OrigenRegla.LOCAL and c.estado is EstadoRegla.ACTIVA
    }
    locales_activas = bool(raices_locales or raices_correspondencia)

    importados_activos = [
        a for a in importados if a.estado is EstadoAlias.ACTIVO
    ]
    aprendidos_activos = [
        a for a in aprendidos if a.estado is EstadoAlias.ACTIVO
    ]

    filas: list[Decision] = []

    for d in declaraciones:
        local = d.origen is OrigenRegla.LOCAL
        activa = d.estado is EstadoRegla.ACTIVA
        conflictos: list[str] = []
        misma_raiz = [x for x in declaraciones
                      if x.declaracion_id != d.declaracion_id
                      and _normalizar(x.contexto_raiz) == _normalizar(d.contexto_raiz)]
        if misma_raiz:
            conflictos.append("Otra declaración para la misma carpeta: se muestran las dos, "
                              "no se elige aquí.")
        acciones: tuple[str, ...] = ()
        if local:
            if activa:
                acciones = ("cambiar", "desactivar", "retirar")
            elif d.estado is EstadoRegla.DESACTIVADA:
                acciones = ("reactivar", "retirar")
        filas.append(Decision(
            tipo="declaracion", id=d.declaracion_id, fila_id=d.id,
            origen=d.origen.value, estado=d.estado.value, version=d.version,
            contexto=d.contexto_raiz,
            alcance=f"{d.contexto_raiz} — {d.alcance.lower()}",
            destino="—",
            efectos=d.efectos + " No aplica retroactivamente.",
            precedencia=_precedencia("declaracion", d.origen.value),
            conflictos=tuple(conflictos), acciones=acciones,
            es_importada=not local,
        ))

    for c in correspondencias:
        local = c.origen is OrigenRegla.LOCAL
        activa = c.estado is EstadoRegla.ACTIVA
        conflictos = []
        mismo_destino = [x for x in correspondencias
                         if x.correspondencia_id != c.correspondencia_id
                         and _normalizar(x.contexto_raiz) == _normalizar(c.contexto_raiz)
                         and x.destino_id != c.destino_id
                         and x.estado is EstadoRegla.ACTIVA]
        if mismo_destino:
            conflictos.append("Otras correspondencias activas para la misma carpeta; "
                              "no se elige aquí.")
        acciones = ()
        if local:
            if activa:
                acciones = ("desactivar", "retirar")
            elif c.estado is EstadoRegla.DESACTIVADA:
                acciones = ("reactivar", "retirar")
        tipo_reg = " · solo archivos" if c.tipo_de_registro is not None else ""
        destino = ("Serie: " + _destino_serie(series, c.destino_id)
                   if c.destino_tipo.value == "serie" else "Publicación")
        filas.append(Decision(
            tipo="correspondencia", id=c.correspondencia_id, fila_id=c.id,
            origen=c.origen.value, estado=c.estado.value, version=c.version,
            contexto=c.contexto_raiz,
            alcance=(f"{c.contexto_raiz} — " +
                     ("esta carpeta y subcarpetas" if c.incluir_descendientes
                      else "solo esta carpeta") + tipo_reg),
            destino=destino,
            efectos="Solo prepara propuestas; no vincula ni aplica metadatos.",
            precedencia=_precedencia("correspondencia", c.origen.value),
            conflictos=tuple(conflictos), acciones=acciones,
            es_importada=not local,
        ))

    for a in aprendidos:
        conflictos = []
        if locales_activas:
            conflictos.append("Hay decisiones locales activas que mandan sobre este alias "
                              "(es global). No se elige aquí.")
        if any(i.patron_norm == a.pattern_norm for i in importados_activos):
            conflictos.append("Un alias importado activo usa el mismo patrón; "
                              "la capa 2 va por delante.")
        filas.append(Decision(
            tipo="alias_aprendido", id=a.id, fila_id=a.id,
            origen=a.origen.value, estado=a.estado.value, version=a.version,
            contexto="Global (sin carpeta)",
            alcance=f"Global — patrón «{a.pattern_norm}»",
            destino=_destino_serie(series, a.series_id),
            efectos=_efectos_aprendido(a.estado),
            precedencia=_precedencia("alias_aprendido", a.origen.value),
            conflictos=tuple(conflictos),
            historial=tuple(a.historial or ()),
            acciones=_acciones_alias(a.estado, importado=False),
        ))

    for a in importados:
        conflictos = []
        ambito = _normalizar(a.scope_path) if a.scope_path else ""
        if ambito and (ambito in raices_locales or ambito in raices_correspondencia):
            conflictos.append("Hay una decisión local para esa carpeta: la local tiene "
                              "prioridad; el alias no se borra.")
        if any(x.pattern_norm == a.patron_norm for x in aprendidos_activos):
            conflictos.append("Un alias aprendido activo usa el mismo patrón; "
                              "la capa 3 queda por debajo.")
        filas.append(Decision(
            tipo="alias_importado", id=a.alias_id, fila_id=a.id,
            origen="importacion", estado=a.estado.value, version=a.version,
            contexto=a.scope_path or "Global",
            alcance=(f"{a.scope_path} y subcarpetas" if a.scope_path else "Global"),
            destino=_destino_serie(series, a.series_id),
            efectos=_efectos_importado(a.estado),
            precedencia=_precedencia("alias_importado", a.origen.value),
            conflictos=tuple(conflictos),
            acciones=_acciones_alias(a.estado, importado=True),
            es_importada=True,
        ))

    # Filtros (combinables; un valor inválido no rompe: simplemente no filtra).
    if tipo in TIPOS:
        filas = [f for f in filas if f.tipo == tipo]
    if estado:
        filas = [f for f in filas if f.estado == estado]
    if origen:
        filas = [f for f in filas if f.origen == origen]
    if carpeta.strip():
        buscado = _normalizar(carpeta)
        filas = [f for f in filas if buscado in _texto_busqueda(f)]
    filas.sort(key=lambda f: (ORDEN_ESTADO.get(f.estado, 9), TIPOS.index(f.tipo),
                              _normalizar(f.contexto)))
    return filas[:LIMITE_MAXIMO]
