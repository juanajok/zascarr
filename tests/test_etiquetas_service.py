# ruff: noqa: E501
"""
tests/test_etiquetas_service.py

Lógica pura y de sesión de `services/etiquetas.py` (BL-ETQ1a, #403). Sin Postgres real: la
paridad con `f_tag_norm` vive en `test_tag_norm_pg.py` y la migración en
`test_etiquetas_migracion_pg.py`. Aquí se comprueban las reglas de normalización/validación,
la precedencia de autoría y el comportamiento del servicio con una sesión falsa (colas).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from zascarr.services.etiquetas import (
    EtiquetaDeSerie,
    EtiquetasService,
    NombreDeEtiquetaInvalidoError,
    Sugerencia,
    clave_de,
    normalize_tag,
    puede_escribir,
    validar_nombre,
)

# ── FakeSession (mismo patrón de colas que test_web_series.py) ────────────────

class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeExecResult:
    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return FakeScalarResult(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class FakeSession:
    """`execute` consume una cola de `FakeExecResult`; `add` y `flush` se registran para afirmar
    sobre ellos. `flush` puede lanzar si se programa (rama de carrera)."""

    def __init__(self, queue):
        self._queue = list(queue)
        self.flush = AsyncMock()
        self.rollback = AsyncMock()
        self.added: list = []

    async def execute(self, _statement):
        return self._queue.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def get(self, _model, _id):
        return None


def _tag(clave: str = "noir"):
    return SimpleNamespace(id=uuid4(), clave=clave)


def _asignacion(source: str = "manual", oculta: bool = False):
    return SimpleNamespace(source=source, oculta=oculta)


# ── Normalización y validación ────────────────────────────────────────────────

class TestNormalizar:

    @pytest.mark.parametrize("entrada,esperado", [
        ("Noir", "noir"),
        ("NOIR", "noir"),
        ("Nóir", "noir"),
        ("  Noir   ", "noir"),
        ("The Walking Dead", "the walking dead"),          # conserva el artículo
        ("S.H.I.E.L.D.", "s h i e l d"),                   # no colapsa puntos entre letras
        ("space-opera", "space opera"),
        ("space opera", "space opera"),
        ("España", "espana"),                              # ñ → n (unaccent)
        ("Müller", "muller"),                              # ü → u
        ("Café, Té y Más", "cafe te y mas"),
        ("¡Ataque!", "ataque"),
        ("   varios    espacios   ", "varios espacios"),
        ("trazo-bajo_x", "trazo bajo x"),                  # guion y subrayado → espacio
        # Letras que `unaccent` translitera y NFKD no descompone: la tabla corta mantiene la
        # paridad con f_tag_norm (ver test_tag_norm_pg.py).
        ("Smørrebrød", "smorrebrod"),
        ("Æon Flux", "aeon flux"),
        ("Straße", "strasse"),
        ("ẞ", "ss"),
        ("Łódź", "lodz"),
        ("Đà Nẵng", "da nang"),
        ("Þór", "thor"),
        ("ı", "i"),
    ])
    def test_normaliza(self, entrada, esperado):
        assert normalize_tag(entrada) == esperado

    def test_clave_de_sustituye_espacios_por_guiones(self):
        assert clave_de("space opera") == "space-opera"
        assert clave_de("noir") == "noir"


class TestValidarNombre:

    def test_nombre_valido_se_normaliza(self):
        assert validar_nombre("  Nóir  ") == "noir"

    def test_espacios_internos_se_conservan(self):
        assert validar_nombre("Space Opera") == "space opera"

    @pytest.mark.parametrize("nombre", [
        "",
        "   ",
        "…",
        "!!!",
    ])
    def test_nombre_vacio_o_sin_letras_se_rechaza(self, nombre):
        with pytest.raises(NombreDeEtiquetaInvalidoError):
            validar_nombre(nombre)

    def test_demasiado_largo_se_rechaza(self):
        with pytest.raises(NombreDeEtiquetaInvalidoError) as exc:
            validar_nombre("a" * 65)
        assert "64" in str(exc.value)

    @pytest.mark.parametrize("nombre", ["a,b", "a\nb", "a\rb", "a\tb", "a\x00b"])
    def test_coma_salto_o_control_se_rechazan(self, nombre):
        with pytest.raises(NombreDeEtiquetaInvalidoError):
            validar_nombre(nombre)


class TestPuedeEscribir:

    def test_la_escritura_manual_siempre_puede(self):
        assert puede_escribir(_asignacion(source="manual"), "manual") is True

    def test_un_escritor_automatico_no_toca_una_fila_manual(self):
        assert puede_escribir(_asignacion(source="manual"), "comicinfo_xml") is False
        assert puede_escribir(_asignacion(source="manual"), "anilist") is False

    def test_un_escritor_automatico_si_toca_una_fila_no_manual(self):
        assert puede_escribir(_asignacion(source="comicinfo_xml"), "anilist") is True

    def test_sin_fila_se_puede_crear(self):
        assert puede_escribir(None, "comic_vine") is True


# ── Servicio con sesión falsa ─────────────────────────────────────────────────

class TestDeSerie:

    async def test_devuelve_etiquetas_visibles_ordenadas(self):
        sesion = FakeSession([FakeExecResult([_tag("noir"), _tag("space-opera")])])
        servicio = EtiquetasService(sesion)
        assert await servicio.de_serie(uuid4()) == [
            EtiquetaDeSerie(clave="noir"),
            EtiquetaDeSerie(clave="space-opera"),
        ]


class TestSugerir:

    async def test_prefijo_normalizado_con_recuento(self):
        sesion = FakeSession([FakeExecResult([("noir", 34), ("noir-back", 3)])])
        servicio = EtiquetasService(sesion)
        assert await servicio.sugerir(uuid4(), "Nó") == [
            Sugerencia(clave="noir", series=34),
            Sugerencia(clave="noir-back", series=3),
        ]

    async def test_texto_que_normaliza_a_vacio_no_consulta(self):
        sesion = FakeSession([])  # si consultara, estallaría al quedarse sin cola
        servicio = EtiquetasService(sesion)
        assert await servicio.sugerir(uuid4(), "!!!") == []


class TestAnadir:

    async def test_anade_etiqueta_existente(self):
        tag = _tag("noir")
        sesion = FakeSession([FakeExecResult([tag]), FakeExecResult([]), FakeExecResult(None)])
        servicio = EtiquetasService(sesion)
        resultado = await servicio.anadir(uuid4(), "noir")
        assert resultado.ok is True and resultado.aviso == "Etiqueta añadida."
        assert sesion.flush.await_count >= 1

    async def test_duplicada_visible_no_se_vuelve_a_anadir(self):
        tag = _tag("noir")
        sesion = FakeSession([FakeExecResult([tag]), FakeExecResult([_asignacion()])])
        resultado = await EtiquetasService(sesion).anadir(uuid4(), "noir")
        assert resultado.ok is False
        assert resultado.aviso == "Esa etiqueta ya estaba en la serie."

    async def test_inexistente_sin_crear_se_rechaza(self):
        sesion = FakeSession([FakeExecResult([])])
        resultado = await EtiquetasService(sesion).anadir(uuid4(), "noirx")
        assert resultado.ok is False
        assert resultado.aviso == "Esa etiqueta no existe. Elige una de las sugerencias."

    async def test_crear_crea_y_anade(self):
        sesion = FakeSession([FakeExecResult([]), FakeExecResult([]), FakeExecResult(None)])
        resultado = await EtiquetasService(sesion).anadir(uuid4(), "noirx", crear=True)
        assert resultado.ok is True and resultado.aviso == "Etiqueta añadida."
        assert len(sesion.added) == 1
        assert sesion.added[0].namespace == "etiqueta" and sesion.added[0].name == "noirx"

    async def test_la_carrera_al_crear_no_duplica_ni_propaga_la_excepcion(self):
        """Dos peticiones crean el mismo nombre a la vez: la perdedora del UNIQUE no puede
        duplicar la fila ni romper la respuesta; se le dice que ya existe."""
        sesion = FakeSession([FakeExecResult([])])
        sesion.flush.side_effect = IntegrityError("INSERT", {}, Exception("duplicado"))
        resultado = await EtiquetasService(sesion).anadir(uuid4(), "noirx", crear=True)
        assert resultado.ok is False
        assert resultado.aviso == "Esa etiqueta ya existe: noirx"
        assert sesion.rollback.await_count == 1

    async def test_crear_un_nombre_que_ya_existe_se_rechaza(self):
        tag = _tag("noir")
        sesion = FakeSession([FakeExecResult([tag])])
        resultado = await EtiquetasService(sesion).anadir(uuid4(), "Nóir", crear=True)
        assert resultado.ok is False
        assert resultado.aviso == "Esa etiqueta ya existe: noir"

    async def test_nombre_invalido_no_escribe(self):
        sesion = FakeSession([])
        resultado = await EtiquetasService(sesion).anadir(uuid4(), "a,b")
        assert resultado.ok is False
        assert sesion.added == []


class TestQuitar:

    async def test_quitar_manual_borra(self):
        tag = _tag("noir")
        sesion = FakeSession([
            FakeExecResult([tag]), FakeExecResult([_asignacion(source="manual")]), FakeExecResult(None),
        ])
        resultado = await EtiquetasService(sesion).quitar(uuid4(), "noir")
        assert resultado.ok is True and resultado.aviso == "Etiqueta quitada."
        assert sesion.flush.await_count >= 1

    async def test_quitar_una_fila_de_fuente_la_oculta(self):
        tag = _tag("noir")
        sesion = FakeSession([
            FakeExecResult([tag]),
            FakeExecResult([_asignacion(source="comicinfo_xml")]),
            FakeExecResult(None),
        ])
        resultado = await EtiquetasService(sesion).quitar(uuid4(), "noir")
        assert resultado.ok is True and resultado.aviso == "Etiqueta quitada."

    async def test_quitar_una_etiqueta_que_no_esta_se_rechaza(self):
        tag = _tag("noir")
        sesion = FakeSession([FakeExecResult([tag]), FakeExecResult([])])
        resultado = await EtiquetasService(sesion).quitar(uuid4(), "noir")
        assert resultado.ok is False
        assert resultado.aviso == "Esa etiqueta no estaba en la serie."

    async def test_quitar_una_etiqueta_inexistente_se_rechaza(self):
        sesion = FakeSession([FakeExecResult([])])
        resultado = await EtiquetasService(sesion).quitar(uuid4(), "noirx")
        assert resultado.ok is False
        assert resultado.aviso == "Esa etiqueta no existe. Elige una de las sugerencias."
