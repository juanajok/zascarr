# ruff: noqa: E501
"""Descubrimiento contextualizado (rebanada 2a): buscar en las fuentes DESDE un grupo de la superficie de revisión.

Contrato en `docs/design/rebanada-2-elegir-serie-y-vincular.md` (bloque A). Lo que hace: toma un grupo
(`clave`), propone una consulta, reutiliza `DiscoveryService` para consultar las fuentes y, por cada resultado,
añade lo que se calcula EN LOCAL: si ya existe la serie (mismo id externo), qué series locales se le parecen y
si la carpeta corrobora o contradice el resultado (las MISMAS señales de la rebanada 1).

Lo que NO hace: no escribe nada, no crea series, no vincula, no elige ni recomienda. Ningún campo ni orden
indica «la mejor»; el orden es el fijo de las fuentes y luego el título. La red solo se usa dentro de
`descubrir()`, que solo se invoca a petición (botón), nunca al abrir el grupo.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.core.carpetas import analizar_carpeta
from zascarr.core.matcher import normalize_title
from zascarr.models import Series
from zascarr.services.discovery import (
    CAMPO_ID_EXTERNO,
    CAMPOS_ID_DE_TEXTO,
    ORDEN_DE_FUENTES,
    Busqueda,
    DiscoveryResult,
    DiscoveryService,
)
from zascarr.services.revision_carpetas import RevisionCarpetas, Senal, senales_contra_serie
from zascarr.services.tokens_revision import (
    CandidataFirmada,
    candidata_firmable,
    crear_token_candidata,
    texto_firmable,
)
from zascarr.utils.url_portada import es_url_de_portada_permitida

MAX_DESCRIPCION_VISTA = 300
MOTIVO_PARECIDA = "Mismo título normalizado y un año compatible, pero sin ese identificador externo."


class GrupoNoEncontradoError(LookupError):
    """No hay registros pendientes en esa carpeta (puede haberse vinculado o descartado ya)."""


class ConsultaVaciaError(ValueError):
    """No hay consulta posible: ni la persona la dio ni la carpeta ni los nombres permiten proponer una."""


# ── Contrato de salida ────────────────────────────────────────────────────────────────────────

class SerieLocal(BaseModel):
    series_id: str
    titulo: str
    anio: int | None
    tradicion: str


class SerieParecida(SerieLocal):
    motivo: str


class Coincidencia(BaseModel):
    en_conflicto: bool
    senales: list[Senal]


class Candidata(BaseModel):
    token: str
    fuente: str
    titulo: str
    anio: int | None
    tradicion_sugerida: str
    sitio_url: str | None
    portada: str | None
    descripcion: str | None
    ya_en_biblioteca: SerieLocal | None
    parecidas_locales: list[SerieParecida]
    coincidencia_con_la_carpeta: Coincidencia


class GrupoResumen(BaseModel):
    clave: str
    carpeta_contextual: str | None
    n_archivos: int


class RespuestaDescubrir(BaseModel):
    consulta: str
    consulta_propuesta: str
    grupo: GrupoResumen
    fuentes: dict[str, str]
    avisos: list[str]
    candidatas: list[Candidata]


@dataclass
class _Preparado:
    """Un resultado de una fuente ya depurado: `firmable` es lo que se firma, se consulta y se muestra."""
    resultado: DiscoveryResult
    firmable: CandidataFirmada
    sitio_url: str | None


@dataclass
class _Locales:
    por_id: dict[tuple[str, str], Series]
    por_titulo: dict[str, list[Series]]


def _a_serie_local(s: Series) -> SerieLocal:
    return SerieLocal(series_id=str(s.id), titulo=s.title, anio=s.start_year, tradicion=s.tradition.value)


def _anios_compatibles(a: int | None, b: int | None) -> bool:
    """Un año desconocido no descarta (se avisa de más antes que de menos); dos conocidos, a ±1."""
    return a is None or b is None or abs(a - b) <= 1


class DescubrimientoDeGrupo:
    def __init__(self, db: AsyncSession, descubridor: DiscoveryService | None = None,
                 *, secret: str, ahora: float | None = None):
        self._db = db
        self._descubridor = descubridor or DiscoveryService(db)
        self._secret = secret
        self._ahora = ahora

    async def descubrir(self, clave: str, consulta: str | None) -> RespuestaDescubrir:
        grupo = await RevisionCarpetas(self._db).archivos_del_grupo(clave)
        if grupo is None:
            raise GrupoNoEncontradoError(clave)
        div, archivos = grupo
        carpeta = analizar_carpeta(div.contextual) if div.contextual else None
        propuesta = self._consulta_propuesta(carpeta, archivos)
        usada = (consulta or "").strip() or propuesta
        if not usada:
            raise ConsultaVaciaError()

        busqueda = await self._descubridor.search_detallada(usada)
        # Primero se PREPARA cada resultado (lo que se firmará, se mostrará y se usará en las consultas), y solo después
        # se consulta la base: un resultado que no se puede dar de alta (título o identificador que no caben en lo que se
        # guarda, o con caracteres no firmables) no llega a ninguna consulta, ni a la BD ni al token. Se avisa, no se calla.
        preparados, omitidas = self._preparar(self._ordenar(busqueda))
        locales = await self._buscar_locales(preparados)
        avisos = list(busqueda.avisos)
        if omitidas:
            avisos.append(f"Se han omitido {omitidas} resultado(s) cuyo título o identificador no se puede guardar "
                          "(demasiado largo o con caracteres no válidos).")
        return RespuestaDescubrir(
            consulta=usada, consulta_propuesta=propuesta,
            grupo=GrupoResumen(clave=clave, carpeta_contextual=div.contextual, n_archivos=len(archivos)),
            fuentes=busqueda.fuentes, avisos=avisos,
            candidatas=[self._candidata(clave, p, locales, carpeta, archivos, bool(div.contextual))
                        for p in preparados],
        )

    # ── Piezas ─────────────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _consulta_propuesta(carpeta, archivos) -> str:
        """La carpeta limpia manda; si no hay carpeta de serie, el título que dominan los nombres.
        Un «título» sin ninguna letra (el parser da «01» para `01.cbz`) no es una consulta: no se propone."""
        candidatos = [carpeta.titulo if carpeta is not None else "",
                      RevisionCarpetas._patron(archivos).titulo_dominante or ""]
        return next((t for t in candidatos if t and any(c.isalpha() for c in t)), "")

    @staticmethod
    def _ordenar(b: Busqueda) -> list[DiscoveryResult]:
        """Orden NEUTRO y determinista: el fijo de las fuentes y luego el título. Nunca «la mejor primero»."""
        orden = {f: i for i, f in enumerate(ORDEN_DE_FUENTES)}
        return sorted(b.resultados, key=lambda r: (orden.get(r.source, 99), r.title.casefold(), r.external_id))

    @staticmethod
    def _preparar(resultados: list[DiscoveryResult]) -> tuple[list[_Preparado], int]:
        """(resultados utilizables, cuántos se omitieron). La portada solo sale si cumple la política de H1 (y por el
        proxy con lista blanca, nunca `src` externo); la URL de la ficha se muestra solo si es texto firmable."""
        preparados: list[_Preparado] = []
        for r in resultados:
            portada_ok = bool(r.cover_url) and es_url_de_portada_permitida(r.cover_url or "")
            firmable = candidata_firmable(
                r.source.value, r.external_id, r.title, r.start_year, r.tradition_guess.value, r.description,
                r.cover_url if portada_ok else None)
            if firmable is None:
                continue
            sitio = r.site_url if r.site_url is None or texto_firmable(r.site_url) else None
            preparados.append(_Preparado(r, firmable, sitio))
        return preparados, len(resultados) - len(preparados)

    async def _buscar_locales(self, preparados: list[_Preparado]) -> _Locales:
        """Dos consultas, vengan 3 resultados o 40: por identificador externo y por título normalizado."""
        ids: dict[str, set] = {}
        for p in preparados:
            campo = CAMPO_ID_EXTERNO.get(p.resultado.source)
            if campo is None:
                continue
            valor: int | str | None
            if campo in CAMPOS_ID_DE_TEXTO:
                valor = p.firmable.id_externo
            else:
                try:
                    valor = int(p.firmable.id_externo)
                except ValueError:
                    valor = None
            if valor is not None:
                ids.setdefault(campo, set()).add(valor)

        por_id: dict[tuple[str, str], Series] = {}
        if ids:
            condiciones = [getattr(Series, campo).in_(valores) for campo, valores in ids.items()]
            for s in (await self._db.execute(select(Series).where(or_(*condiciones)))).scalars().all():
                for campo in ids:
                    v = getattr(s, campo)
                    if v is not None:
                        por_id[(campo, str(v))] = s

        normas = {n for p in preparados if (n := normalize_title(p.firmable.titulo))}
        por_titulo: dict[str, list[Series]] = {}
        if normas:
            for s in (await self._db.execute(select(Series).where(Series.title_norm.in_(normas)))).scalars().all():
                por_titulo.setdefault(s.title_norm or "", []).append(s)
        return _Locales(por_id, por_titulo)

    def _candidata(self, clave: str, p: _Preparado, locales: _Locales, carpeta, archivos,
                   tiene_contexto: bool) -> Candidata:
        r, firmable = p.resultado, p.firmable
        campo = CAMPO_ID_EXTERNO.get(r.source)
        ya = locales.por_id.get((campo, firmable.id_externo)) if campo else None
        parecidas = [
            SerieParecida(**_a_serie_local(s).model_dump(), motivo=MOTIVO_PARECIDA)
            for s in sorted(locales.por_titulo.get(normalize_title(firmable.titulo), []),
                            key=lambda s: (s.start_year or 0, str(s.id)))
            if (ya is None or s.id != ya.id) and _anios_compatibles(firmable.anio, s.start_year)
        ]
        senales = senales_contra_serie(archivos, carpeta, firmable.titulo, firmable.anio, tiene_contexto=tiene_contexto)

        cover = firmable.cover_url
        token = crear_token_candidata(clave, firmable, self._secret, ahora=self._ahora)
        return Candidata(
            token=token, fuente=r.source.value, titulo=firmable.titulo, anio=firmable.anio,
            tradicion_sugerida=r.tradition_guess.value, sitio_url=p.sitio_url,
            portada=None if cover is None else "/ui/descubrir/portada?" + urlencode({"url": cover, "source": r.source.value}),
            descripcion=(firmable.descripcion or "")[:MAX_DESCRIPCION_VISTA] or None,
            ya_en_biblioteca=_a_serie_local(ya) if ya is not None else None,
            parecidas_locales=parecidas,
            coincidencia_con_la_carpeta=Coincidencia(
                en_conflicto=any(s.severidad == "conflicto" for s in senales), senales=senales),
        )

