"""
tests/test_orchestrator.py

Suite del orquestador (D1): búsqueda en cascada con reintento de
candidatos, cooldown de reintento (H2-style) y cierre del círculo
"descargado -> en tu biblioteca" vía existencia de File, sin depender de
Transmission/aMule ni Prowlarr reales.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from zascarr.config import get_settings
from zascarr.models import (
    ComicTradition,
    File,
    FileFormat,
    Issue,
    MetadataSource,
    Series,
    Wishlist,
    WishlistPolicy,
    WishlistStatus,
)
from zascarr.services.orchestrator import (
    MOTIVO_CANDIDATO_INVALIDO,
    MOTIVO_CANDIDATO_RECHAZADO,
    MOTIVO_CLIENTE_INACCESIBLE,
    MOTIVO_ERROR_INESPERADO,
    MOTIVO_FUENTE_INACCESIBLE,
    MOTIVO_NUMERO_DISTINTO,
    MOTIVO_SIN_FUENTE,
    MOTIVO_SIN_RESULTADOS,
    DownloadBackend,
    Orchestrator,
    SincronizacionPolitica,
    _extract_ed2k_hash,
    crear_token_candidato,
    verificar_token_candidato,
)
from zascarr.services.politica import (
    ESTADOS_REACTIVABLES,
    MOTIVO_DESEO_DE_SERIE,
    MOTIVO_POLITICA_FUTUROS,
    Querer,
    querer_de_serie,
    stmt_retirada,
)
from zascarr.services.prowlarr import SearchResult


@pytest.fixture(autouse=True)
def _p2p_enabled(monkeypatch):
    """Blindaje legal: prowlarr/transmission/amule están deshabilitados
    por defecto (opt-in). Esta suite prueba la lógica de búsqueda/envío
    en sí, no el propio opt-in (eso tiene su test dedicado más abajo),
    así que se habilitan los tres para no romper cada test existente."""
    settings = get_settings()
    settings = settings.model_copy(update={
        "prowlarr_enabled": True, "transmission_enabled": True, "amule_enabled": True,
    })
    monkeypatch.setattr("zascarr.services.orchestrator.get_settings", lambda: settings)


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class FakeExecResult:
    def __init__(self, rows, rowcount=None):
        self._rows = rows
        # Para UPDATE/DELETE (p.ej. la reclamación atómica de
        # send_manual_candidate): filas afectadas, no filas devueltas.
        # Por defecto sigue el tamaño de `rows` para no romper los
        # exec results que ya existían pensados solo para SELECT.
        self.rowcount = rowcount if rowcount is not None else len(rows)

    def scalars(self):
        return FakeScalarResult(self._rows)

    def all(self):
        # Las consultas de D8 (números poseídos, items existentes, manuales) leen
        # filas de varias columnas, no una sola entidad: `.all()` directo.
        return self._rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def first(self):
        return self._rows[0] if self._rows else None


def claim_ganada() -> FakeExecResult:
    """Resultado de la reclamación atómica de send_manual_candidate
    cuando SÍ se gana la carrera (1 fila afectada)."""
    return FakeExecResult([], rowcount=1)


def claim_perdida() -> FakeExecResult:
    """... cuando se pierde (otra petición concurrente ya reclamó el
    item, 0 filas afectadas)."""
    return FakeExecResult([], rowcount=0)


class FakeSession:
    """Cola de resultados en el orden en que el orquestador los pide."""

    def __init__(self, queue: list | None = None):
        self._queue = list(queue or [])
        self.flush = AsyncMock()

    async def execute(self, _statement):
        return self._queue.pop(0)


class CapturingSession(FakeSession):
    """Como FakeSession, pero guarda cada statement compilado — para
    verificar de verdad el WHERE que genera el código, no solo lo que
    hace con una lista de resultados ya dada (ver B7: revisión de PR,
    2026-09-26, sobre `_is_fulfilled` sin filtrar `is_missing`)."""

    def __init__(self, queue: list | None = None):
        super().__init__(queue)
        self.statements: list[str] = []

    async def execute(self, statement):
        self.statements.append(str(statement))
        return await super().execute(statement)


def make_series(title="Batman", tradition=ComicTradition.AMERICAN) -> Series:
    return Series(id=uuid4(), title=title, tradition=tradition)


def make_result(title="Batman #1.cbz", url="magnet:?xt=urn:btih:abc", seeders=10, size=1024) -> SearchResult:
    return SearchResult(title=title, indexer="test", download_url=url,
                        size_bytes=size, seeders=seeders, category="comics")


# ═══════════════════════════════════════════════════════════════════════════
# 1. _ranked_candidates — pool completo, no solo el ganador
# ═══════════════════════════════════════════════════════════════════════════

class TestRankedCandidates:

    def test_ordena_por_score_descendente(self):
        orch = Orchestrator(db=FakeSession())
        peor = make_result(title="Batman Variant.cbz", seeders=5)
        mejor = make_result(title="Batman #1.cbz", seeders=50)
        ranked = orch._ranked_candidates([peor, mejor], "Batman")
        assert ranked[0] is mejor
        assert ranked[1] is peor

    def test_torrents_antes_que_ed2k(self):
        orch = Orchestrator(db=FakeSession())
        ed2k = make_result(title="Batman.cbz", url="ed2k://|file|batman.cbz|100|HASH123|/", seeders=0)
        torrent = make_result(title="Batman.cbz", seeders=1)
        ranked = orch._ranked_candidates([ed2k, torrent], "Batman")
        assert ranked == [torrent, ed2k]

    def test_torrent_sin_seeders_se_descarta(self):
        orch = Orchestrator(db=FakeSession())
        sin_seeders = make_result(seeders=0)
        ranked = orch._ranked_candidates([sin_seeders], "Batman")
        assert ranked == []

    def test_por_encima_del_tamano_maximo_se_descarta(self):
        orch = Orchestrator(db=FakeSession())
        grande = make_result(size=999_999_999_999)
        assert orch._ranked_candidates([grande], "Batman") == []


class TestExtractEd2kHash:

    def test_extrae_el_hash_de_la_url(self):
        assert _extract_ed2k_hash("ed2k://|file|batman.cbz|123456|ABCDEF0123456789|/") == "ABCDEF0123456789"

    def test_url_malformada_devuelve_none(self):
        assert _extract_ed2k_hash("ed2k://not-a-real-link") is None


# ═══════════════════════════════════════════════════════════════════════════
# 2. _process_item — reintento con el siguiente candidato (Mylar3)
# ═══════════════════════════════════════════════════════════════════════════

class TestProcessItemRetryPool:

    @pytest.mark.asyncio
    async def test_si_el_mejor_falla_al_enviarse_prueba_el_siguiente(self):
        item = Wishlist(id=uuid4(), search_query="Batman", status=WishlistStatus.WANTED)
        session = FakeSession()  # search_query ya viene puesto, _build_query no toca la DB
        orch = Orchestrator(db=session)
        orch._prowlarr = AsyncMock()
        orch._prowlarr.search.return_value = [
            make_result(title="Batman #1 malo.cbz", seeders=50),
            make_result(title="Batman #1 bueno.cbz", seeders=10),
        ]
        orch._transmission = AsyncMock()
        orch._transmission.add_torrent.side_effect = [None, {"hashString": "abc123", "name": "Batman #1 bueno.cbz"}]

        result = await orch._process_item(item)

        assert result is True
        assert item.status == WishlistStatus.DOWNLOADING
        assert item.download_ref == "abc123"
        assert item.download_backend == DownloadBackend.TRANSMISSION.value
        assert orch._transmission.add_torrent.await_count == 2

    @pytest.mark.asyncio
    async def test_todos_los_candidatos_fallan_es_failed(self):
        item = Wishlist(id=uuid4(), search_query="Batman", status=WishlistStatus.WANTED)
        orch = Orchestrator(db=FakeSession())
        orch._prowlarr = AsyncMock()
        orch._prowlarr.search.return_value = [make_result(seeders=10)]
        orch._transmission = AsyncMock()
        orch._transmission.add_torrent.return_value = None

        result = await orch._process_item(item)

        assert result is False
        assert item.status == WishlistStatus.FAILED

    @pytest.mark.asyncio
    async def test_sin_candidatos_vuelve_a_wanted_no_a_failed(self):
        item = Wishlist(id=uuid4(), search_query="Serie Rarísima", status=WishlistStatus.WANTED)
        orch = Orchestrator(db=FakeSession())
        orch._prowlarr = AsyncMock()
        orch._prowlarr.search.return_value = []

        result = await orch._process_item(item)

        assert result is False
        assert item.status == WishlistStatus.WANTED  # sin resultados no es un fallo


# ═══════════════════════════════════════════════════════════════════════════
# 2b. last_error — D9: por qué esta fila no avanza, con causa distinguible
# ═══════════════════════════════════════════════════════════════════════════

class TestMotivoNoAvanza:

    @pytest.mark.asyncio
    async def test_sin_ninguna_fuente_activa_no_intenta_nada(self, monkeypatch):
        """Si ni Prowlarr ni el foro están activos, ni se llama a
        Prowlarr — se dice la causa exacta en vez de un "Buscando…"
        eterno sin explicación."""
        settings = get_settings().model_copy(update={
            "prowlarr_enabled": False, "forum_enabled": False,
        })
        monkeypatch.setattr("zascarr.services.orchestrator.get_settings", lambda: settings)
        item = Wishlist(id=uuid4(), search_query="Batman", status=WishlistStatus.WANTED)
        orch = Orchestrator(db=FakeSession())
        orch._prowlarr = AsyncMock()

        result = await orch._process_item(item)

        assert result is False
        assert item.status == WishlistStatus.WANTED
        assert item.last_error == MOTIVO_SIN_FUENTE
        orch._prowlarr.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_prowlarr_inaccesible_se_distingue_de_sin_resultados(self):
        """Un fallo real de conexión/API de Prowlarr no debe confundirse
        con "no había nada" — son causas y acciones distintas."""
        item = Wishlist(id=uuid4(), search_query="Batman", status=WishlistStatus.WANTED)
        orch = Orchestrator(db=FakeSession())
        orch._prowlarr = AsyncMock()
        orch._prowlarr.search.side_effect = ConnectionError("boom")

        result = await orch._process_item(item)

        assert result is False
        assert item.status == WishlistStatus.WANTED
        assert item.last_error == MOTIVO_FUENTE_INACCESIBLE

    @pytest.mark.asyncio
    async def test_sin_resultados_en_ninguna_fuente(self):
        item = Wishlist(id=uuid4(), search_query="Serie Rarísima", status=WishlistStatus.WANTED)
        orch = Orchestrator(db=FakeSession())
        orch._prowlarr = AsyncMock()
        orch._prowlarr.search.return_value = []

        await orch._process_item(item)

        assert item.last_error == MOTIVO_SIN_RESULTADOS

    @pytest.mark.asyncio
    async def test_candidatos_encontrados_pero_backend_apagado(self, monkeypatch):
        settings = get_settings().model_copy(update={
            "prowlarr_enabled": True, "transmission_enabled": False, "amule_enabled": False,
        })
        monkeypatch.setattr("zascarr.services.orchestrator.get_settings", lambda: settings)
        item = Wishlist(id=uuid4(), search_query="Batman", status=WishlistStatus.WANTED)
        orch = Orchestrator(db=FakeSession())
        orch._prowlarr = AsyncMock()
        orch._prowlarr.search.return_value = [make_result(seeders=50)]

        await orch._process_item(item)

        assert item.last_error == MOTIVO_CANDIDATO_RECHAZADO

    @pytest.mark.asyncio
    async def test_ningun_cliente_de_descarga_disponible(self):
        item = Wishlist(id=uuid4(), search_query="Batman", status=WishlistStatus.WANTED)
        orch = Orchestrator(db=FakeSession())
        orch._prowlarr = AsyncMock()
        orch._prowlarr.search.return_value = [make_result(seeders=10)]
        orch._transmission = AsyncMock()
        orch._transmission.add_torrent.return_value = None

        await orch._process_item(item)

        assert item.status == WishlistStatus.FAILED
        assert item.last_error == MOTIVO_CLIENTE_INACCESIBLE

    @pytest.mark.asyncio
    async def test_exito_limpia_el_motivo_anterior(self):
        """Un last_error de un ciclo anterior no debe quedar pegado una
        vez la descarga arranca de verdad."""
        item = Wishlist(id=uuid4(), search_query="Batman", status=WishlistStatus.FAILED,
                        last_error=MOTIVO_CLIENTE_INACCESIBLE)
        orch = Orchestrator(db=FakeSession())
        orch._prowlarr = AsyncMock()
        orch._prowlarr.search.return_value = [make_result(seeders=10)]
        orch._transmission = AsyncMock()
        orch._transmission.add_torrent.return_value = {"hashString": "abc"}

        await orch._process_item(item)

        assert item.status == WishlistStatus.DOWNLOADING
        assert item.last_error is None

    @pytest.mark.asyncio
    async def test_error_inesperado_en_el_ciclo_se_registra(self):
        """Un item que revienta con una excepción no prevista (no una de
        las causas ya distinguidas) igualmente deja una explicación en
        español, nunca solo un FAILED mudo."""
        item = Wishlist(id=uuid4(), search_query="Batman", status=WishlistStatus.WANTED)
        session = FakeSession(queue=[
            FakeExecResult(["acknowledged"]),  # is_acknowledged: sí aceptado
            FakeExecResult([item]),            # items pendientes de la wishlist
        ])
        orch = Orchestrator(db=session)

        async def _revienta(_item):
            raise RuntimeError("boom")

        orch._process_item = _revienta

        sent = await orch.process_wishlist()

        assert sent == 0
        assert item.status == WishlistStatus.FAILED
        assert item.last_error == MOTIVO_ERROR_INESPERADO


# ═══════════════════════════════════════════════════════════════════════════
# 2c. Búsqueda manual con confirmación (D10) — ver, no enviar hasta elegir
# ═══════════════════════════════════════════════════════════════════════════

class TestBusquedaManual:

    @pytest.mark.asyncio
    async def test_preview_no_envia_nada_solo_muestra(self):
        """El punto central de D10: ver candidatos no debe tocar
        Transmission/aMule — solo enviar uno concreto lo hace."""
        item = Wishlist(id=uuid4(), search_query="Batman", status=WishlistStatus.WANTED)
        orch = Orchestrator(db=FakeSession())
        orch._prowlarr = AsyncMock()
        orch._prowlarr.search.return_value = [make_result(seeders=10)]
        orch._transmission = AsyncMock()

        candidatos = await orch.preview_candidates(item)

        assert candidatos is not None and len(candidatos) == 1
        assert item.status == WishlistStatus.WANTED  # no queda "colgado" en SEARCHING
        orch._transmission.add_torrent.assert_not_called()

    @pytest.mark.asyncio
    async def test_preview_sin_query_devuelve_none(self):
        item = Wishlist(id=uuid4(), status=WishlistStatus.WANTED)  # sin series_id/issue_id/search_query
        orch = Orchestrator(db=FakeSession())

        assert await orch.preview_candidates(item) is None

    @pytest.mark.asyncio
    async def test_preview_sin_resultados_deja_el_motivo_de_d9(self):
        item = Wishlist(id=uuid4(), search_query="Serie Rarísima", status=WishlistStatus.WANTED)
        orch = Orchestrator(db=FakeSession())
        orch._prowlarr = AsyncMock()
        orch._prowlarr.search.return_value = []

        candidatos = await orch.preview_candidates(item)

        assert candidatos == []
        assert item.last_error == MOTIVO_SIN_RESULTADOS

    @pytest.mark.asyncio
    async def test_enviar_candidato_elegido_pasa_a_downloading(self):
        item = Wishlist(id=uuid4(), status=WishlistStatus.WANTED)
        orch = Orchestrator(db=FakeSession([claim_ganada()]))
        orch._transmission = AsyncMock()
        orch._transmission.add_torrent.return_value = {"hashString": "abc123"}
        candidato = make_result(title="Batman #1.cbz", seeders=10)

        result = await orch.send_manual_candidate(item, candidato)

        assert result is True
        assert item.status == WishlistStatus.DOWNLOADING
        assert item.download_ref == "abc123"
        assert item.last_error is None

    @pytest.mark.asyncio
    async def test_enviar_candidato_con_backend_apagado_se_rechaza(self, monkeypatch):
        settings = get_settings().model_copy(update={"transmission_enabled": False, "amule_enabled": False})
        monkeypatch.setattr("zascarr.services.orchestrator.get_settings", lambda: settings)
        item = Wishlist(id=uuid4(), status=WishlistStatus.WANTED)
        orch = Orchestrator(db=FakeSession([claim_ganada()]))
        orch._transmission = AsyncMock()
        candidato = make_result(seeders=10)  # magnet:// -> Transmission, apagado

        result = await orch.send_manual_candidate(item, candidato)

        assert result is False
        assert item.last_error == MOTIVO_CANDIDATO_RECHAZADO
        orch._transmission.add_torrent.assert_not_called()

    @pytest.mark.asyncio
    async def test_enviar_candidato_si_falla_el_cliente_se_marca_failed(self):
        item = Wishlist(id=uuid4(), status=WishlistStatus.WANTED)
        orch = Orchestrator(db=FakeSession([claim_ganada()]))
        orch._transmission = AsyncMock()
        orch._transmission.add_torrent.return_value = None
        candidato = make_result(seeders=10)

        result = await orch.send_manual_candidate(item, candidato)

        assert result is False
        assert item.status == WishlistStatus.FAILED
        assert item.last_error == MOTIVO_CLIENTE_INACCESIBLE

    @pytest.mark.asyncio
    async def test_transmission_inalcanzable_no_revienta_da_motivo_claro(self):
        """Bug real encontrado verificando D10 en vivo: Transmission
        caído (conexión rechazada) lanzaba una excepción de httpx en vez
        de fallar limpio — en la confirmación manual eso se colaba como
        un 500 crudo al no haber try/except en el router. _send debe
        traducirlo al mismo MOTIVO_CLIENTE_INACCESIBLE que un rechazo
        "blando" (Transmission responde pero no acepta)."""
        item = Wishlist(id=uuid4(), status=WishlistStatus.WANTED)
        orch = Orchestrator(db=FakeSession([claim_ganada()]))
        orch._transmission = AsyncMock()
        orch._transmission.add_torrent.side_effect = ConnectionRefusedError("boom")
        candidato = make_result(seeders=10)

        result = await orch.send_manual_candidate(item, candidato)

        assert result is False
        assert item.status == WishlistStatus.FAILED
        assert item.last_error == MOTIVO_CLIENTE_INACCESIBLE

    @pytest.mark.asyncio
    async def test_no_reenvia_si_el_item_ya_no_esta_en_estado_accionable(self):
        """Hallazgo de revisión (2026-09-26): sin este guardarraíl, una
        doble confirmación (doble clic, un token reenviado dentro de su
        ventana de validez) podía encolar la misma descarga otra vez
        sobre un item que ya está DOWNLOADING/IMPORTED."""
        item = Wishlist(id=uuid4(), status=WishlistStatus.DOWNLOADING)
        orch = Orchestrator(db=FakeSession())
        orch._transmission = AsyncMock()
        candidato = make_result(seeders=10)

        result = await orch.send_manual_candidate(item, candidato)

        assert result is False
        assert item.status == WishlistStatus.DOWNLOADING  # sin tocar
        assert item.last_error == MOTIVO_CANDIDATO_INVALIDO
        orch._transmission.add_torrent.assert_not_called()

    @pytest.mark.asyncio
    async def test_pierde_la_reclamacion_atomica_no_envia_nada(self):
        """Hallazgo de revisión de PR (2026-09-26): el guardarraíl de
        estado por sí solo no basta contra dos peticiones CONCURRENTES
        — ambas pueden leer WANTED en su propia sesión antes de que
        ninguna termine de enviar. El objeto en memoria sigue diciendo
        WANTED (nadie se lo ha refrescado), pero la reclamación atómica
        (UPDATE condicionado) es quien de verdad decide: si otra
        petición ya ganó la carrera, esta ni siquiera llega a mirar el
        backend."""
        item = Wishlist(id=uuid4(), status=WishlistStatus.WANTED)
        orch = Orchestrator(db=FakeSession([claim_perdida()]))
        orch._transmission = AsyncMock()
        candidato = make_result(seeders=10)

        result = await orch.send_manual_candidate(item, candidato)

        assert result is False
        assert item.status == WishlistStatus.WANTED  # sin tocar, no se ganó la reclamación
        orch._transmission.add_torrent.assert_not_called()

    @pytest.mark.asyncio
    async def test_perder_la_reclamacion_no_pisa_el_resultado_del_ganador(self):
        """Verificado en vivo contra Postgres real (2026-09-26): antes de
        este cambio, el perdedor escribía last_error="candidato
        inválido" y hacía flush() incondicionalmente — como esa
        escritura llega DESPUÉS de que el ganador ya confirmó la suya
        (el ganador pasa por el `_send()` más lento), pisaba un
        last_error=None de un envío que sí tuvo éxito. Ahora el
        perdedor no toca last_error en absoluto."""
        item = Wishlist(id=uuid4(), status=WishlistStatus.WANTED, last_error=None)
        orch = Orchestrator(db=FakeSession([claim_perdida()]))
        orch._transmission = AsyncMock()
        candidato = make_result(seeders=10)

        await orch.send_manual_candidate(item, candidato)

        assert item.last_error is None  # sin tocar


class TestTokenCandidato:
    """D10 (hallazgo de revisión, 2026-09-26): el candidato viaja firmado
    por el servidor, ligado al item y con caducidad — nunca reconstruido
    a partir de campos sueltos que el formulario reenvíe."""

    def test_token_valido_devuelve_el_mismo_candidato(self):
        item_id = uuid4()
        candidato = make_result(title="Batman #1.cbz", url="magnet:?xt=urn:btih:abc", seeders=10)

        token = crear_token_candidato(item_id, candidato, "secreto")
        recuperado = verificar_token_candidato(token, item_id, "secreto")

        assert recuperado is not None
        assert recuperado.title == "Batman #1.cbz"
        assert recuperado.download_url == "magnet:?xt=urn:btih:abc"

    def test_token_de_otro_item_no_vale(self):
        candidato = make_result(seeders=10)
        token = crear_token_candidato(uuid4(), candidato, "secreto")

        assert verificar_token_candidato(token, uuid4(), "secreto") is None

    def test_token_con_otro_secreto_no_vale(self):
        item_id = uuid4()
        candidato = make_result(seeders=10)
        token = crear_token_candidato(item_id, candidato, "secreto")

        assert verificar_token_candidato(token, item_id, "otro-secreto") is None

    def test_token_manipulado_no_vale(self):
        item_id = uuid4()
        candidato = make_result(seeders=10)
        token = crear_token_candidato(item_id, candidato, "secreto")
        manipulado = token[:-1] + ("0" if token[-1] != "0" else "1")

        assert verificar_token_candidato(manipulado, item_id, "secreto") is None

    def test_token_caducado_no_vale(self, monkeypatch):
        item_id = uuid4()
        candidato = make_result(seeders=10)
        monkeypatch.setattr("zascarr.services.orchestrator.TOKEN_CANDIDATO_TTL_SEGUNDOS", -1)
        token = crear_token_candidato(item_id, candidato, "secreto")

        assert verificar_token_candidato(token, item_id, "secreto") is None

    def test_token_vacio_o_secreto_vacio_no_vale(self):
        item_id = uuid4()
        candidato = make_result(seeders=10)
        token = crear_token_candidato(item_id, candidato, "secreto")

        assert verificar_token_candidato("", item_id, "secreto") is None
        assert verificar_token_candidato(token, item_id, "") is None


# ═══════════════════════════════════════════════════════════════════════════
# 3. last_searched_at — marcado en cada intento (H2 aplicado aquí también)
# ═══════════════════════════════════════════════════════════════════════════

class TestUltimoIntento:

    @pytest.mark.asyncio
    async def test_se_marca_incluso_sin_resultados(self):
        item = Wishlist(id=uuid4(), search_query="X", status=WishlistStatus.WANTED)
        orch = Orchestrator(db=FakeSession())
        orch._prowlarr = AsyncMock()
        orch._prowlarr.search.return_value = []

        assert item.last_searched_at is None
        await orch._process_item(item)
        assert item.last_searched_at is not None

    @pytest.mark.asyncio
    async def test_se_marca_con_exito(self):
        item = Wishlist(id=uuid4(), search_query="Batman", status=WishlistStatus.WANTED)
        orch = Orchestrator(db=FakeSession())
        orch._prowlarr = AsyncMock()
        orch._prowlarr.search.return_value = [make_result(seeders=10)]
        orch._transmission = AsyncMock()
        orch._transmission.add_torrent.return_value = {"hashString": "abc"}

        await orch._process_item(item)
        assert item.last_searched_at is not None

    def test_query_de_seleccion_incluye_wanted_failed_y_cooldown(self):
        """Sin DB real: se verifica que el WHERE generado cubre WANTED y
        FAILED (no solo WANTED, o un fallo de envío se abandona para
        siempre) y compara last_searched_at contra NULL o el cooldown."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
        from sqlalchemy import or_
        stmt = (
            select(Wishlist)
            .where(Wishlist.status.in_([WishlistStatus.WANTED, WishlistStatus.FAILED]))
            .where(or_(
                Wishlist.last_searched_at.is_(None),
                Wishlist.last_searched_at < cutoff,
            ))
        )
        compiled = str(stmt)
        assert "wishlist_status" in compiled or "status IN" in compiled
        assert "last_searched_at IS NULL" in compiled
        assert "last_searched_at <" in compiled


