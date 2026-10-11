# ruff: noqa: E501
"""Vista previa de la vinculación (rebanada 2c): qué pasaría si estos archivos se vincularan a esta serie, SIN hacerlo.

Contrato: `docs/design/rebanada-2-elegir-serie-y-vincular.md`, bloque C («Implementación 2c») y ADR 0007.
Vincular conserva el nombre y la ruta de cada archivo, así que aquí **no hay destino que calcular ni proponer**.

Qué hace: recibe el grupo, la serie elegida y las modificaciones EXPLÍCITAS de la persona (números editados y
archivos marcados), evalúa cada registro y devuelve, por archivo, su número, su edición, su ruta actual, las señales
de la rebanada 1 recalculadas contra ESA serie y su estado (con todos los motivos de bloqueo, no solo uno). Si hay
al menos un archivo marcado y ejecutable emite el token `vincular` con lo que se vio.

Qué NO hace: no escribe nada (ni `Issue`, ni `files`, ni alias), no lee el contenido de los archivos (solo `stat`:
metadatos), no calcula hashes, no usa la red, no consulta fuentes y **no marca nada por su cuenta**.

Orden de precedencia cuando un registro tiene varios impedimentos (el primero que se cumple es su `estado`; todos
van en `motivos`):
`ya_vinculado` > `en_curso` > `origen_no_encontrado` > `origen_no_verificable` > `requiere_numero` >
`numero_repetido_en_el_grupo` > `colision_de_edicion` > `numero_ya_existe`. Sin impedimentos: `con_conflicto_de_carpeta`
(se puede marcar, con las señales a la vista) o `se_vincularia`. Fuera de la página: `fuera_de_la_pagina`, sin evaluar.

Páginas: como mucho `LIMITE_ARCHIVOS` (100) archivos evaluados por petición, en orden determinista (nombre e id) y
con un **cursor** explícito (`cursor` / `siguiente`): se puede llegar a cualquier archivo del grupo aunque los de la
primera página estén bloqueados. La selección, los números editados y el token valen solo para los archivos de la página.

Números repetidos: la vista los identifica todos (`repetido_con`), pero **no bloquean por sí solos**: lo que no puede
haber es dos archivos MARCADOS y ejecutables con el mismo número. Marcar solo uno permite vincularlo y deja el otro
pendiente; nada elige, fusiona ni elimina una copia.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import stat as _stat
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.core.carpetas import analizar_carpeta
from zascarr.models import (
    ASIGNACION_ESTADOS_VIVOS,
    EDITION_KIND_A_FORMAT,
    AsignacionOperacion,
    File,
    Issue,
    IssueFormat,
    Series,
)
from zascarr.services.descubrimiento_grupo import GrupoNoEncontradoError, SerieLocal
from zascarr.services.revision_carpetas import RevisionCarpetas, Senal, senales_contra_serie
from zascarr.services.tokens_revision import (
    MAX_NUMERO,
    ArchivoFirmado,
    VinculacionFirmada,
    clave_de_numero,
    crear_token_vinculacion,
)
from zascarr.utils.naming import parse_comic_filename

#: Hipótesis inicial conservadora (D8): no validada ni garantía de duración. Acota los `stat` y, en 2d, la transacción.
LIMITE_ARCHIVOS = 100

#: Impedimentos, por orden de precedencia. Un registro con cualquiera de ellos NO se puede marcar.
BLOQUEOS = ("ya_vinculado", "en_curso", "origen_no_encontrado", "origen_no_verificable", "requiere_numero",
            "numero_repetido_en_el_grupo", "colision_de_edicion", "numero_ambiguo", "numero_ya_existe")
EstadoArchivo = Literal["ya_vinculado", "en_curso", "origen_no_encontrado", "origen_no_verificable",
                        "requiere_numero", "numero_repetido_en_el_grupo", "colision_de_edicion",
                        "numero_ambiguo", "numero_ya_existe", "con_conflicto_de_carpeta", "se_vincularia", "fuera_de_la_pagina"]
Causa = Literal["permiso", "error_de_lectura", "biblioteca_no_accesible", "no_es_un_archivo", "fecha_anterior_a_1970"]

TEXTOS: dict[str, str] = {
    "ya_vinculado": "Ya está vinculado a una serie.",
    "en_curso": "Tiene una asignación en curso: espera a que termine.",
    "origen_no_encontrado": "Registro pendiente de verificar: en la ruta registrada no hay ningún archivo.",
    "requiere_numero": "Falta el número: escríbelo para poder vincularlo.",
    "con_conflicto_de_carpeta": "Se puede vincular, pero hay señales que lo contradicen: revísalas antes de marcarlo.",
    "se_vincularia": "Se vincularía en su sitio: conservará su nombre y su carpeta.",
    "numero_repetido_en_el_grupo": "Otro archivo marcado tiene el mismo número: marca solo uno de los dos.",
    "numero_ambiguo": "La serie tiene más de un número así (volúmenes distintos): no se elige uno por ti.",
    "fuera_de_la_pagina": f"Este archivo no está en esta página (máximo {LIMITE_ARCHIVOS} por página): "
                          "ábrela con su cursor para poder marcarlo.",
}
#: El número que sale del NOMBRE no cumple la regla del número (como mucho `MAX_NUMERO` caracteres, sin saltos de línea):
#: se trata como ausente, no se trunca ni se firma. No se enseña entero (puede ser larguísimo).
TEXTO_NUMERO_DEL_NOMBRE_NO_VALIDO = (
    f"El número que sale del nombre tiene más de {MAX_NUMERO} caracteres o no es válido, así que no se puede usar: "
    "escríbelo para poder vincularlo.")
#: «No se pudo verificar» NO afirma que el archivo haya desaparecido: solo que la comprobación falló.
TEXTOS_NO_VERIFICABLE: dict[str, str] = {
    "permiso": "No se pudo comprobar el archivo: no hay permiso para leer su carpeta. No significa que haya desaparecido.",
    "error_de_lectura": "No se pudo comprobar el archivo por un error de lectura del disco. No significa que haya desaparecido.",
    "biblioteca_no_accesible": "No se pudo comprobar el archivo: la carpeta de la biblioteca no está disponible (¿disco desmontado?). No significa que haya desaparecido.",
    "no_es_un_archivo": "La ruta registrada existe pero no es un archivo: no se puede vincular.",
    # No enseña la fecha: solo que es anterior a 1970 (el token no admite fechas negativas, #142).
    "fecha_anterior_a_1970": "La fecha de modificación del archivo es anterior a 1970 y no se puede comprobar. No significa que haya "
                             "desaparecido: actualiza su fecha (por ejemplo, volviendo a copiarlo) y repite la vista previa.",
}


class SerieElegidaNoExisteError(LookupError):
    """La serie elegida no existe (se borró, o el identificador es de otra instalación)."""


class ArchivoAjenoError(ValueError):
    """Se pidió modificar o marcar un archivo que no es de este grupo (ni está ya vinculado)."""

    def __init__(self, cuantos: int):
        super().__init__(f"{cuantos} archivo(s) no pertenecen a este grupo")
        self.cuantos = cuantos


class CursorNoValidoError(ValueError):
    """El cursor de página no se puede interpretar."""


class NumeroNoValidoError(ValueError):
    """Un número editado no cabe en `Issue.issue_number` o no es un texto razonable."""


# ── Contrato de salida ───────────────────────────────────────────────────────────────────────────

class ArchivoVinculacion(BaseModel):
    id: str
    nombre: str
    #: Relativa a la biblioteca; absoluta (y `fuera_de_la_biblioteca`) si el registro apunta fuera de ella.
    ruta_actual: str
    fuera_de_la_biblioteca: bool
    formato: str | None
    numero: str | None
    numero_del_nombre: str | None
    numero_origen: Literal["nombre", "persona", "ninguno"]
    estado: EstadoArchivo
    #: TODOS los impedimentos, por orden de precedencia (el primero es `estado`).
    motivos: list[str]
    texto: str
    causa: Causa | None
    marcado: bool
    marcable: bool
    incluido_en_token: bool
    #: Existe en la serie un `Issue` con ese número y edición (sin archivo): se reutilizaría, no es un impedimento.
    issue_existente: bool
    #: Ids de los OTROS archivos de esta página con el mismo número (sin distinguir mayúsculas). Informativo: no
    #: bloquea mientras no se marquen dos a la vez.
    repetido_con: list[str]
    conflictos: list[Senal]


class PaginaOut(BaseModel):
    """Posición de esta vista en el grupo (orden por nombre e id). `siguiente` es el cursor de la página posterior."""
    maximo: int
    en_el_grupo: int
    tratados: int
    desde: int
    hasta: int
    cursor: str | None
    siguiente: str | None
    hay_mas: bool
    texto: str | None


class TotalesVinculacion(BaseModel):
    marcados: int
    a_vincular: int
    marcados_bloqueados: int
    sin_marcar: int
    numeros_repetidos: int
    por_estado: dict[str, int]


class RespuestaVinculacion(BaseModel):
    clave: str
    serie: SerieLocal
    pagina: PaginaOut
    archivos: list[ArchivoVinculacion]
    totales: TotalesVinculacion
    avisos_de_grupo: list[Senal]
    token: str | None
    motivo_sin_token: str | None


# ── Comprobación de los orígenes (solo `stat`) ───────────────────────────────────────────────────

@dataclass(frozen=True)
class _Origen:
    estado: Literal["ok", "no_encontrado", "no_verificable"]
    tamano: int = 0
    mtime_ns: int = 0
    causa: Causa | None = None


def _comprobar_origenes(rutas: dict[str, str], biblioteca: Path, estadistica: Callable[[str], os.stat_result]
                        ) -> dict[str, _Origen]:
    """`stat` de cada ruta (sin abrir ni leer nada). Síncrono: se llama dentro de `asyncio.to_thread`.

    Distingue «no hay archivo» de «no se pudo comprobar»: un `FileNotFoundError` con la carpeta de la biblioteca
    inaccesible es un volumen que no responde, no un archivo que desapareció."""
    raiz_inaccesible: bool | None = None

    def biblioteca_inaccesible() -> bool:
        nonlocal raiz_inaccesible
        if raiz_inaccesible is None:
            try:
                raiz_inaccesible = not _stat.S_ISDIR(estadistica(str(biblioteca)).st_mode)
            except OSError:
                raiz_inaccesible = True
        return raiz_inaccesible

    salida: dict[str, _Origen] = {}
    for fid, ruta in rutas.items():
        try:
            st = estadistica(ruta)
        except (FileNotFoundError, NotADirectoryError):
            dentro = _dentro_de(ruta, biblioteca)
            salida[fid] = (_Origen("no_verificable", causa="biblioteca_no_accesible")
                           if dentro and biblioteca_inaccesible() else _Origen("no_encontrado"))
        except PermissionError:
            salida[fid] = _Origen("no_verificable", causa="permiso")
        except OSError:
            salida[fid] = _Origen("no_verificable", causa="error_de_lectura")
        else:
            if not _stat.S_ISREG(st.st_mode):
                salida[fid] = _Origen("no_verificable", causa="no_es_un_archivo")
            elif st.st_mtime_ns < 0:
                # El token firma `mtime_ns` y el verificador exige `>= 0`: un archivo anterior a 1970 no se podría
                # confirmar y arrastraría todo el lote (#142). Se defiende la vista previa; el verificador no cambia.
                salida[fid] = _Origen("no_verificable", causa="fecha_anterior_a_1970")
            else:
                salida[fid] = _Origen("ok", st.st_size, st.st_mtime_ns)
    return salida


def _dentro_de(ruta: str, biblioteca: Path) -> bool:
    try:
        PurePosixPath(ruta).relative_to(PurePosixPath(str(biblioteca)))
        return True
    except ValueError:
        return False


# ── Servicio ─────────────────────────────────────────────────────────────────────────────────────

# ── Cursor de página ─────────────────────────────────────────────────────────────────────────────

def _cursor_de(a) -> str:
    """Posición en el orden estable del grupo (nombre, id). Es solo una posición: no autoriza nada ni va firmada."""
    return base64.urlsafe_b64encode(json.dumps([a.nombre, a.id], ensure_ascii=False).encode()).decode()


def _leer_cursor(cursor: str) -> tuple[str, str]:
    try:
        nombre, ident = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        if not isinstance(nombre, str) or not isinstance(ident, str):
            raise ValueError
        UUID(ident)
        return nombre, ident
    except (ValueError, TypeError, UnicodeError):
        raise CursorNoValidoError("El cursor de la página no es válido.") from None


class VistaPreviaDeVinculacion:
    def __init__(self, db: AsyncSession, *, secret: str, biblioteca: Path | str | None = None,
                 estadistica: Callable[[str], os.stat_result] | None = None, ahora: float | None = None):
        self._db = db
        self._secret = secret
        self._biblioteca = Path(str(biblioteca or get_settings().library_path))
        # Enlace tardío: lo que se llama es `os.stat` en el momento de usarlo (las pruebas lo observan).
        self._estadistica = estadistica or (lambda ruta: os.stat(ruta))
        self._ahora = ahora

    async def previsualizar(self, clave: str, series_id: UUID, *, numeros: dict[str, str] | None = None,
                            marcados: set[str] | None = None, cursor: str | None = None) -> RespuestaVinculacion:
        numeros = {k: self._numero_valido(v) for k, v in (numeros or {}).items()}
        marcados = set(marcados or ())
        db = self._db

        grupo = await RevisionCarpetas(db, self._biblioteca).archivos_del_grupo(clave)
        if grupo is None:
            raise GrupoNoEncontradoError(clave)
        div, todos = grupo
        serie = (await db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
        if serie is None:
            raise SerieElegidaNoExisteError(str(series_id))

        # La página: los `LIMITE_ARCHIVOS` primeros DESPUÉS del cursor (clave de orden estable: aunque otros archivos
        # se vinculen entre petición y petición, el cursor sigue señalando el mismo punto).
        despues = todos if not cursor else [a for a in todos if (a.nombre, a.id) > _leer_cursor(cursor)]
        tratados, resto = despues[:LIMITE_ARCHIVOS], despues[LIMITE_ARCHIVOS:]
        antes = len(todos) - len(despues)
        en_grupo = {a.id for a in todos}
        pedidos = set(numeros) | marcados
        ajenos = pedidos - en_grupo
        ya_vinculados = await self._ya_vinculados(ajenos)
        if len(ya_vinculados) != len(ajenos):
            raise ArchivoAjenoError(len(ajenos) - len(ya_vinculados))
        en_pagina = {a.id for a in tratados}
        fuera = [a for a in todos if a.id in pedidos and a.id not in en_pagina]

        # ── Lecturas de BD (constantes: no dependen del número de archivos) ──
        ids = [UUID(a.id) for a in tratados] + [UUID(i) for i in ya_vinculados]
        rutas = {str(i): r for i, r in (await db.execute(select(File.id, File.file_path).where(File.id.in_(ids)))).all()}
        en_curso = {str(f) for (f,) in (await db.execute(select(AsignacionOperacion.file_id).where(
            AsignacionOperacion.file_id.in_(ids), AsignacionOperacion.estado.in_(ASIGNACION_ESTADOS_VIVOS)))).all()}

        # ── Número y edición de cada archivo: del nombre, salvo lo que la persona haya editado ──
        propuesta: dict[str, tuple[str | None, str | None, str, str]] = {}
        descartados: set[str] = set()        # archivos cuyo número del nombre no cumple la regla (se trata como ausente)
        for a in tratados + fuera:
            p = parse_comic_filename(a.nombre)
            del_nombre, descartado = self._numero_del_nombre(p.issue_number)
            if descartado and a.id not in numeros:
                descartados.add(a.id)
            formato = EDITION_KIND_A_FORMAT.get(p.edition_kind, IssueFormat.SINGLE_ISSUE).value
            if a.id in numeros:
                numero, origen = numeros[a.id] or None, "persona"
            else:
                numero, origen = del_nombre, "nombre" if del_nombre else "ninguno"
            propuesta[a.id] = (numero, del_nombre, formato, origen)

        existentes = await self._issues_de_la_serie(serie.id, {n for n, *_ in propuesta.values() if n})
        origenes = await asyncio.to_thread(
            _comprobar_origenes, {a.id: rutas[a.id] for a in tratados if a.id in rutas},
            self._biblioteca, self._estadistica)
        repetidos = self._repetidos([(a.id, propuesta[a.id][0]) for a in tratados])      # id → otros con ese número

        # ── Señales de la rebanada 1 contra la serie elegida (todo el grupo, no solo lo tratado) ──
        carpeta = analizar_carpeta(div.contextual) if div.contextual else None
        senales = senales_contra_serie(todos, carpeta, serie.title, serie.start_year, tiene_contexto=bool(div.contextual))
        de_grupo = [s for s in senales if not s.archivos]

        salida: list[ArchivoVinculacion] = []
        evaluar = {}
        for a in tratados:
            numero, del_nombre, formato, origen_n = propuesta[a.id]
            evaluar[a.id] = dict(
                fid=a.id, nombre=a.nombre, ruta=rutas.get(a.id), numero=numero, del_nombre=del_nombre, formato=formato,
                origen_n=origen_n, origen=origenes.get(a.id), en_curso=a.id in en_curso,
                repetido_con=repetidos.get(a.id, []), existentes=existentes,
                conflictos=[s for s in senales if a.id in s.archivos], marcado=a.id in marcados,
                numero_del_nombre_descartado=a.id in descartados)
            salida.append(self._evaluar(**evaluar[a.id], repetido_en_seleccion=False))
        # Lo que no puede haber es dos archivos MARCADOS y ejecutables con el mismo número: se bloquean ambos (nada
        # elige por la persona). Un duplicado sin marcar, o marcado solo él, no se bloquea.
        por_numero: dict[str, list[str]] = defaultdict(list)
        for f in salida:
            if f.marcado and not f.motivos and f.numero:
                por_numero[clave_de_numero(f.numero)].append(f.id)
        en_conflicto = {i for ids_ in por_numero.values() if len(ids_) > 1 for i in ids_}
        salida = [self._evaluar(**evaluar[f.id], repetido_en_seleccion=True) if f.id in en_conflicto else f for f in salida]
        for a in fuera:
            numero, del_nombre, formato, origen_n = propuesta[a.id]
            salida.append(self._fuera_de_la_pagina(a.id, a.nombre, numero, del_nombre, formato, origen_n, a.id in marcados))
        for fid, (nombre, ruta) in ya_vinculados.items():
            salida.append(self._ya_vinculado(fid, nombre, ruta, fid in marcados))

        # ── Token: solo si hay una selección ejecutable ──
        incluidos = [f for f in salida if f.incluido_en_token]
        token = None
        if incluidos:
            firmados = tuple(
                ArchivoFirmado(f.id, f.numero or "", f.formato or "", origenes[f.id].tamano, origenes[f.id].mtime_ns,
                               tuple(sorted({s.codigo for s in f.conflictos if s.severidad == "conflicto"})))
                for f in incluidos)
            token = crear_token_vinculacion(
                VinculacionFirmada(clave, str(serie.id), str(uuid4()), firmados), self._secret, ahora=self._ahora)
        n_marcados = sum(1 for f in salida if f.marcado)
        motivo = None
        if token is None:
            motivo = ("No has marcado ningún archivo." if n_marcados == 0 else
                      "Ninguno de los archivos marcados se puede vincular: mira el motivo de cada uno.")

        avisos = list(de_grupo)
        if tratados and all(o.estado == "no_encontrado" for o in origenes.values()) and len(origenes) >= 5:
            avisos.append(Senal(
                codigo="ningun_origen_encontrado", severidad="aviso",
                texto="Ningún archivo de este grupo se encuentra en su ruta registrada. Si el disco no está "
                      "montado, no es que hayan desaparecido: comprueba el disco antes de dar por perdidos los registros."))
        return RespuestaVinculacion(
            clave=clave, serie=SerieLocal(series_id=str(serie.id), titulo=serie.title, anio=serie.start_year,
                                          tradicion=serie.tradition.value),
            pagina=PaginaOut(
                maximo=LIMITE_ARCHIVOS, en_el_grupo=len(todos), tratados=len(tratados),
                desde=antes + 1 if tratados else 0, hasta=antes + len(tratados), cursor=cursor or None,
                siguiente=_cursor_de(tratados[-1]) if resto and tratados else None, hay_mas=bool(resto),
                texto=None if not resto and not antes else
                f"Este grupo tiene {len(todos)} archivos pendientes; esta página muestra del {antes + 1} al "
                f"{antes + len(tratados)} (máximo {LIMITE_ARCHIVOS} por página, por nombre). Lo que marques, los "
                "números que edites y el token valen solo para los archivos de esta página."),
            archivos=salida,
            totales=TotalesVinculacion(
                marcados=n_marcados, a_vincular=len(incluidos),
                marcados_bloqueados=sum(1 for f in salida if f.marcado and not f.marcable),
                sin_marcar=sum(1 for f in salida if not f.marcado),
                numeros_repetidos=sum(1 for f in salida if f.repetido_con),
                por_estado=dict(Counter(f.estado for f in salida))),
            avisos_de_grupo=avisos, token=token, motivo_sin_token=motivo)

    # ── Piezas ───────────────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _numero_del_nombre(valor: str | None) -> tuple[str | None, bool]:
        """(número utilizable o `None`, descartado). El número que sale del nombre pasa por la MISMA regla que el que
        escribe la persona (`_numero_valido`): si no la cumple se trata como AUSENTE (el archivo pasa a «requiere
        número»), nunca se trunca. Sin esto, la vista previa lo firmaba y el verificador (≤ `MAX_NUMERO` caracteres)
        rechazaba el token ENTERO. El parser no acota el número y no se toca."""
        v = (valor or "").strip()
        if not v:
            return None, False
        try:
            return VistaPreviaDeVinculacion._numero_valido(v) or None, False
        except NumeroNoValidoError:
            return None, True

    @staticmethod
    def _numero_valido(valor: str) -> str:
        v = (valor or "").strip()
        if len(v) > MAX_NUMERO or any(c in v for c in "\n\r\t\x00"):
            raise NumeroNoValidoError("El número no es válido (máximo 20 caracteres, sin saltos de línea).")
        return v

    async def _ya_vinculados(self, ids: set[str]) -> dict[str, tuple[str, str]]:
        """De los ids ajenos al grupo, los que ya tienen serie: se muestran como `ya_vinculado`. Los demás son errores."""
        if not ids:
            return {}
        filas = (await self._db.execute(
            select(File.id, File.file_name, File.file_path).where(
                File.id.in_([UUID(i) for i in ids]), File.issue_id.is_not(None)))).all()
        return {str(i): (nombre, ruta) for i, nombre, ruta in filas}

    async def _issues_de_la_serie(self, series_id, numeros: set[str]) -> dict[str, list[tuple[IssueFormat, int]]]:
        """clave de número (sin distinguir mayúsculas) → [(edición, archivos ya vinculados)] de los `Issue` de la
        serie con esos números. Más de uno por clave (volúmenes distintos, o `volume` NULL) = ambiguo."""
        if not numeros:
            return {}
        claves = {clave_de_numero(n) for n in numeros}
        filas = (await self._db.execute(select(Issue.id, Issue.issue_number, Issue.format).where(
            Issue.series_id == series_id, func.lower(Issue.issue_number).in_(claves)))).all()
        if not filas:
            return {}
        cuenta = dict((await self._db.execute(
            select(File.issue_id, func.count()).where(File.issue_id.in_([f[0] for f in filas])).group_by(File.issue_id))).all())
        salida: dict[str, list[tuple[IssueFormat, int]]] = defaultdict(list)
        for iid, n, fmt in filas:
            salida[clave_de_numero(n)].append((fmt or IssueFormat.SINGLE_ISSUE, cuenta.get(iid, 0)))
        return dict(salida)

    @staticmethod
    def _repetidos(pares: list[tuple[str, str | None]]) -> dict[str, list[str]]:
        """id → ids de los OTROS archivos con el mismo número (sin distinguir mayúsculas). Solo los que se repiten."""
        por_numero: dict[str, list[str]] = defaultdict(list)
        for fid, numero in pares:
            if numero:
                por_numero[clave_de_numero(numero)].append(fid)
        return {fid: sorted(i for i in por_numero[clave_de_numero(numero)] if i != fid)
                for fid, numero in pares if numero and len(por_numero[clave_de_numero(numero)]) > 1}

    def _evaluar(self, fid, nombre, ruta, numero, del_nombre, formato, origen_n, origen: _Origen | None, en_curso: bool,
                 repetido_con: list[str], existentes, conflictos: list[Senal], marcado: bool,
                 repetido_en_seleccion: bool, numero_del_nombre_descartado: bool = False) -> ArchivoVinculacion:
        motivos: list[str] = []
        causa: str | None = None
        if en_curso:
            motivos.append("en_curso")
        if origen is None or origen.estado == "no_encontrado":
            motivos.append("origen_no_encontrado")
        elif origen.estado == "no_verificable":
            motivos.append("origen_no_verificable")
            causa = origen.causa
        if not numero:
            motivos.append("requiere_numero")
        elif repetido_en_seleccion:
            motivos.append("numero_repetido_en_el_grupo")
        lista = existentes.get(clave_de_numero(numero)) if numero else None
        existente = lista[0] if lista and len(lista) == 1 else None
        texto_extra = ""
        if lista and len(lista) > 1:
            motivos.append("numero_ambiguo")
        elif existente is not None:
            fmt_existente, con_archivos = existente
            if fmt_existente.value != formato:
                motivos.append("colision_de_edicion")
                texto_extra = f"El número {numero} ya existe en la serie como otra edición ({fmt_existente.value})."
            elif con_archivos:
                motivos.append("numero_ya_existe")
                texto_extra = f"El número {numero} ya tiene {con_archivos} archivo(s) vinculado(s) en la serie."
        motivos.sort(key=BLOQUEOS.index)
        if motivos:
            estado = motivos[0]
            if estado == "origen_no_verificable":
                texto = TEXTOS_NO_VERIFICABLE[causa or "error_de_lectura"]
            elif estado in ("colision_de_edicion", "numero_ya_existe"):
                texto = texto_extra
            elif estado == "numero_ambiguo":
                texto = TEXTOS["numero_ambiguo"]
            elif estado == "numero_repetido_en_el_grupo":
                texto = f"Otro archivo marcado tiene el mismo número ({numero}): marca solo uno de los dos."
            elif estado == "requiere_numero" and numero_del_nombre_descartado:
                texto = TEXTO_NUMERO_DEL_NOMBRE_NO_VALIDO
            else:
                texto = TEXTOS[estado]
        else:
            estado = "con_conflicto_de_carpeta" if any(s.severidad == "conflicto" for s in conflictos) else "se_vincularia"
            texto = TEXTOS[estado]
            if repetido_con:
                texto += f" Comparte el número {numero} con otro archivo: se puede vincular uno, no los dos a la vez."
        marcable = not motivos
        return ArchivoVinculacion(
            id=fid, nombre=nombre, **self._ruta(ruta), formato=formato, numero=numero, numero_del_nombre=del_nombre,
            numero_origen=origen_n, estado=estado, motivos=motivos, texto=texto, causa=causa, marcado=marcado,
            marcable=marcable, incluido_en_token=marcado and marcable,
            issue_existente=bool(existente and not motivos), repetido_con=repetido_con, conflictos=conflictos)

    def _fuera_de_la_pagina(self, fid, nombre, numero, del_nombre, formato, origen_n, marcado) -> ArchivoVinculacion:
        return ArchivoVinculacion(
            id=fid, nombre=nombre, ruta_actual="", fuera_de_la_biblioteca=False, formato=formato, numero=numero,
            numero_del_nombre=del_nombre, numero_origen=origen_n, estado="fuera_de_la_pagina", motivos=["fuera_de_la_pagina"],
            texto=TEXTOS["fuera_de_la_pagina"], causa=None, marcado=marcado, marcable=False, incluido_en_token=False,
            issue_existente=False, repetido_con=[], conflictos=[])

    def _ya_vinculado(self, fid, nombre, ruta, marcado) -> ArchivoVinculacion:
        return ArchivoVinculacion(
            id=fid, nombre=nombre, **self._ruta(ruta), formato=None, numero=None, numero_del_nombre=None,
            numero_origen="ninguno", estado="ya_vinculado", motivos=["ya_vinculado"], texto=TEXTOS["ya_vinculado"],
            causa=None, marcado=marcado, marcable=False, incluido_en_token=False, issue_existente=False,
            repetido_con=[], conflictos=[])

    def _ruta(self, ruta: str | None) -> dict:
        if not ruta:
            return {"ruta_actual": "", "fuera_de_la_biblioteca": False}
        try:
            return {"ruta_actual": str(PurePosixPath(ruta).relative_to(PurePosixPath(str(self._biblioteca)))),
                    "fuera_de_la_biblioteca": False}
        except ValueError:
            return {"ruta_actual": ruta, "fuera_de_la_biblioteca": True}
