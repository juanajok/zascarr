# ruff: noqa: E501, F401, F811
"""#117 — recuperación y fronteras de la confirmación de un lote de vinculación, de extremo a extremo (Postgres real
y PROCESOS reales).

#116 fija lo que ve la persona en cada estado (`test_vinculacion_resultado_pg.py`); esta suite aporta la evidencia de
que se cumple **en la base de datos, tras la muerte del proceso y ante la concurrencia**, y no duplica ese contrato.

«Reiniciar el proceso» es aquí literal (`tests/_proceso_vinculacion.py`): un proceso hijo recibe `SIGKILL` en un punto
exacto de la confirmación —con las escrituras ya dentro de la transacción abierta, o justo después del `COMMIT`— y
otro proceso, con otra conexión y sin memoria del anterior, repite el mismo token. Lo que sobrevive es lo que Postgres
tiene. Los vínculos, los números y el informe los inspecciona el proceso de la prueba, que no participó.

| Criterio de #117 | Enlaza con #116 | Dónde se prueba |
|---|---|---|
| 1. Fallo antes del commit | criterio 1 | `TestCriterio1MuerteAntesDelCommit` |
| 2. Commit hecho y respuesta perdida | criterio 2 | `TestCriterio2CommitHechoYRespuestaPerdida` |
| 3. Fallo tras el commit | criterio 3 | `TestCriterio3FalloTrasElCommit` |
| 4. Caducidad del token | criterio 5 | `TestCriterio4CaducidadDelToken` |
| 5. Retención y purga | criterio 5 | `TestCriterio5RetencionYPurga` |
| 6. Confirmaciones concurrentes | criterio 2 | `TestCriterio6Concurrencia` |

Lecturas de los criterios que esta suite fija y que necesitan al responsable del producto (ver la PR): la 1 (qué
devuelve reenviar el token tras un fallo que no dejó nada), la 4 (qué devuelve un token caducado cuyo informe sí
está) y la 5 (las condiciones de retención se toman del contrato implementado, no están «acordadas» en la tarjeta).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

import zascarr
from tests._pg import RAIZ
from tests.test_vinculacion_pg import (  # noqa: F401  (fixtures y ayudas compartidas)
    CLAVE,
    SECRETO,
    archivos,
    confirmar,
    documento_canonico,
    ent,
    entorno,
    estado_de_archivos,
    firmar,
    informes,
    instantanea,
    numero_de,
    serie_de_prueba,
    token_de,
    url_bd,
)
from zascarr.services.tokens_revision import TTL_SEGUNDOS, verificar_token_vinculacion
from zascarr.services.vinculacion import (
    MENSAJE_CADUCADO_SIN_APLICAR,
    MENSAJE_CADUCADO_SIN_INFORME,
    RETENCION_HORAS,
)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)"),
]

UNO, DOS, TRES = "Flash 01 (1987).cbz", "Flash 02 (1987).cbz", "Flash 03 (1987).cbz"
ESPERA_S = 90.0


# ── Procesos reales ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Hijo:
    """Un proceso de ZascArr (`tests/_proceso_vinculacion.py`) y lo que ha impreso."""
    proc: asyncio.subprocess.Process
    lineas: list[str] = field(default_factory=list)

    async def esperar(self, prefijo: str) -> str:
        while True:
            crudo = await asyncio.wait_for(self.proc.stdout.readline(), ESPERA_S)
            if not crudo:
                raise AssertionError(f"el proceso terminó sin imprimir {prefijo!r}:\n" + "\n".join(self.lineas))
            linea = crudo.decode().rstrip()
            self.lineas.append(linea)
            if linea.startswith(prefijo):
                return linea

    async def soltar(self) -> None:
        """Le dice al proceso retenido que siga (escribe una línea en su entrada estándar)."""
        self.proc.stdin.write(b"\n")
        await self.proc.stdin.drain()

    async def terminar(self) -> int:
        resto = await asyncio.wait_for(self.proc.stdout.read(), ESPERA_S)
        self.lineas.extend(resto.decode().splitlines())
        return await asyncio.wait_for(self.proc.wait(), ESPERA_S)

    def marca(self, prefijo: str) -> str | None:
        return next((x for x in self.lineas if x.startswith(prefijo)), None)

    def t(self, prefijo: str) -> float:
        return float(self.marca(prefijo).split("t=")[1])

    @property
    def resultado(self) -> dict | None:
        m = self.marca("RESULTADO ")
        return json.loads(m[len("RESULTADO "):]) if m else None


_VIVOS: list[asyncio.subprocess.Process] = []


@pytest.fixture(autouse=True)
async def _sin_hijos_huerfanos():
    """Si una prueba falla a medias, no deja procesos con la transacción abierta sobre la base que se va a borrar."""
    yield
    for p in _VIVOS:
        if p.returncode is None:
            p.kill()
            await p.wait()
    _VIVOS.clear()


async def lanzar(ent, url_bd: str, token: str, modo: str = "confirmar", *, retener: float = 0.0, barrera: bool = False) -> Hijo:
    src = str(Path(zascarr.__file__).resolve().parents[1])
    entorno = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(RAIZ), src, os.environ.get("PYTHONPATH", "")]),
        "ZASCARR_PRUEBA_BD": url_bd, "ZASCARR_PRUEBA_BIBLIOTECA": str(ent.lib), "ZASCARR_PRUEBA_SECRETO": SECRETO,
        "ZASCARR_PRUEBA_TOKEN": token, "ZASCARR_PRUEBA_MODO": modo, "ZASCARR_PRUEBA_RETENER_S": str(retener),
        "ZASCARR_PRUEBA_BARRERA": "1" if barrera else "0",
    }
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "tests._proceso_vinculacion", cwd=str(RAIZ), env=entorno,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    _VIVOS.append(proc)
    return Hijo(proc)


async def ejecutar(ent, url_bd: str, token: str, modo: str = "confirmar", **kw) -> tuple[Hijo, int]:
    h = await lanzar(ent, url_bd, token, modo, **kw)
    return h, await h.terminar()


def operacion_de(token: str) -> str:
    return verificar_token_vinculacion(token, SECRETO, ignorar_caducidad=True).operacion


# ── Lo que Postgres tiene ───────────────────────────────────────────────────────────────────────

async def sin_efectos(ent) -> None:
    assert await numero_de("issues", ent.banco) == 0, "hay Issues de una operación que no se confirmó"
    assert await informes(ent.banco) == [], "hay un informe persistido de una operación que no se confirmó"
    assert all(v[0] is None for v in (await estado_de_archivos(ent.banco)).values()), "hay archivos vinculados"


async def sin_transacciones_abiertas(ent, espera: float = 10.0) -> None:
    """Postgres aborta la transacción de un cliente que murió: no queda ninguna sesión «idle in transaction»."""
    consulta = text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                    "AND pid <> pg_backend_pid() AND state LIKE 'idle in transaction%'")
    hasta = time.monotonic() + espera
    while True:
        async with ent.banco.fabrica() as s:
            n = (await s.execute(consulta)).scalar_one()
        if n == 0 or time.monotonic() > hasta:
            assert n == 0, f"{n} sesión(es) con la transacción abierta tras la muerte del proceso"
            return
        await asyncio.sleep(0.1)


async def concuerda_con_el_informe(ent, informe: dict) -> None:
    """El estado de la base coincide, archivo a archivo, con lo que dice el informe persistido."""
    op = informe["operacion_id"]
    async with ent.banco.fabrica() as s:
        filas = {str(i): (str(iss) if iss else None, vinculo) for i, iss, vinculo in (await s.execute(text(
            "SELECT id, issue_id, metadata->'vinculo'->>'operacion_id' FROM files"))).all()}
        n_issues = (await s.execute(text("SELECT count(*) FROM issues"))).scalar_one()
    vinculados = [a for a in informe["archivos"] if a["estado"] == "vinculado"]
    for a in informe["archivos"]:
        issue, vinculo_op = filas[a["id"]]
        if a["estado"] == "vinculado":
            assert issue is not None and vinculo_op == op, f"{a['id']}: el informe dice vinculado y la base no"
        elif a["estado"] == "omitido":
            assert issue is None and vinculo_op is None, f"{a['id']}: el informe dice omitido y la base lo tiene vinculado"
    assert sum(1 for _, v in filas.values() if v == op) == len(vinculados) == informe["totales"]["vinculados"]
    assert n_issues == informe["totales"]["issues_creados"]


async def informe_persistido(ent, operacion: str) -> dict:
    filas = [r for r in await informes(ent.banco) if r[0] == operacion]
    assert len(filas) == 1, f"debía haber un informe para {operacion} y hay {len(filas)}"
    return filas[0][2]


# ── Criterio 1 ──────────────────────────────────────────────────────────────────────────────────

class TestCriterio1MuerteAntesDelCommit:
    """El proceso muere con las escrituras ya dentro de la transacción y sin confirmar."""

    async def test_no_queda_nada_y_reenviar_el_token_aplica_una_sola_vez_con_el_mismo_operacion_id(self, ent, url_bd):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO, DOS)
        token = await token_de(serie, ids.values())
        antes = await instantanea(ent.banco)

        h, codigo = await ejecutar(ent, url_bd, token, "morir_antes_del_commit")
        assert codigo == -9, f"el proceso debía morir por SIGKILL y salió con {codigo}:\n" + "\n".join(h.lineas)
        assert h.marca("EN_TRANSACCION vinculados=2 informes=1"), h.lineas     # la transacción SÍ tenía escrituras
        assert h.resultado is None                                              # y no hubo respuesta
        await sin_transacciones_abiertas(ent)
        await sin_efectos(ent)
        assert await instantanea(ent.banco) == antes                            # ni una fila distinta, en ninguna tabla

        # Reenviar el mismo token (otro proceso, otra conexión): una sola operación, la del token.
        h2, codigo2 = await ejecutar(ent, url_bd, token)
        r = h2.resultado
        assert codigo2 == 0 and r["status"] == 200, h2.lineas
        assert r["body"]["operacion_id"] == operacion_de(token) and r["body"]["repetida"] is False
        assert {i[0] for i in await informes(ent.banco)} == {operacion_de(token)}
        assert await numero_de("issues", ent.banco) == 2
        await concuerda_con_el_informe(ent, await informe_persistido(ent, operacion_de(token)))

    async def test_el_candado_de_la_operacion_no_queda_retenido_tras_la_muerte(self, ent, url_bd):
        """El proceso muerto sostenía el candado de la operación y el de la serie: Postgres los suelta con la conexión.
        Se comprueba pidiéndolos otra vez, con un plazo, en lugar de suponer que se liberaron."""
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO)
        token = await token_de(serie, ids.values())
        h, codigo = await ejecutar(ent, url_bd, token, "morir_antes_del_commit")
        assert codigo == -9
        h2 = await lanzar(ent, url_bd, token)
        codigo2 = await h2.terminar()               # si el candado siguiera retenido, esto agotaría el plazo
        assert codigo2 == 0 and h2.resultado["status"] == 200, h2.lineas


# ── Criterio 2 ──────────────────────────────────────────────────────────────────────────────────

class TestCriterio2CommitHechoYRespuestaPerdida:
    """El COMMIT llegó a Postgres y el proceso murió antes de contestar."""

    async def test_el_reenvio_devuelve_el_informe_persistido_sin_duplicar_efectos(self, ent, url_bd):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO, DOS, TRES)
        token = await token_de(serie, ids.values())

        h, codigo = await ejecutar(ent, url_bd, token, "morir_despues_del_commit")
        assert codigo == -9, h.lineas
        assert h.marca("COMMIT_HECHO") and h.resultado is None                  # confirmado, sin respuesta
        op = operacion_de(token)
        informe = await informe_persistido(ent, op)
        assert informe["global"] == "vinculados_todos"
        await concuerda_con_el_informe(ent, informe)                            # la base concuerda con el informe
        despues_del_commit = await instantanea(ent.banco)

        h2, codigo2 = await ejecutar(ent, url_bd, token)
        r = h2.resultado
        assert codigo2 == 0 and r["status"] == 200 and r["body"]["repetida"] is True, h2.lineas
        assert documento_canonico(r["body"]["resultado"]) == documento_canonico(informe)    # el persistido, tal cual
        assert await instantanea(ent.banco) == despues_del_commit               # el reenvío no cambia NADA
        assert await numero_de("issues", ent.banco) == 3 and len(await informes(ent.banco)) == 1
        await concuerda_con_el_informe(ent, informe)


# ── Criterio 3 ──────────────────────────────────────────────────────────────────────────────────

class TestCriterio3FalloTrasElCommit:
    """El proceso SIGUE vivo, pero falla después del COMMIT y no puede completar la respuesta."""

    async def test_no_afirma_que_no_hubo_cambios_y_repetir_el_token_devuelve_lo_persistido(self, ent, url_bd):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO, DOS)
        token = await token_de(serie, ids.values())

        h, codigo = await ejecutar(ent, url_bd, token, "fallar_despues_del_commit")
        assert codigo == 0 and h.marca("COMMIT_HECHO"), h.lineas
        r = h.resultado
        assert r["status"] == 503 and r["body"]["detail"]["codigo"] == "resultado_incierto"
        texto = json.dumps(r["body"], ensure_ascii=False).lower()
        assert "no se ha cambiado nada" not in texto and "mismo token" in texto
        assert "resultado" not in r["body"] and "repetida" not in r["body"]      # no es un informe
        informe = await informe_persistido(ent, operacion_de(token))             # y SÍ hay efectos
        await concuerda_con_el_informe(ent, informe)
        antes = await instantanea(ent.banco)

        h2, codigo2 = await ejecutar(ent, url_bd, token)
        r2 = h2.resultado
        assert codigo2 == 0 and r2["status"] == 200 and r2["body"]["repetida"] is True, h2.lineas
        assert documento_canonico(r2["body"]["resultado"]) == documento_canonico(informe)
        assert await instantanea(ent.banco) == antes
        assert "no se ha cambiado nada" not in json.dumps(r2["body"], ensure_ascii=False).lower()


# ── Criterio 4 ──────────────────────────────────────────────────────────────────────────────────

class TestCriterio4CaducidadDelToken:
    """Un token caducado no crea ni modifica nada. La prueba separa los dos «no hay informe»: el que prueba que no se
    aplicó (dentro de la retención) y el que ya no puede saberse (pasada la retención)."""

    async def _sin_cambios(self, ent, antes: dict, informes_antes: list) -> None:
        assert await instantanea(ent.banco) == antes
        assert await informes(ent.banco) == informes_antes

    async def test_caducado_dentro_de_la_retencion_no_se_aplico_y_no_cambia_nada(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO, DOS)
        previo = await firmar(ent, serie, [(ids[UNO], "1")])
        assert (await confirmar(previo)).status_code == 200                    # estado no vacío: otra operación ya vinculó UNO
        antes, inf = await instantanea(ent.banco), await informes(ent.banco)
        caducado = await firmar(ent, serie, [(ids[UNO], "1"), (ids[DOS], "2")], ahora=time.time() - (TTL_SEGUNDOS + 60))

        r = await confirmar(caducado)
        d = r.json()["detail"]
        assert r.status_code == 410 and d["codigo"] == "token_caducado"
        assert d["puede_haberse_aplicado"] is False and d["mensaje"] == MENSAJE_CADUCADO_SIN_APLICAR
        await self._sin_cambios(ent, antes, inf)

    async def test_caducado_pasada_la_retencion_ya_no_se_puede_saber_y_tampoco_cambia_nada(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO, DOS)
        antes, inf = await instantanea(ent.banco), await informes(ent.banco)
        caducado = await firmar(ent, serie, [(ids[UNO], "1"), (ids[DOS], "2")],
                                ahora=time.time() - (RETENCION_HORAS * 3600 + 60))
        r = await confirmar(caducado)
        d = r.json()["detail"]
        assert r.status_code == 410 and d["puede_haberse_aplicado"] is True and d["mensaje"] == MENSAJE_CADUCADO_SIN_INFORME
        await self._sin_cambios(ent, antes, inf)

    async def test_caducado_con_informe_persistido_devuelve_ese_informe_y_no_toca_nada(self, ent):
        """Lectura fijada (ver la PR): la caducidad del token no oculta el informe de una operación que SÍ se aplicó."""
        from zascarr.services.vinculacion import VinculacionDeArchivos
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO)
        t0 = time.time() - 3600
        token = await firmar(ent, serie, [(ids[UNO], "1")], ahora=t0)
        async with ent.banco.fabrica() as s:                                    # se aplicó cuando el token aún valía
            await VinculacionDeArchivos(s, secret=SECRETO, ahora=t0 + 60).confirmar(token)
        antes, inf = await instantanea(ent.banco), await informes(ent.banco)

        r = await confirmar(token)                                              # ahora caducado, con su informe guardado
        assert r.status_code == 200 and r.json()["repetida"] is True
        assert documento_canonico(r.json()["resultado"]) == documento_canonico(inf[0][2])
        await self._sin_cambios(ent, antes, inf)


# ── Criterio 5 ──────────────────────────────────────────────────────────────────────────────────

async def envejecer(ent, operacion: str, *, minutos: int, token_vigente: bool) -> None:
    """Deja el informe como estaría pasado ese tiempo. El informe es inmutable (un UPDATE falla por diseño), así que se
    reescribe la fila entera —borrar e insertar el mismo documento—, lo único que permite la tabla."""
    async with ent.banco.fabrica() as s:
        fila = (await s.execute(text("SELECT series_id::text, resultado FROM vinculacion_operaciones "
                                     "WHERE operacion_id = CAST(:o AS uuid)"), {"o": operacion})).one()
        await s.execute(text("DELETE FROM vinculacion_operaciones WHERE operacion_id = CAST(:o AS uuid)"), {"o": operacion})
        await s.execute(text(
            "INSERT INTO vinculacion_operaciones (operacion_id, series_id, resultado, token_hasta, creada) VALUES "
            "(CAST(:o AS uuid), CAST(:s AS uuid), CAST(:r AS jsonb), now() + make_interval(hours => :v), "
            "now() - make_interval(mins => :m))"),
            {"o": operacion, "s": fila[0], "r": json.dumps(fila[1]), "v": 1 if token_vigente else -1, "m": minutos})
        await s.commit()


class TestCriterio5RetencionYPurga:
    """Las condiciones son las del contrato implementado (#103): informe más antiguo que `RETENCION_HORAS` **y** token
    ya caducado. La tarjeta las deja «pendientes de decisión»: los casos se calculan desde `RETENCION_HORAS` y no
    repiten el número, de modo que un cambio acordado se hace en un sitio y estas pruebas lo siguen."""

    @pytest.mark.parametrize("minutos,token_vigente,se_purga", [
        (RETENCION_HORAS * 60 - 1, False, False),     # un minuto antes de cumplir la retención, token caducado
        (RETENCION_HORAS * 60 + 1, True, False),      # pasada la retención, pero el token aún vale
        (RETENCION_HORAS * 60 + 1, False, True),      # las dos condiciones
    ], ids=["antes_de_la_retencion", "retencion_cumplida_con_token_vigente", "las_dos_condiciones"])
    async def test_ciclo_completo_con_un_informe_real(self, ent, minutos, token_vigente, se_purga):
        from zascarr.services.vinculacion import VinculacionDeArchivos
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO, DOS)
        t0 = time.time() - (RETENCION_HORAS * 3600 + 3600)                      # firmado hace más de la retención
        token = await firmar(ent, serie, [(ids[UNO], "1")], ahora=t0)
        async with ent.banco.fabrica() as s:
            await VinculacionDeArchivos(s, secret=SECRETO, ahora=t0 + 60).confirmar(token)
        operacion = operacion_de(token)
        informe = await informe_persistido(ent, operacion)
        await envejecer(ent, operacion, minutos=minutos, token_vigente=token_vigente)

        # Otra operación cualquiera ejecuta la purga acotada.
        otro = await firmar(ent, serie, [(ids[DOS], "2")])
        assert (await confirmar(otro)).status_code == 200
        quedan = {i[0] for i in await informes(ent.banco)}
        assert (operacion not in quedan) is se_purga and operacion_de(otro) in quedan

        # La purga solo toca el comprobante: los vínculos y los números siguen donde estaban.
        despues_de_purgar = await instantanea(ent.banco)
        await concuerda_con_el_informe_de(ent, informe, ids[UNO])
        r = await confirmar(token)                                              # el token de la operación, reenviado
        if se_purga:
            d = r.json()["detail"]
            assert r.status_code == 410 and d["codigo"] == "token_caducado"
            assert d["informe_disponible"] is False and d["puede_haberse_aplicado"] is True    # y de hecho SÍ se aplicó
            assert d["mensaje"] == MENSAJE_CADUCADO_SIN_INFORME
        else:
            assert r.status_code == 200 and r.json()["repetida"] is True
            assert documento_canonico(r.json()["resultado"]) == documento_canonico(informe)
        assert await instantanea(ent.banco) == despues_de_purgar                # reenviarlo nunca cambia nada


async def concuerda_con_el_informe_de(ent, informe: dict, archivo_id) -> None:
    """El archivo del informe sigue vinculado a su número (la purga no deshace nada)."""
    estados = {a["id"]: a["estado"] for a in informe["archivos"]}
    assert estados[str(archivo_id)] == "vinculado"
    async with ent.banco.fabrica() as s:
        issue = (await s.execute(text("SELECT issue_id FROM files WHERE id = CAST(:f AS uuid)"),
                                 {"f": str(archivo_id)})).scalar_one()
    assert issue is not None


# ── Criterio 6 ──────────────────────────────────────────────────────────────────────────────────

async def esperar_a_alguien_esperando_el_candado(ent, *, esperando: int, espera: float = 60.0) -> None:
    """Hasta que `esperando` backends están bloqueados de verdad en un candado de aviso (no «arrancando»)."""
    consulta = text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                    "AND wait_event_type = 'Lock' AND wait_event = 'advisory'")
    hasta = time.monotonic() + espera
    while time.monotonic() < hasta:
        async with ent.banco.fabrica() as s:
            if (await s.execute(consulta)).scalar_one() >= esperando:
                return
        await asyncio.sleep(0.05)
    raise AssertionError("nadie llegó a esperar el candado de la operación")


class TestCriterio6Concurrencia:

    async def test_seis_procesos_a_la_vez_con_el_mismo_token_producen_un_solo_conjunto_de_efectos(self, ent, url_bd):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO, DOS, TRES)
        token = await token_de(serie, ids.values())
        hijos = [await lanzar(ent, url_bd, token, barrera=True) for _ in range(6)]
        for h in hijos:
            await h.esperar("LISTO")                    # todos con la conexión caliente y la aplicación cargada
        for h in hijos:
            await h.soltar()
        codigos = [await h.terminar() for h in hijos]
        assert codigos == [0] * 6, [h.lineas for h in hijos]
        r = [h.resultado for h in hijos]
        assert [x["status"] for x in r] == [200] * 6
        assert sorted(x["body"]["repetida"] for x in r) == [False] + [True] * 5      # uno aplicó; cinco leyeron
        assert len({documento_canonico(x["body"]["resultado"]) for x in r}) == 1      # el mismo informe en todas
        assert {x["body"]["operacion_id"] for x in r} == {operacion_de(token)}
        informe = await informe_persistido(ent, operacion_de(token))
        assert documento_canonico(r[0]["body"]["resultado"]) == documento_canonico(informe)
        assert len(await informes(ent.banco)) == 1 and await numero_de("issues", ent.banco) == 3
        await concuerda_con_el_informe(ent, informe)

    async def test_quien_llega_con_la_operacion_en_curso_espera_y_devuelve_su_informe(self, ent, url_bd):
        """Determinista: el primero retiene su transacción (ya escrita, sin confirmar); los demás llegan DESPUÉS y no
        pueden terminar antes de que el primero confirme."""
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO, DOS)
        token = await token_de(serie, ids.values())
        a = await lanzar(ent, url_bd, token, "retener_antes_del_commit", retener=ESPERA_S)
        await a.esperar("RETENIENDO")
        otros = [await lanzar(ent, url_bd, token) for _ in range(2)]
        await esperar_a_alguien_esperando_el_candado(ent, esperando=2)
        assert await informes(ent.banco) == []          # mientras tanto, Postgres no tiene nada confirmado
        await a.soltar()                                # ahora sí: que A confirme
        assert await a.terminar() == 0 and [await h.terminar() for h in otros] == [0, 0]
        assert a.resultado["status"] == 200 and a.resultado["body"]["repetida"] is False
        for h in otros:
            assert h.resultado["status"] == 200 and h.resultado["body"]["repetida"] is True, h.lineas
            assert h.resultado["t_fin"] >= a.t("ANTES_DEL_COMMIT")             # no contestó antes de que A confirmara
            assert documento_canonico(h.resultado["body"]["resultado"]) == documento_canonico(a.resultado["body"]["resultado"])
        assert len(await informes(ent.banco)) == 1 and await numero_de("issues", ent.banco) == 2
        await concuerda_con_el_informe(ent, await informe_persistido(ent, operacion_de(token)))

    async def test_si_quien_tiene_la_operacion_muere_el_que_espera_la_aplica_una_sola_vez(self, ent, url_bd):
        """Recuperación bajo concurrencia: el primero muere con los candados puestos y la transacción sin confirmar; el
        segundo, que ya estaba esperando, obtiene el candado, no encuentra informe y aplica el lote una sola vez."""
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, UNO, DOS)
        token = await token_de(serie, ids.values())
        a = await lanzar(ent, url_bd, token, "retener_y_morir_antes_del_commit", retener=ESPERA_S)
        await a.esperar("RETENIENDO")
        b = await lanzar(ent, url_bd, token)
        await esperar_a_alguien_esperando_el_candado(ent, esperando=1)     # B espera de verdad a que A suelte la operación
        await a.soltar()                                        # A muere ahora, con la transacción abierta
        assert await a.terminar() == -9 and a.resultado is None
        assert await b.terminar() == 0, b.lineas
        assert b.resultado["status"] == 200 and b.resultado["body"]["repetida"] is False
        assert len(await informes(ent.banco)) == 1 and await numero_de("issues", ent.banco) == 2
        await concuerda_con_el_informe(ent, await informe_persistido(ent, operacion_de(token)))
        await sin_transacciones_abiertas(ent)
