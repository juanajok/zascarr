# ruff: noqa: E501
"""CNV5-3 / #482: sesión efímera en memoria para elegir propuestas de fuentes.

Single worker: un dict con TTL de 15 minutos, tope de sesiones y claves opacas por opción. No toca
BD, archivos ni `File.metadata_`; solo guarda propuestas, elecciones e identidad/stat/hash para que
CNV5-4 pueda validar antes de escribir. Las claves son opacas: el valor crudo nunca viaja en el
formulario.

La sesión es **del proceso** (instalación de un solo operador y un solo worker), no de una cookie ni
de un usuario: no hay identidad de persona que guardar. Al reiniciar se pierde y hay que volver a
buscar; nunca se usa para autorizar por sí sola (CNV5-4 exige además token y archivo).
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field, replace
from urllib.parse import urlsplit

from zascarr.core.propuestas_comicinfo import (
    EstadoPropuesta,
    NivelDato,
    OpcionPropuesta,
    PropuestaCampo,
    ResultadoFuente,
    campos_elegibles,
)

TTL_SESION_S = 15 * 60
MAX_SESIONES = 200

ETIQUETAS_CAMPO = {
    "Year": "Año",
    "Publisher": "Editorial",
    "Summary": "Sinopsis",
    "Writer": "Guionista",
    "Penciller": "Dibujante",
    "Inker": "Entintador",
    "Colorist": "Colorista",
    "Letterer": "Rotulista",
    "CoverArtist": "Portadista",
    "Editor": "Editor",
    "Translator": "Traductor",
    "Genre": "Género",
    "PageCount": "Páginas",
}
ETIQUETAS_NIVEL = {NivelDato.SERIE: "de la serie, no del número",
                   NivelDato.NUMERO: "del número"}
NOMBRES_FUENTE = {
    "comic_vine": "Comic Vine",
    "anilist": "AniList",
    "tebeosfera": "Tebeosfera",
    "gcd": "GCD",
}


def _url_segura(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parte = urlsplit(url)
    except ValueError:
        return None
    if parte.scheme not in ("http", "https") or not parte.hostname:
        return None
    if parte.username or parte.password:
        return None
    return url


@dataclass(frozen=True)
class OpcionUI:
    clave: str
    valor: str
    fuente: str
    nombre_fuente: str
    nivel: str
    procedencia: str | None


@dataclass(frozen=True)
class CampoUI:
    tag: str
    etiqueta: str
    actual: str | None
    opciones: tuple[OpcionUI, ...]
    bloqueado: bool = False
    motivo: str | None = None
    elegida: str | None = None
    estado: str = "anadir"


@dataclass
class SesionPropuestas:
    operacion_id: str
    file_id: str
    serie_id: str
    ruta: str
    tamano: int
    mtime_ns: int
    sha256: str
    propuestas: tuple[PropuestaCampo, ...]
    estados: tuple[ResultadoFuente, ...]
    avisos: tuple[str, ...]
    opciones: dict[str, OpcionPropuesta]
    claves_por_tag: dict[str, dict[str, str]]   # tag -> clave -> valor interno
    elecciones: dict[str, str] = field(default_factory=dict)
    creada: float = 0.0
    expira: float = 0.0

    @property
    def campos_sin_datos(self) -> tuple[CampoUI, ...]:
        con_propuesta = {p.tag for p in self.propuestas}
        return tuple(CampoUI(tag, ETIQUETAS_CAMPO.get(tag, tag), None, (), False,
                             "Sin datos nuevos en las fuentes", estado="sin_dato")
                     for tag in sorted(campos_elegibles() - con_propuesta))

    @property
    def reintento_cortesia(self) -> bool:
        return any(e.estado == "limite_de_cortesia" for e in self.estados)

    @property
    def avisos_fuentes(self) -> tuple[str, ...]:
        avisos = []
        for estado in self.estados:
            if estado.estado == "ok":
                continue
            nombre = NOMBRES_FUENTE.get(estado.fuente.value, estado.fuente.value)
            motivo = estado.motivo or "No se ha podido consultar."
            avisos.append(f"{nombre}: {motivo}")
        return tuple(avisos)

    @property
    def resumen(self) -> str:
        actuales = {p.tag: (p.actual or "") for p in self.propuestas}
        cambios = 0
        for tag, clave in self.elecciones.items():
            valor = self.claves_por_tag.get(tag, {}).get(clave)
            if valor and valor.strip().casefold() != actuales.get(tag, "").strip().casefold():
                cambios += 1
        total = len([p for p in self.propuestas if not p.bloqueado])
        sustantivo = "cambio" if cambios == 1 else "cambios"
        return f"Has elegido {cambios} {sustantivo} de {total} campos con propuesta."

    def campos_ui(self) -> tuple[CampoUI, ...]:
        salida: list[CampoUI] = []
        for p in self.propuestas:
            opciones = []
            for clave, valor in self.claves_por_tag.get(p.tag, {}).items():
                op = self.opciones[clave]
                opciones.append(OpcionUI(
                    clave=clave, valor=valor,
                    fuente=op.fuente.value,
                    nombre_fuente=NOMBRES_FUENTE.get(op.fuente.value, op.fuente.value),
                    nivel=ETIQUETAS_NIVEL.get(op.nivel, ""),
                    procedencia=_url_segura(op.procedencia),
                ))
            salida.append(CampoUI(
                tag=p.tag, etiqueta=ETIQUETAS_CAMPO.get(p.tag, p.tag),
                actual=p.actual, opciones=tuple(opciones), bloqueado=p.bloqueado,
                motivo=p.motivo, elegida=self.elecciones.get(p.tag),
                estado=p.estado.value,
            ))
        return tuple(salida)


class SesionCaducadaError(LookupError):
    pass


class AlmacenPropuestas:
    """Almacén en memoria con TTL y tope; pensado para un solo worker."""

    def __init__(self, *, ttl: float = TTL_SESION_S, maximo: int = MAX_SESIONES,
                 reloj=time.monotonic):
        self._ttl = ttl
        self._maximo = maximo
        self._reloj = reloj
        self._datos: dict[str, SesionPropuestas] = {}
        self._candado = threading.Lock()

    def limpiar(self) -> None:
        with self._candado:
            self._datos.clear()

    def _purgar(self, ahora: float) -> None:
        for clave in [k for k, s in self._datos.items() if s.expira <= ahora]:
            self._datos.pop(clave, None)
        if len(self._datos) > self._maximo:
            for clave, _ in sorted(self._datos.items(), key=lambda kv: kv[1].creada):
                if len(self._datos) <= self._maximo:
                    break
                self._datos.pop(clave, None)

    def crear(self, *, file_id: object, serie_id: object, ruta: str, tamano: int,
              mtime_ns: int, sha256: str, propuestas: tuple[PropuestaCampo, ...],
              estados: tuple[ResultadoFuente, ...] = (), avisos: tuple[str, ...] = (),
              bloqueados: set[str] | None = None) -> SesionPropuestas:
        ahora = self._reloj()
        opciones: dict[str, OpcionPropuesta] = {}
        claves_por_tag: dict[str, dict[str, str]] = {}
        finales: list[PropuestaCampo] = []
        bloqueados = bloqueados or set()
        for propuesta in propuestas:
            if propuesta.tag in bloqueados or propuesta.bloqueado:
                finales.append(replace(propuesta, opciones=(), bloqueado=True,
                                       estado=EstadoPropuesta.BLOQUEADO,
                                       motivo="Protegido: no se toca"))
                continue
            mapa: dict[str, str] = {}
            for opcion in propuesta.opciones:
                clave = uuid.uuid4().hex
                opciones[clave] = opcion
                mapa[clave] = opcion.valor
            claves_por_tag[propuesta.tag] = mapa
            finales.append(replace(propuesta, opciones=tuple(
                OpcionPropuesta(opciones[c].valor, opciones[c].fuente, opciones[c].nivel,
                                opciones[c].procedencia) for c in mapa)))
        sesion = SesionPropuestas(
            operacion_id=uuid.uuid4().hex, file_id=str(file_id), serie_id=str(serie_id),
            ruta=ruta, tamano=int(tamano), mtime_ns=int(mtime_ns), sha256=sha256,
            propuestas=tuple(finales), estados=tuple(estados), avisos=tuple(avisos),
            opciones=opciones, claves_por_tag=claves_por_tag,
            creada=ahora, expira=ahora + self._ttl,
        )
        with self._candado:
            self._purgar(ahora)
            self._datos[sesion.operacion_id] = sesion
        return sesion

    def obtener(self, operacion_id: str) -> SesionPropuestas:
        ahora = self._reloj()
        with self._candado:
            self._purgar(ahora)
            sesion = self._datos.get(operacion_id)
            if sesion is None:
                raise SesionCaducadaError(
                    "La búsqueda de datos ha caducado. Vuelve a buscar; no se ha cambiado nada.")
            return sesion

    def elegir(self, operacion_id: str, tag: str, clave: str | None) -> SesionPropuestas:
        sesion = self.obtener(operacion_id)
        with self._candado:
            if tag not in sesion.claves_por_tag:
                raise KeyError(tag)
            if clave:
                if clave not in sesion.claves_por_tag[tag]:
                    raise KeyError(clave)
                sesion.elecciones[tag] = clave
            else:
                sesion.elecciones.pop(tag, None)
            return sesion


#: Almacén de proceso (single worker); las pruebas lo limpian.
ALMACEN = AlmacenPropuestas()