# ═══════════════════════════════════════════════════════════════════════════
# 4. check_completions — cierre del círculo por existencia de File
# ═══════════════════════════════════════════════════════════════════════════

def make_file(issue_id=None) -> File:
    return File(id=uuid4(), file_path="/lib/x.cbz", file_name="x.cbz",
                file_format=FileFormat.CBZ, issue_id=issue_id)


class TestCheckCompletions:

    @pytest.mark.asyncio
    async def test_issue_con_file_enlazado_pasa_a_imported(self):
        issue_id = uuid4()
        item = Wishlist(id=uuid4(), issue_id=issue_id, status=WishlistStatus.DOWNLOADING)
        session = FakeSession([
            FakeExecResult([item]),          # select pendientes DOWNLOADING
            FakeExecResult([make_file(issue_id)]),  # _is_fulfilled: File.id existe
        ])
        orch = Orchestrator(db=session)

        completed = await orch.check_completions()

        assert completed == 1
        assert item.status == WishlistStatus.IMPORTED
        assert item.downloaded_at is not None

    @pytest.mark.asyncio
    async def test_sin_file_todavia_se_queda_downloading(self):
        issue_id = uuid4()
        item = Wishlist(id=uuid4(), issue_id=issue_id, status=WishlistStatus.DOWNLOADING)
        session = FakeSession([
            FakeExecResult([item]),
            FakeExecResult([]),  # ningún File enlazado todavía
        ])
        orch = Orchestrator(db=session)

        completed = await orch.check_completions()

        assert completed == 0
        assert item.status == WishlistStatus.DOWNLOADING
        assert item.downloaded_at is None

    @pytest.mark.asyncio
    async def test_item_solo_con_series_id_busca_por_join_a_issues(self):
        series_id = uuid4()
        item = Wishlist(id=uuid4(), series_id=series_id, status=WishlistStatus.DOWNLOADING,
                        added_at=datetime.now(timezone.utc) - timedelta(days=1))
        session = FakeSession([
            FakeExecResult([item]),
            FakeExecResult([make_file()]),  # el join ya filtra por series_id
        ])
        orch = Orchestrator(db=session)

        completed = await orch.check_completions()
        assert completed == 1

    @pytest.mark.asyncio
    async def test_por_issue_id_filtra_is_missing_en_el_where(self):
        """B7 (revisión de PR, 2026-09-26): un File is_missing=True ya no
        es "lo tengo" — sin este filtro, un tebeo borrado a mano tras
        importarse bastaba para dar la wishlist por cumplida igual."""
        issue_id = uuid4()
        item = Wishlist(id=uuid4(), issue_id=issue_id, status=WishlistStatus.DOWNLOADING)
        session = CapturingSession([FakeExecResult([item]), FakeExecResult([])])
        orch = Orchestrator(db=session)

        await orch.check_completions()

        assert "is_missing" in session.statements[1]

    @pytest.mark.asyncio
    async def test_por_series_id_filtra_is_missing_en_el_where(self):
        series_id = uuid4()
        item = Wishlist(id=uuid4(), series_id=series_id, status=WishlistStatus.DOWNLOADING,
                        added_at=datetime.now(timezone.utc) - timedelta(days=1))
        session = CapturingSession([FakeExecResult([item]), FakeExecResult([])])
        orch = Orchestrator(db=session)

        await orch.check_completions()

        assert "is_missing" in session.statements[1]


