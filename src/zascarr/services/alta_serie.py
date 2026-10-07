# ruff: noqa: E501
"""Alta o reutilización de una serie desde la superficie de revisión (rebanada 2b).

Contrato: `docs/design/rebanada-2-elegir-serie-y-vincular.md`, bloque B. Tres operaciones:

- `previsualizar`: **solo lectura**. Dice qué pasaría (reutilizar una serie existente, elegir entre posibles
  duplicados o crear una nueva) y, cuando ya no falta ninguna decisión, emite el **token de alta**.
- `confirmar`: recibe **solo el token**. Reutilizar no escribe nada; crear escribe **una fila de `series`**
  (con su procedencia) y nada más: ni números, ni archivos, ni búsquedas ni enriquecimientos.
- `deshacer`: borra una serie **creada por una operación concreta** mientras nada dependa de ella.

Tres reglas que lo sostienen:

1. **Nada se decide en silencio.** El mismo identificador externo es la única coincidencia automática (es exacta).
   Un título normalizado igual, con año compatible (±1) y la misma tradición es un *posible duplicado*: la
   persona decide «usar la existente» o «crear igualmente». La tradición se **elige** (sin valor por defecto).
2. **Lo que se ejecuta es lo que se vio.** El alta usa solo el token. Al confirmar se vuelve a comprobar, DENTRO
   de la transacción y bajo un candado del título normalizado, que no hayan aparecido parecidas que la persona no
   vio; si aparecieron, 409 y hay que rehacer la vista previa.
3. **La identidad elegida no la cambia un enriquecedor.** Alta desde una fuente: `metadata_source` = esa fuente y
   el campo del id externo en `locked_fields`. Alta manual: `metadata_source = 'manual'` (que ningún
   enriquecedor toca). La procedencia va en `Series.metadata_["alta"]` (versionada, sin token ni sesión).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.core.matcher import normalize_title
from zascarr.models import (
    ASIGNACION_ESTADOS_VIVOS,
    AsignacionOperacion,
    ComicTradition,
    File,
    Issue,
    MetadataSource,
    Series,
    Wishlist,
    WishlistPolicy,
)
from zascarr.services.descubrimiento_grupo import (
    MOTIVO_PARECIDA,
    GrupoNoEncontradoError,
    SerieLocal,
    SerieParecida,
    _a_serie_local,
    _anios_compatibles,
)
from zascarr.services.discovery import CAMPO_ID_EXTERNO, CAMPOS_ID_DE_TEXTO
from zascarr.services.revision_carpetas import RevisionCarpetas
from zascarr.services.tokens_revision import (
    AltaFirmada,
    crear_token_alta,
    verificar_token_alta,
    verificar_token_candidata,
)
from zascarr.utils.url_portada import es_url_de_portada_permitida

VERSION_PROCEDENCIA = 1
#: Espacio de nombres del candado consultivo: que no choque con otros usos de `pg_advisory_xact_lock`.
_ESPACIO_CANDADO = "alta_serie:"
MAX_TITULO = 500
ANIO_MIN, ANIO_MAX = 1800, 2100

Decision = Literal["reutilizar", "crear_igualmente"]


# ── Errores (el router los traduce) ──────────────────────────────────────────────────────────────

class AltaError(Exception):
    """Base: cada subclase lleva un `codigo` estable para la interfaz."""
    codigo = "alta_error"


class TokenInvalidoError(AltaError):
    codigo = "token_invalido"


class DatosInvalidosError(AltaError):
    codigo = "datos_invalidos"


class DecisionInvalidaError(AltaError):
    codigo = "decision_invalida"


class SerieYaNoExisteError(AltaError):
    """La vista previa decía «usar la existente» y esa serie ya no está: hay que rehacer la vista previa."""
    codigo = "la_serie_ya_no_existe"


class ParecidasNuevasError(AltaError):
    """Aparecieron series parecidas que la persona no vio en la vista previa."""
    codigo = "aparecieron_parecidas"

    def __init__(self, nuevas: list[SerieParecida]):
        super().__init__("aparecieron series parecidas después de la vista previa")
        self.nuevas = nuevas


class SerieNoEncontradaError(AltaError):
    codigo = "serie_no_encontrada"


class NoSePuedeDeshacerError(AltaError):
    """`motivo`: `no_creada_por_esta_operacion`, `tiene_archivos`, `tiene_numeros`, `operacion_viva`,
    `tiene_deseados`."""
    codigo = "no_se_puede_deshacer"

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


# ── Contrato de entrada y salida ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DatosManuales:
    titulo: str
    anio: int | None = None


class VistaPreviaAlta(BaseModel):
    """`accion`: `reutilizar` (ya existe con ese identificador, o se eligió una parecida), `elegir` (hay
    posibles duplicados y falta decidir: **sin token**) o `crear`. `token` solo cuando no falta ninguna decisión."""
    accion: Literal["reutilizar", "elegir", "crear"]
    origen: Literal["descubrir", "manual"]
    fuente: str | None
    titulo: str
    anio: int | None
    tradicion: str
    tradicion_sugerida: str | None
    existente: SerieLocal | None
    parecidas: list[SerieParecida]
    decision: str | None
    resumen: str
    efectos: dict[str, int]
    token: str | None


class ResultadoAlta(BaseModel):
    """`resultado`: `creada` o `reutilizada`. `repetida`: esta confirmación ya se había ejecutado y se devuelve
    lo mismo. `deshacer`: solo si se CREÓ; es lo que hace falta para deshacer."""
    resultado: Literal["creada", "reutilizada"]
    serie: SerieLocal
    repetida: bool
    motivo: str | None
    deshacer: dict[str, str] | None


class ResultadoDeshacer(BaseModel):
    deshecho: bool
    series_id: str
    titulo: str


# ── Servicio ─────────────────────────────────────────────────────────────────────────────────────

def fusionar_metadata(actual: dict | None, cambios: dict) -> dict:
    """Regla para CUALQUIER escritor de `Series.metadata_` (enriquecedores incluidos): fusionar por clave de primer
    nivel, nunca sustituir el objeto, y no tocar `alta` (la procedencia del alta es de este flujo)."""
    resultado = dict(actual or {})
    for clave, valor in cambios.items():
        if clave != "alta":
            resultado[clave] = valor
    return resultado


def _limpiar_titulo(titulo: str) -> str:
    limpio = " ".join((titulo or "").split())
    if not limpio or len(limpio) > MAX_TITULO or not normalize_title(limpio):
        raise DatosInvalidosError("El título no puede estar vacío ni ser solo símbolos.")
    return limpio


def _valor_de_id(campo: str, id_externo: str) -> int | str:
    if campo in CAMPOS_ID_DE_TEXTO:
        return id_externo
    try:
        return int(id_externo)
    except ValueError:
        raise DatosInvalidosError("El identificador externo no es válido.") from None


class AltaDeSerie:
    def __init__(self, db: AsyncSession, *, secret: str, ahora: float | None = None):
        self._db = db
        self._secret = secret
        self._ahora = ahora

    # ── Vista previa (solo lectura) ──────────────────────────────────────────────────────────────

    async def previsualizar(
        self, clave: str, *, tradicion: ComicTradition, candidata: str | None = None,
        manual: DatosManuales | None = None, decision: Decision | None = None, serie_id: UUID | None = None,
    ) -> VistaPreviaAlta:
        if candidata is not None and manual is not None or (candidata is None and manual is None):
            raise DatosInvalidosError("Indica una candidata de una fuente o los datos a mano, no ambos ni ninguno.")
        if await RevisionCarpetas(self._db).archivos_del_grupo(clave) is None:
            raise GrupoNoEncontradoError(clave)

        if candidata is not None:
            c = verificar_token_candidata(candidata, clave, self._secret, ahora=self._ahora)
            if c is None:
                raise TokenInvalidoError("La candidata no es válida o ha caducado: vuelve a buscar.")
            origen, fuente, id_externo = "descubrir", c.fuente, c.id_externo
            titulo, anio = _limpiar_titulo(c.titulo), c.anio
            descripcion = c.descripcion
            cover = c.cover_url if c.cover_url and es_url_de_portada_permitida(c.cover_url) else None
            sugerida: str | None = c.tradicion
        elif manual is not None:
            origen, fuente, id_externo = "manual", None, None
            titulo, anio = _limpiar_titulo(manual.titulo), manual.anio
            descripcion = cover = sugerida = None
        if anio is not None and not (ANIO_MIN <= anio <= ANIO_MAX):
            raise DatosInvalidosError("El año no es válido.")

        existente = await self._por_id_externo(fuente, id_externo) if origen == "descubrir" else None
        parecidas = [] if existente is not None else await self._parecidas(titulo, anio, tradicion, excluir=None)
        operacion = str(uuid4())
        base = dict(clave=clave, origen=origen, fuente=fuente, id_externo=id_externo, titulo=titulo, anio=anio,
                    tradicion=tradicion.value, descripcion=descripcion, cover_url=cover, operacion=operacion)

        if existente is not None:
            # La única coincidencia automática: el mismo identificador externo. No se modifica la existente.
            token = crear_token_alta(AltaFirmada(modo="reutilizar", serie_id=str(existente.id), vistas=(), **base),
                                     self._secret, ahora=self._ahora)
            return self._vista(origen, fuente, titulo, anio, tradicion, sugerida, "reutilizar", _a_serie_local(existente), [],
                               None, token, "Ya existe una serie con ese identificador: se usará tal cual, "
                                            "sin modificarla.")

        if parecidas and decision is None:
            return self._vista(origen, fuente, titulo, anio, tradicion, sugerida, "elegir", None, parecidas, None,
                               None, "Hay series que se parecen: elige si es la misma o si es distinta.")
        if decision == "reutilizar":
            elegida = next((p for p in parecidas if serie_id is not None and p.series_id == str(serie_id)), None)
            if elegida is None:
                raise DecisionInvalidaError("La serie elegida no está entre las parecidas.")
            token = crear_token_alta(AltaFirmada(modo="reutilizar", serie_id=elegida.series_id, vistas=(), **base),
                                     self._secret, ahora=self._ahora)
            return self._vista(origen, fuente, titulo, anio, tradicion, sugerida, "reutilizar",
                               SerieLocal(series_id=elegida.series_id, titulo=elegida.titulo, anio=elegida.anio,
                                          tradicion=elegida.tradicion),
                               parecidas, decision, token, "Se usará la serie existente que elegiste, sin modificarla.")
        if decision is not None and decision != "crear_igualmente":
            raise DecisionInvalidaError("Decisión desconocida.")
        if decision == "crear_igualmente" and not parecidas:
            decision = None          # nada que decidir: es un alta normal
        token = crear_token_alta(
            AltaFirmada(modo="crear", serie_id=None, vistas=tuple(p.series_id for p in parecidas), **base),
            self._secret, ahora=self._ahora)
        return self._vista(origen, fuente, titulo, anio, tradicion, sugerida, "crear", None, parecidas, decision,
                           token, "Se creará una serie vacía: sin números ni archivos. Vincular archivos es "
                                  "otro paso, con su propia confirmación.")

    @staticmethod
    def _vista(origen, fuente, titulo, anio, tradicion, sugerida, accion, existente, parecidas, decision, token,
               resumen) -> VistaPreviaAlta:
        return VistaPreviaAlta(
            accion=accion, origen=origen, fuente=fuente, titulo=titulo, anio=anio, tradicion=tradicion.value,
            tradicion_sugerida=sugerida, existente=existente, parecidas=parecidas, decision=decision,
            resumen=resumen, efectos={"series_nuevas": 1 if accion == "crear" else 0, "numeros": 0, "archivos": 0},
            token=token)

    # ── Confirmación ─────────────────────────────────────────────────────────────────────────────

    async def confirmar(self, token: str) -> ResultadoAlta:
        alta = verificar_token_alta(token, self._secret, ahora=self._ahora)
        if alta is None:
            raise TokenInvalidoError("El token no es válido o ha caducado: repite la vista previa.")
        if alta.modo == "reutilizar":
            return await self._reutilizar(alta)
        return await self._crear(alta)

    async def _reutilizar(self, alta: AltaFirmada) -> ResultadoAlta:
        """No escribe nada: comprueba que la serie que se vio siga existiendo (y, si se vio por su identificador
        externo, que siga teniéndolo)."""
        serie = (await self._db.execute(
            select(Series).where(Series.id == UUID(alta.serie_id or "")))).scalar_one_or_none()
        por_id = False
        if serie is not None and alta.origen == "descubrir" and alta.fuente and alta.id_externo is not None:
            campo = CAMPO_ID_EXTERNO[MetadataSource(alta.fuente)]
            por_id = str(getattr(serie, campo)) == alta.id_externo
        if serie is None:
            raise SerieYaNoExisteError("La serie que ibas a usar ya no existe: repite la vista previa.")
        await self._db.commit()
        return ResultadoAlta(resultado="reutilizada", serie=_a_serie_local(serie), repetida=False,
                             motivo="mismo_identificador" if por_id else "elegida_por_la_persona", deshacer=None)

    async def _crear(self, alta: AltaFirmada) -> ResultadoAlta:
        db = self._db
        # 1. Candado del TÍTULO NORMALIZADO (sin año ni tradición): serializa todas las altas que podrían
        #    colisionar, también 1987 frente a 1988. Dura hasta el `commit` o el `rollback`.
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k || f_title_norm(:t), 0))"),
                         {"k": _ESPACIO_CANDADO, "t": alta.titulo})

        # 2. Idempotencia: esta misma operación ya se confirmó (reintento o doble envío).
        previa = (await db.execute(
            select(Series).where(Series.metadata_["alta"]["operacion_id"].astext == alta.operacion))).scalar_one_or_none()
        if previa is not None:
            await db.commit()
            return self._resultado_creada(previa, alta.operacion, repetida=True)

        # 3. Carrera por el identificador externo: ya existe → es una REUTILIZACIÓN, no un error.
        campo = CAMPO_ID_EXTERNO.get(MetadataSource(alta.fuente)) if alta.fuente else None
        if campo is not None and alta.id_externo is not None:
            existente = await self._por_id_externo(alta.fuente, alta.id_externo)
            if existente is not None:
                await db.commit()
                return ResultadoAlta(resultado="reutilizada", serie=_a_serie_local(existente), repetida=False,
                                     motivo="mismo_identificador", deshacer=None)

        # 4. Se REPITE la comprobación de parecidas dentro de la transacción y bajo el candado.
        ahora_parecidas = await self._parecidas(alta.titulo, alta.anio, ComicTradition(alta.tradicion), excluir=None)
        nuevas = [p for p in ahora_parecidas if p.series_id not in set(alta.vistas)]
        if nuevas:
            await db.rollback()
            raise ParecidasNuevasError(nuevas)

        # 5. Alta. Si aun así salta el UNIQUE del identificador (otra confirmación con otro título), se trata
        #    como «ya existía» (H4), no como un error 500.
        serie = Series(
            title=alta.titulo, tradition=ComicTradition(alta.tradicion), start_year=alta.anio,
            description=alta.descripcion,
            cover_url=alta.cover_url if alta.cover_url and es_url_de_portada_permitida(alta.cover_url) else None,
            metadata_source=alta.fuente or MetadataSource.MANUAL.value,
            locked_fields=[campo] if campo is not None else [],
            metadata_={"alta": self._procedencia(alta)},
            **({campo: _valor_de_id(campo, alta.id_externo)} if campo is not None and alta.id_externo else {}),
        )
        try:
            async with db.begin_nested():
                db.add(serie)
                await db.flush()
        except IntegrityError:
            if campo is not None and alta.id_externo is not None:
                existente = await self._por_id_externo(alta.fuente, alta.id_externo)
                if existente is not None:
                    await db.commit()
                    return ResultadoAlta(resultado="reutilizada", serie=_a_serie_local(existente), repetida=False,
                                         motivo="mismo_identificador", deshacer=None)
            raise
        await db.refresh(serie)
        await db.commit()
        return self._resultado_creada(serie, alta.operacion, repetida=False)

    def _procedencia(self, alta: AltaFirmada) -> dict:
        inicio = self._ahora if self._ahora is not None else datetime.now(UTC).timestamp()
        return {
            "version": VERSION_PROCEDENCIA, "origen": alta.origen, "fuente": alta.fuente,
            "id_externo": alta.id_externo, "desde_grupo": alta.clave,
            "fecha": datetime.fromtimestamp(inicio, UTC).isoformat(), "tradicion_elegida": True,
            "operacion_id": alta.operacion,
        }

    @staticmethod
    def _resultado_creada(serie: Series, operacion: str, *, repetida: bool) -> ResultadoAlta:
        return ResultadoAlta(resultado="creada", serie=_a_serie_local(serie), repetida=repetida, motivo=None,
                             deshacer={"series_id": str(serie.id), "operacion_id": operacion})

    # ── Deshacer ─────────────────────────────────────────────────────────────────────────────────

    async def deshacer(self, series_id: UUID, operacion_id: UUID) -> ResultadoDeshacer:
        """Borra la serie SOLO si la creó esa operación y nada depende de ella.

        Protegido frente a concurrencia: `SELECT … FOR UPDATE` sobre la fila de la serie. Quien quiera colgarle
        números (insertar en `issues`, que toma `FOR KEY SHARE` por la clave foránea) espera a este candado o lo
        hace esperar; y como se exige que NO tenga ningún número, un archivo solo puede vincularse a un número
        que antes se creó. Quien vincule archivos a números existentes de esta serie (2d) debe tomar `FOR SHARE`
        sobre la serie antes de comprobar (ficha, bloque D).
        """
        db = self._db
        serie = (await db.execute(select(Series).where(Series.id == series_id).with_for_update())).scalar_one_or_none()
        if serie is None:
            await db.rollback()
            raise SerieNoEncontradaError(str(series_id))
        alta = (serie.metadata_ or {}).get("alta")
        if not isinstance(alta, dict) or alta.get("operacion_id") != str(operacion_id):
            # Ni una serie que ya existía y se reutilizó, ni una creada por otra operación.
            await db.rollback()
            raise NoSePuedeDeshacerError("no_creada_por_esta_operacion")

        async def hay(consulta) -> bool:
            return bool((await db.execute(consulta.limit(1))).first())
        motivo = None
        if await hay(select(File.id).join(Issue, File.issue_id == Issue.id).where(Issue.series_id == series_id)):
            motivo = "tiene_archivos"
        elif await hay(select(Issue.id).where(Issue.series_id == series_id)):
            motivo = "tiene_numeros"
        elif await hay(select(AsignacionOperacion.id).where(
                AsignacionOperacion.series_id == series_id,
                AsignacionOperacion.estado.in_(ASIGNACION_ESTADOS_VIVOS))):
            motivo = "operacion_viva"
        elif serie.wishlist_policy != WishlistPolicy.NONE or await hay(
                select(Wishlist.id).where(Wishlist.series_id == series_id)):
            motivo = "tiene_deseados"
        if motivo is not None:
            await db.rollback()
            raise NoSePuedeDeshacerError(motivo)
        titulo = serie.title
        await db.execute(delete(Series).where(Series.id == series_id))
        await db.commit()
        return ResultadoDeshacer(deshecho=True, series_id=str(series_id), titulo=titulo)

    # ── Consultas ────────────────────────────────────────────────────────────────────────────────

    async def _por_id_externo(self, fuente: str | None, id_externo: str | None) -> Series | None:
        if not fuente or id_externo is None:
            return None
        campo = CAMPO_ID_EXTERNO.get(MetadataSource(fuente))
        if campo is None:
            raise DatosInvalidosError("Esa fuente no puede dar de alta series.")
        valor = _valor_de_id(campo, id_externo)
        return (await self._db.execute(select(Series).where(getattr(Series, campo) == valor))).scalar_one_or_none()

    async def _parecidas(self, titulo: str, anio: int | None, tradicion: ComicTradition, *,
                         excluir: str | None) -> list[SerieParecida]:
        """Mismo título normalizado (el de Postgres, `f_title_norm`), año compatible (±1; un año desconocido no
        descarta) y la MISMA tradición. Orden fijo: año y id."""
        filas = (await self._db.execute(
            select(Series).where(Series.title_norm == func.f_title_norm(titulo), Series.tradition == tradicion)
        )).scalars().all()
        return [SerieParecida(**_a_serie_local(s).model_dump(), motivo=MOTIVO_PARECIDA)
                for s in sorted(filas, key=lambda s: (s.start_year or 0, str(s.id)))
                if _anios_compatibles(anio, s.start_year) and str(s.id) != excluir]
