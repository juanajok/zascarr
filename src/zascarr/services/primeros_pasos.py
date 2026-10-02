"""
Primeros pasos del Inicio (V4): una función PURA que convierte el estado observado en pasos.

Reglas que se miden contra el coleccionista, no contra el desarrollador:

- **Nada se marca a mano**: cada estado sale de un hecho observado (la adopción se ejecutó, hay N
  archivos sin clasificar, hay una fuente activa...). Sin hecho, no hay «hecho».
- **Auditoría ≠ adopción.** El informe de duplicados acredita que alguien MIRÓ el disco en una
  fecha; no que la biblioteca esté registrada. Son estados distintos con fuente distinta
  (`InformeDisco` frente a `EstadoAdopcion`) y ninguno implica al otro.
- **Cada cifra dice de dónde sale** («comparados a fondo el 3 de octubre», «registrados»); nunca se
  afirma un escaneo del disco que no ocurrió.
- **Una sola acción principal**: el primer paso `SIGUIENTE` o, si no queda ninguno obligatorio, el
  primer paso opcional por hacer.

Esta función no toca la BD ni el disco: `services/inicio.py` reúne el estado y se lo pasa.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from zascarr.services.library_adopter import EstadoAdopcion

MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre")


def fecha_llana(fecha: datetime) -> str:
    """«3 de octubre de 2026»: sin locale del sistema (la Pi puede no tener es_ES)."""
    local = fecha.astimezone() if fecha.tzinfo else fecha
    return f"{local.day} de {MESES[local.month - 1]} de {local.year}"


class EstadoPaso(StrEnum):
    HECHO = "hecho"
    SIGUIENTE = "siguiente"      # el que toca ahora (obligatorio)
    PENDIENTE = "pendiente"      # obligatorio, pero hay otro antes
    OPCIONAL = "opcional"        # se puede saltar
    BLOQUEADO = "bloqueado"      # hoy no se puede hacer (se explica por qué)


class ClavePaso(StrEnum):
    BIBLIOTECA = "biblioteca"
    REVISAR = "revisar"
    SERIES = "series"
    DESCARGAS = "descargas"


@dataclass(frozen=True)
class InformeDisco:
    """Último informe de duplicados guardado (`ImportRun`, `details.kind == "audit"`)."""
    fecha: datetime
    archivos_leidos: int
    archivos_comparados: int


@dataclass(frozen=True)
class EstadoInicio:
    """Lo observado. Cada campo tiene una única fuente; ver `services/inicio.py`."""
    adopcion: EstadoAdopcion
    archivos_registrados: int
    archivos_sin_clasificar: int
    series_seguidas: int
    informe: InformeDisco | None
    aviso_legal_aceptado: bool
    hay_fuente_de_busqueda: bool


@dataclass(frozen=True)
class Paso:
    clave: ClavePaso
    titulo: str
    detalle: str
    estado: EstadoPaso
    obligatorio: bool
    enlace: str | None = None
    accion: str | None = None


@dataclass(frozen=True)
class PrimerosPasos:
    pasos: tuple[Paso, ...]
    principal: Paso | None

    @property
    def hechos(self) -> int:
        return sum(1 for p in self.pasos if p.estado is EstadoPaso.HECHO)

    @property
    def total(self) -> int:
        return len(self.pasos)

    @property
    def completo(self) -> bool:
        """Todo lo obligatorio está hecho (puede quedar algo opcional)."""
        return all(p.estado is EstadoPaso.HECHO for p in self.pasos if p.obligatorio)


def _plural(n: int, uno: str, varios: str) -> str:
    return uno if n == 1 else varios


def _paso_biblioteca(e: EstadoInicio) -> Paso | None:
    informe = e.informe
    if e.adopcion is EstadoAdopcion.CATALOGO_PREVIO:
        return None   # ya había catálogo sin adopción: no se ofrece (mismo criterio que should_run)
    if e.adopcion is EstadoAdopcion.HECHA:
        if e.archivos_registrados:
            n = e.archivos_registrados
            detalle = (f"{n} {_plural(n, 'tebeo registrado', 'tebeos registrados')}"
                       " · no se movió ni se renombró nada")
        else:
            detalle = "Se leyó la carpeta, pero no se registró ningún tebeo."
        if informe:
            detalle += (f" · {informe.archivos_comparados} comparados a fondo "
                        f"el {fecha_llana(informe.fecha)}")
        return Paso(ClavePaso.BIBLIOTECA, "Tu biblioteca está registrada", detalle,
                    EstadoPaso.HECHO, True, "/ui/auditoria",
                    "Ver duplicados" if informe else "Buscar repetidos")
    if e.adopcion is EstadoAdopcion.PENDIENTE:
        detalle = ("Hay tebeos en la carpeta de tu biblioteca que ZascArr aún no conoce. "
                   "Registrarlos no mueve, renombra ni borra nada.")
        if informe:
            detalle += (f" Ya miraste qué hay repetido el {fecha_llana(informe.fecha)} "
                        f"({informe.archivos_leidos} leídos, "
                        f"{informe.archivos_comparados} comparados).")
        else:
            detalle += " Antes puedes ver qué hay repetido en tu disco; tampoco cambia nada."
        return Paso(ClavePaso.BIBLIOTECA, "Registra tu biblioteca", detalle,
                    EstadoPaso.SIGUIENTE, True, "/ui/auditoria", "Preparar mi biblioteca →")
    # SIN_TEBEOS
    return Paso(ClavePaso.BIBLIOTECA, "Registra tu biblioteca",
                "No hemos encontrado tebeos (.cbz, .cbr) en la carpeta de tu biblioteca. "
                "Cuando los copies ahí podrás registrarlos desde aquí.",
                EstadoPaso.BLOQUEADO, True)


def _paso_revisar(e: EstadoInicio) -> Paso:
    n = e.archivos_sin_clasificar
    if n:
        cuantos = _plural(n, "tebeo que no hemos sabido clasificar",
                          "tebeos que no hemos sabido clasificar")
        return Paso(ClavePaso.REVISAR, f"Revisa {n} {cuantos}",
                    "Puedes decirnos de qué serie son, uno a uno.",
                    EstadoPaso.SIGUIENTE, True, "/ui/pendientes", "Revisar ahora →")
    if e.archivos_registrados:
        return Paso(ClavePaso.REVISAR, "No tienes tebeos por clasificar",
                    "Todo lo registrado tiene ya su serie o lo has descartado.",
                    EstadoPaso.HECHO, True, "/ui/pendientes", "Ver")
    return Paso(ClavePaso.REVISAR, "Revisa lo que no sepamos clasificar",
                "Aún no hay tebeos registrados: los que no sepamos clasificar aparecerán aquí.",
                EstadoPaso.BLOQUEADO, True)


def _paso_series(e: EstadoInicio) -> Paso:
    n = e.series_seguidas
    if n:
        return Paso(ClavePaso.SERIES, f"Sigues {n} {_plural(n, 'serie', 'series')}",
                    "Tienes peticiones suyas en Deseados.",
                    EstadoPaso.HECHO, False, "/ui/descubrir", "Buscar más")
    return Paso(ClavePaso.SERIES, "Elige las series que quieres seguir",
                "Búscalas por título y las damos de alta con portada y datos.",
                EstadoPaso.OPCIONAL, False, "/ui/descubrir", "Buscar series")


def _paso_descargas(e: EstadoInicio) -> Paso:
    if e.hay_fuente_de_busqueda and e.aviso_legal_aceptado:
        return Paso(ClavePaso.DESCARGAS, "La búsqueda de descargas está activada",
                    "Hay una fuente activada y el aviso legal aceptado. "
                    "No comprobamos que conteste: "
                    "si una búsqueda falla, el motivo aparece en Deseados.",
                    EstadoPaso.HECHO, False, "/ui/ajustes", "Ajustes")
    if e.hay_fuente_de_busqueda:
        return Paso(ClavePaso.DESCARGAS, "Acepta el aviso legal para buscar descargas",
                    "Hay una fuente activada, pero sin el aviso legal aceptado no se busca nada.",
                    EstadoPaso.OPCIONAL, False, "/ui/legal", "Leer y aceptar")
    return Paso(ClavePaso.DESCARGAS, "Conecta cómo descargar",
                "Solo si quieres que ZascArr busque lo que te falta. "
                "Viene desactivado: lo decides tú.",
                EstadoPaso.OPCIONAL, False, "/ui/ajustes", "Configurar")


def calcular_primeros_pasos(estado: EstadoInicio) -> PrimerosPasos:
    """Pasos con su estado y el paso principal. Pura: mismos datos, mismo resultado."""
    crudos = [_paso_biblioteca(estado), _paso_revisar(estado),
              _paso_series(estado), _paso_descargas(estado)]
    pasos: list[Paso] = []
    ya_hay_siguiente = False
    for paso in crudos:
        if paso is None:
            continue
        if paso.estado is EstadoPaso.SIGUIENTE:
            # Solo uno es «el que toca»; los demás obligatorios por hacer quedan «pendientes».
            if ya_hay_siguiente:
                paso = replace(paso, estado=EstadoPaso.PENDIENTE)
            ya_hay_siguiente = True
        pasos.append(paso)
    principal = next((p for p in pasos if p.estado is EstadoPaso.SIGUIENTE), None)
    if principal is None:
        principal = next((p for p in pasos
                          if p.estado is EstadoPaso.OPCIONAL and p.enlace), None)
    return PrimerosPasos(pasos=tuple(pasos), principal=principal)