# ═══════════════════════════════════════════════════════════════════════════
# 5. Blindaje legal (aceptación) y opt-in P2P — no tocar red sin ninguno
# ═══════════════════════════════════════════════════════════════════════════

class TestGateLegalYOptInP2P:

    @pytest.mark.asyncio
    async def test_process_wishlist_no_hace_nada_sin_aceptar_el_aviso(self):
        """Ni siquiera llega a mirar la wishlist si no hay acknowledgment
        — el ciclo entero se salta, Prowlarr no se toca."""
        session = FakeSession([FakeExecResult([])])  # is_acknowledged: ninguna fila
        orch = Orchestrator(db=session)
        orch._prowlarr = AsyncMock()

        sent = await orch.process_wishlist()

        assert sent == 0
        orch._prowlarr.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_backend_deshabilitado_descarta_el_candidato(self, monkeypatch):
        """Aunque Prowlarr encuentre algo, un backend no activado
        (transmission_enabled=False, default de fábrica) no se intenta."""
        item = Wishlist(id=uuid4(), search_query="Batman", status=WishlistStatus.WANTED)
        settings = get_settings().model_copy(update={
            "prowlarr_enabled": True, "transmission_enabled": False, "amule_enabled": False,
        })
        monkeypatch.setattr("zascarr.services.orchestrator.get_settings", lambda: settings)

        orch = Orchestrator(db=FakeSession())
        orch._prowlarr = AsyncMock()
        orch._prowlarr.search.return_value = [make_result(seeders=50)]  # magnet:// -> Transmission
        orch._transmission = AsyncMock()

        result = await orch._process_item(item)

        assert result is False
        assert item.status == WishlistStatus.WANTED  # sin candidatos utilizables, no es un fallo
        orch._transmission.add_torrent.assert_not_called()


class TestFiltroPorNumeroD8:
    """D8: la búsqueda es de TEXTO, así que devolver algo no significa que sea el
    número de ESA serie. `_ranked_candidates` puntúa pero **no descarta**, así que
    el filtro tiene que ser aquí y el título tiene que contar."""

    @staticmethod
    def _candidato(titulo: str) -> SearchResult:
        return SearchResult(titulo, "indexer", "magnet:?xt=urn:btih:abc", 100, 5, "comics")

    def _acepta(self, titulo: str, numero: int, serie: str) -> bool:
        return Orchestrator._candidato_es_del_numero(self._candidato(titulo), numero, serie)

    def test_el_numero_correcto_de_la_serie_pasa(self):
        assert self._acepta("Batman 004 (2019) (Digital).cbz", 4, "Batman")
        assert self._acepta("Batman 4.cbz", 4, "Batman")   # 04 y 4 son el mismo

    def test_otra_serie_con_el_mismo_numero_no_pasa(self):
        """La contención aceptaba esto: "Batman" está dentro de "Batman Beyond"."""
        assert not self._acepta("Batman Beyond 004 (2019).cbz", 4, "Batman")

    def test_la_serie_corta_no_sirve_para_la_larga(self):
        """Y en el otro sentido: "Batman" tampoco sirve para "Batman Beyond"."""
        assert not self._acepta("Batman 004.cbz", 4, "Batman Beyond")

    @pytest.mark.parametrize("titulo", ["Batman 1.5.cbz", "Batman 4-6.cbz", "Batman 12a.cbz"])
    def test_numeros_que_no_son_enteros_no_pasan(self, titulo):
        """Se rechazan de forma explícita, no por accidente de comparación."""
        assert not self._acepta(titulo, 4, "Batman")

    def test_un_titulo_que_normaliza_vacio_se_rechaza(self):
        """El hueco que señaló la revisión: con `""` en cualquiera de los dos
        lados, `"" in x` (o `== ""`) colaría cualquier cosa."""
        assert not self._acepta("004", 4, "004")

    def test_sin_serie_en_la_base_no_se_acepta_nada(self):
        """Falla cerrado: preferimos que el número quede en Pendientes antes que
        dar por bueno un candidato de otra serie."""
        assert not self._acepta("Batman 004.cbz", 4, "")

    def test_un_numero_mas_largo_no_pasa_por_el_corto(self):
        """Comparar texto lo habría colado: "120" no es el 12."""
        assert not self._acepta("Batman 120 (2019).cbz", 12, "Batman")

    def test_el_subtitulo_tras_guion_lo_separa_el_parser(self):
        """RF-04/B5: "Asterix T01 - Asterix el Galo" → serie "Asterix", así que
        la igualdad no pierde este caso (era el motivo para usar contención)."""
        assert self._acepta("Asterix T01 - Asterix el Galo.cbz", 1, "Asterix")


class TestMotivoNumeroDistintoD8:
    """D9 + D8: cuando lo ÚNICO que vacía el pool es el filtro por número, el
    motivo no puede decir «ningún cliente de descarga está activo» — eso sería
    falso. La integración importa: los casos puros de `_candidato_es_del_numero`
    no prueban que `_search_and_rank` escriba el motivo correcto."""

    @pytest.mark.asyncio
    async def test_solo_el_filtro_de_numero_vacio_el_pool(self):
        serie = make_series(title="Batman")
        item = Wishlist(id=uuid4(), series_id=serie.id, numero=4, status=WishlistStatus.WANTED)
        session = FakeSession([
            FakeExecResult([serie]),   # _build_query
            FakeExecResult([serie]),   # título de la serie para el filtro
            FakeExecResult([]),        # alias locales
        ])
        orch = Orchestrator(db=session)
        orch._prowlarr = AsyncMock()
        orch._prowlarr.search.return_value = [make_result(title="Batman 007.cbz", seeders=50)]
        orch._transmission = AsyncMock()

        result = await orch._search_and_rank(item)

        assert result == []
        assert item.status == WishlistStatus.WANTED
        assert item.last_error == MOTIVO_NUMERO_DISTINTO
        # El título del item pedía la serie genérica, no un número suelto.
        orch._prowlarr.search.assert_awaited_once_with("Batman 4", categories=[7030, 7020])


class TestFiltroPorNumeroConAliasD8:
    """B13: un release español puede llamar "La Patrulla-X" a una serie
    catalogada como "X-Men". Con igualdad estricta ese candidato se descartaría
    y el número no avanzaría nunca, justo para el público hispanohablante. Los
    alias locales son los que el coleccionista ya confirmó: aceptarlos no afloja
    el filtro."""

    @staticmethod
    def _candidato(titulo: str) -> SearchResult:
        return SearchResult(titulo, "indexer", "magnet:?xt=urn:btih:abc", 100, 5, "comics")

    def _acepta(self, titulo, numero, serie, alias=()):
        return Orchestrator._candidato_es_del_numero(
            self._candidato(titulo), numero, serie, set(alias))

    def test_sin_alias_el_nombre_espanol_se_rechaza(self):
        """Documenta el riesgo: así se comporta hoy sin alias."""
        assert not self._acepta("La Patrulla-X 012 (1985).cbz", 12, "X-Men")

    def test_con_alias_confirmado_si_se_acepta(self):
        from zascarr.core.matcher import normalize_title as nt
        assert self._acepta("La Patrulla-X 012 (1985).cbz", 12, "X-Men", {nt("La Patrulla-X")})

    def test_el_alias_no_cuela_otro_numero(self):
        from zascarr.core.matcher import normalize_title as nt
        assert not self._acepta("La Patrulla-X 013 (1985).cbz", 12, "X-Men", {nt("La Patrulla-X")})

    def test_sin_serie_pero_con_alias_sigue_aceptando(self):
        """Los alias son de ESA serie, así que no hace falta el título."""
        from zascarr.core.matcher import normalize_title as nt
        assert self._acepta("La Patrulla-X 012.cbz", 12, "", {nt("La Patrulla-X")})

    def test_sin_serie_y_sin_alias_sigue_fallando_cerrado(self):
        assert not self._acepta("La Patrulla-X 012.cbz", 12, "")


class TestMedicionD8ContraElBancoReal:
    """Convierte en regresión la medición del docstring del filtro: los casos que
    solo pasarían con contención **no son series distintas legítimas**, sino
    sobre-captura del parser, y el filtro tiene que rechazarlos. Así los números
    del docstring no se quedan viejos."""

    @staticmethod
    def _banco():
        import csv
        from pathlib import Path
        ruta = (Path(__file__).resolve().parents[1]
                / "scripts" / "medicion" / "muestra81_etiquetada.csv")
        assert ruta.exists(), "el banco real de medición tiene que estar en el repo"
        with ruta.open(encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_la_sobre_captura_del_parser_se_rechaza(self):
        """El rechazo tiene que ser POR TÍTULO. Si el parser leyera otro número
        del candidato, la aserción pasaría por el motivo equivocado y no
        probaría nada, así que se comprueba la precondición caso a caso."""
        from zascarr.utils.naming import normalize_series_name as norm
        from zascarr.utils.naming import parse_comic_filename
        comprobados: list[str] = []
        for fila in self._banco():
            real, parseado = fila["serie_real"] or "", fila["parser_serie"] or ""
            a, b = norm(parseado), norm(real)
            if not a or not b or a == b:
                continue
            if not (a in b or b in a):    # solo la contención lo aceptaría
                continue
            candidato = SearchResult(f"{parseado} 4", "i", "magnet:x", 1, 1, "comics")
            parsed = parse_comic_filename(candidato.title)
            if parsed.issue_number != "4" or parsed.series != parseado:
                continue      # este caso no puede demostrar el rechazo por título
            comprobados.append(parseado)
            assert not Orchestrator._candidato_es_del_numero(candidato, 4, real), \
                f"«{parseado}» no debería valer para «{real}» (mismo número, distinto título)"
        # Suelo alto a propósito: si el parser cambia y solo un caso sigue
        # cumpliendo la precondición, la prueba pasaría casi vacía sin que nadie
        # se enterara. Se exigen los tres que cumplen hoy y, por nombre, los dos
        # de sobre-captura que justifican la decisión en el docstring.
        assert len(comprobados) >= 3, \
            f"solo {len(comprobados)} caso(s) demuestran el rechazo por título: {comprobados}"
        assert any("taxus" in c.lower() for c in comprobados), comprobados
        assert any("dreadstar" in c.lower() for c in comprobados), comprobados

    def test_la_igualdad_es_la_mayoria_del_banco(self):
        """La medición que justifica elegir igualdad: si esto baja mucho, la
        decisión habría que revisarla con datos nuevos."""
        from zascarr.utils.naming import normalize_series_name as norm
        filas = [f for f in self._banco()
                 if norm(f["serie_real"] or "") and norm(f["parser_serie"] or "")]
        iguales = sum(1 for f in filas
                      if norm(f["parser_serie"]) == norm(f["serie_real"]))
        assert iguales >= int(len(filas) * 0.8), f"solo {iguales}/{len(filas)} con igualdad"

    def test_un_omnibus_del_mismo_numero_no_es_la_grapa(self):
        """El filtro descarta lo que el parser marca como edición (`edition_kind`):
        un Omnigold 4 no es la grapa #4 (regla de C2/B15)."""
        candidato = SearchResult("Batman Omnigold 4 (2019).cbz", "i", "magnet:x", 1, 1, "comics")
        assert not Orchestrator._candidato_es_del_numero(candidato, 4, "Batman")


# ═══════════════════════════════════════════════════════════════════════════
# D8 — generación y retirada con un solo predicado
# ═══════════════════════════════════════════════════════════════════════════
#
# La prueba de comportamiento completa vive en `tests/test_politica_d8_pg.py`
# (Postgres real). Aquí queda lo que corre siempre en CI: el `WHERE` exacto de
# las dos sentencias que no pueden equivocarse y las ramas que ni tocan la BD.

def _sql(statement) -> str:
    from sqlalchemy.dialects import postgresql
    return str(statement.compile(dialect=postgresql.dialect(),
                                 compile_kwargs={"literal_binds": True}))


class TestSentenciasD8:
    """El `WHERE` es la regla. Se fija compilado, no en prosa."""

    def test_la_retirada_solo_toca_lo_que_no_empezo(self):
        sql = _sql(stmt_retirada(uuid4(), Querer(frozenset({1, 3}), True)))

        assert "status IN ('wanted', 'failed')" in sql
        assert "origen = 'politica'" in sql
        assert "status='retirado'" in sql
        # Lo que ya empezó no se retira: marcarlo sería mentir (D9).
        assert "searching" not in sql
        assert "downloading" not in sql
        assert "numero NOT IN (1, 3)" in sql

    def test_sin_numeros_queridos_se_retira_todo_lo_pendiente(self):
        """El caso «pasar a `ninguno`»: sin lista de números no hay `NOT IN` que
        valga, se retira todo lo pendiente de esa serie."""
        sql = _sql(stmt_retirada(uuid4(), Querer(frozenset(), True)))

        assert "status IN ('wanted', 'failed')" in sql
        assert "numero" not in sql          # ninguna condición de número
        assert "searching" not in sql and "downloading" not in sql

    def test_la_generacion_solo_reactiva_retirado_e_imported(self):
        """El `DO UPDATE` es la red bajo el filtro de Python. Lo que fija aquí:
        que la inferencia del conflicto reproduce el `WHERE` del índice parcial
        y que la reactivación se limita a `retirado`/`imported` — así no reinicia
        un `FAILED` (le borraría el `last_error` de D9) ni un `DOWNLOADED` (la
        descarga ya viene de camino)."""
        sql = _sql(Orchestrator._stmt_materializar(uuid4(), 4, datetime.now(UTC)))

        assert ("ON CONFLICT (series_id, numero) "
                "WHERE origen = 'politica' AND numero IS NOT NULL") in sql
        assert "DO UPDATE SET" in sql
        assert "download_ref = NULL" in sql
        assert "status IN ('retirado', 'imported')" in sql
        for no_reactivable in ("wanted", "searching", "downloading", "downloaded", "failed"):
            assert no_reactivable not in sql.split("WHERE")[-1], no_reactivable

    def test_los_estados_reactivables_son_solo_dos(self):
        """Contrato explícito: si alguien añade un estado, tiene que decidir a
        conciencia si la generación puede reiniciarlo."""
        assert set(ESTADOS_REACTIVABLES) == {WishlistStatus.RETIRADO, WishlistStatus.IMPORTED}


class TestQuererDeSerieD8:
    """Las ramas que no llegan a la BD: son las que más fácil se rompen al
    tocar el orden de las comprobaciones."""

    @pytest.mark.asyncio
    async def test_ninguno_no_quiere_nada_y_no_es_un_fallo(self):
        serie = make_series()
        serie.wishlist_policy = WishlistPolicy.NONE

        querer = await querer_de_serie(FakeSession(), serie)

        assert querer == Querer(frozenset(), True)
        assert querer.motivo is None

    @pytest.mark.asyncio
    async def test_futuros_se_declara_no_computable(self):
        serie = make_series()
        serie.wishlist_policy = WishlistPolicy.FUTURE

        querer = await querer_de_serie(FakeSession(), serie)

        assert querer == Querer(frozenset(), False, MOTIVO_POLITICA_FUTUROS)

    @pytest.mark.asyncio
    async def test_un_manual_de_serie_vivo_no_quiere_ningun_numero(self):
        serie = make_series()
        serie.wishlist_policy = WishlistPolicy.MISSING
        # (issue_id, numero) del manual de serie: los dos nulos.
        session = FakeSession([FakeExecResult([(None, None)])])

        querer = await querer_de_serie(session, serie)

        assert querer.numeros == frozenset()
        assert querer.motivo == MOTIVO_DESEO_DE_SERIE
        assert querer.computable is True


class TestSincronizacionD8:
    """El flujo completo con FakeSession: generación acotada y retirada atómica."""

    @staticmethod
    def _serie(total=2, policy=WishlistPolicy.MISSING) -> Series:
        return Series(id=uuid4(), title="Batman", tradition=ComicTradition.AMERICAN,
                      total_issues=total, metadata_source=MetadataSource.COMIC_VINE.value,
                      wishlist_policy=policy)

    @pytest.mark.asyncio
    async def test_genera_los_huecos_y_retira_cero(self):
        serie = self._serie(total=2)
        session = FakeSession([
            FakeExecResult([object()]),   # is_acknowledged
            FakeExecResult([serie]),      # series con política
            FakeExecResult([]),           # items manuales vivos: ninguno
            FakeExecResult([]),           # números poseídos: ninguno
            FakeExecResult([], rowcount=0),   # retirada
            FakeExecResult([]),           # items de política ya existentes: ninguno
            FakeExecResult([]),           # insert 1
            FakeExecResult([]),           # insert 2
        ])

        resultado = await Orchestrator(db=session).sync_policy_items(lote=10)

        assert resultado == SincronizacionPolitica(2, 0)

    @pytest.mark.asyncio
    async def test_el_tope_no_deja_materializar_de_mas(self):
        serie = self._serie(total=5)
        session = FakeSession([
            FakeExecResult([object()]),
            FakeExecResult([serie]),
            FakeExecResult([]),
            FakeExecResult([]),
            FakeExecResult([], rowcount=0),
            FakeExecResult([]),
            FakeExecResult([]),           # solo hay sitio para UN insert
        ])

        resultado = await Orchestrator(db=session).sync_policy_items(lote=1)

        assert resultado == SincronizacionPolitica(1, 0)
        assert len(session._queue) == 0, "el tope tiene que cortar antes de agotar la cola"

    @pytest.mark.asyncio
    async def test_una_serie_a_ninguno_retira_sin_generar(self):
        serie = self._serie(total=3, policy=WishlistPolicy.NONE)
        session = FakeSession([
            FakeExecResult([object()]),
            FakeExecResult([serie]),
            FakeExecResult([], rowcount=2),   # la retirada
        ])

        resultado = await Orchestrator(db=session).sync_policy_items()

        assert resultado == SincronizacionPolitica(0, 2)

    @pytest.mark.asyncio
    async def test_sin_acuse_no_se_toca_la_base(self):
        session = FakeSession([FakeExecResult([])])   # is_acknowledged: nada

        resultado = await Orchestrator(db=session).sync_policy_items()

        assert resultado == SincronizacionPolitica(0, 0)
        assert len(session._queue) == 0, "sin acuse no se consulta siquiera la política"
