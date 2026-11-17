# ruff: noqa: E501
"""F-03/F-04 (SecOps) — flujo aprobado de `restaurar_datos.sh --produccion` (BL-OPS2).

Lo que fijan estas pruebas, que es justo lo que faltaba:

- La copia se carga en una base **nueva** (`zascarr_restaurando`) **con la app sirviendo**, se comprueba y solo
  después se para la app; la base viva no se destruye en ningún momento (BR-06, FR-19/FR-20).
- La copia previa `rollback-safety_<TS>.sql.gz` y la relectura de la seguridad vigente se hacen **con la app
  parada** (FR-20.6, FR-21; F-04).
- El cambio es por **renombrado** (`zascarr` → `zascarr_previa`, `zascarr_restaurando` → `zascarr`) y la vuelta
  atrás también; no hay `dropdb` de la base viva ni de la previa antes de comprobar el arranque (FR-22/FR-23).
- El script escribe `ops-restaurar.json` en cada fase, con solo códigos y números, y deja `base_en_su_sitio`
  correcto en cada fallo (FR-24).
- Los recuentos son genéricos para todas las tablas base del dump (F-15/AC-51).
"""
from __future__ import annotations

import fcntl
import gzip
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from tests._restaurar_produccion import (
    estado_restaurar,
    eventos,
    ejecutar,
    plantilla_eventos,
    preparar,
    sql_dump,
)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="scripts de shell POSIX")

FASES = {"verificando", "preparando", "restaurando", "comprobando", "parando",
         "seguridad", "copia_previa", "cambiando", "arrancando"}


def _sin_violaciones(ctx) -> None:
    texto = "\n".join(eventos(ctx))
    assert "VIOLACION" not in texto, texto


# ── Camino feliz ────────────────────────────────────────────────────────────────────────────────────────────────
def test_restaura_en_base_nueva_y_cambia_por_renombrado(tmp_path):
    """BR-06/F-03: la base viva no se toca hasta que la nueva está comprobada; el cambio es por renombrado."""
    ctx = preparar(tmp_path)
    r = ejecutar(ctx, extra_env={"FAKE_ENFORCE_STOP": "1"})
    assert r.returncode == 0, r.stdout + r.stderr
    _sin_violaciones(ctx)
    ev = eventos(ctx)

    # La base viva no se recrea ni se tira: no hay `createdb zascarr` ni `dropdb zascarr`.
    assert "createdb zascarr" not in ev
    assert "dropdb zascarr" not in ev
    # La copia se carga en la base nueva ANTES de parar la app.
    assert ev.index("createdb zascarr_restaurando") < ev.index("stop zascarr")
    # El cambio es por renombrado, y el orden es el aprobado: parar → seguridad → copia previa → renombrar.
    assert ev.index("stop zascarr") < ev.index("reaplicar_seguridad")
    assert ev.index("reaplicar_seguridad") < ev.index("pg_dump zascarr")
    assert ev.index("pg_dump zascarr") < ev.index("renombrar zascarr>zascarr_previa")
    assert ev.index("renombrar zascarr>zascarr_previa") < ev.index("renombrar zascarr_restaurando>zascarr")
    # La previa solo se borra DESPUÉS de arrancar y comprobar; la restaurada entra en su sitio, no se borra.
    assert ev.index("renombrar zascarr_restaurando>zascarr") < ev.index("up zascarr")
    assert ev.index("dropdb zascarr_previa") > ev.index("up zascarr")
    assert "dropdb zascarr_restaurando" not in ev

    # Copia previa verificada, 0600, y en el directorio de copias.
    seguridad = sorted(ctx["backup"].glob("rollback-safety_*.sql.gz"))
    assert len(seguridad) == 1
    assert stat.S_IMODE(seguridad[0].stat().st_mode) == 0o600
    assert gzip.decompress(seguridad[0].read_bytes()).startswith(b"--\n-- PostgreSQL database dump")

    # La seguridad vigente se conserva y lo de integraciones viene de la copia (FR-34).
    reaplicado = ctx["restore"].read_text(encoding="utf-8")
    assert '"auth_mode":"password"' in reaplicado
    assert '"auth_password_hash":"hash-nuevo"' in reaplicado
    assert '"prowlarr_api_key":"clave-copia"' in reaplicado
    assert '"comicvine_enabled":false' in reaplicado
    assert '"webhook_url":"https://webhook-nuevo"' in reaplicado
    assert '"auth_session_version":8' in reaplicado
    assert "sk-nueva" in reaplicado and "sk-vieja" not in reaplicado

    # Estado final: solo códigos y números.
    estado = estado_restaurar(ctx)
    assert estado is not None
    assert estado["schema"] == 1
    assert estado["copia"] == "backup-20260101_120000"
    assert estado["resultado"] == "hecha"
    assert estado["error"] is None
    assert estado["base_en_su_sitio"] is True
    assert estado["fase"] in FASES
    assert isinstance(estado["recuentos"], dict) and estado["recuentos"]["series"] == 2
    assert estado["actualizado_epoch"] >= estado["inicio_epoch"] > 0
    assert stat.S_IMODE((ctx["status"] / "ops-restaurar.json").stat().st_mode) == 0o644
    assert not list(ctx["status"].glob(".ops-restaurar.json.tmp*"))


def test_copia_previa_y_seguridad_exigen_la_app_parada(tmp_path):
    """F-04/FR-20.6/FR-21: si la app sigue sirviendo, el propio falso aborta con una violación de orden."""
    ctx = preparar(tmp_path)
    r = ejecutar(ctx, extra_env={"FAKE_ENFORCE_STOP": "1"})
    assert r.returncode == 0, r.stdout + r.stderr
    _sin_violaciones(ctx)


def test_no_imprime_los_valores_de_seguridad(tmp_path):
    """AC-37: los centinelas de la fila vigente no aparecen en la salida del script."""
    ctx = preparar(
        tmp_path,
        seguridad_actual={
            "auth_mode": "password", "auth_password_hash": "CENTINELA-HASH",
            "secret_key": "CENTINELA-SK", "base_url": "CENTINELA-URL",
            "auth_session_version": 1, "comicvine_enabled": False, "fuentes_heredadas": False,
        },
    )
    r = ejecutar(ctx, extra_env={"FAKE_ENFORCE_STOP": "1"})
    assert r.returncode == 0, r.stdout + r.stderr
    salida = r.stdout + r.stderr
    for centinela in ("CENTINELA-HASH", "CENTINELA-SK", "CENTINELA-URL"):
        assert centinela not in salida, salida
    assert "CENTINELA" not in json.dumps(estado_restaurar(ctx))


# ── Fallos antes del cambio: la base viva queda idéntica ───────────────────────────────────────────────────────
def test_un_fallo_al_cargar_el_dump_no_toca_la_base_viva(tmp_path):
    """AC-31: fallo en la carga ⇒ `zascarr_restaurando` desaparece, la viva no se toca y la app nunca se para."""
    ctx = preparar(tmp_path)
    r = ejecutar(ctx, extra_env={"FAKE_ENFORCE_STOP": "1", "FAKE_RESTORE_FAIL": "1"})
    assert r.returncode != 0
    ev = eventos(ctx)
    assert "createdb zascarr_restaurando" in ev
    assert "dropdb zascarr_restaurando" in ev
    assert "stop zascarr" not in ev and "pg_dump zascarr" not in ev
    assert not any(e.startswith("renombrar ") for e in ev)
    assert not (ctx["estado_docker"] / "db.zascarr_restaurando").exists()
    assert (ctx["estado_docker"] / "db.zascarr").exists()
    estado = estado_restaurar(ctx)
    assert estado["resultado"] == "fallida" and estado["error"] == "restauracion_fallida"
    assert estado["base_en_su_sitio"] is True


def test_una_restauracion_anterior_sin_cerrar_aborta_antes_de_tocar_nada(tmp_path):
    """FR-19.2: `zascarr_previa` sobrante ⇒ precondition_failed, sin crear nada."""
    ctx = preparar(tmp_path)
    (ctx["estado_docker"] / "db.zascarr_previa").write_text("", encoding="utf-8")
    r = ejecutar(ctx)
    assert r.returncode != 0
    ev = eventos(ctx)
    assert "createdb zascarr_restaurando" not in ev
    assert "stop zascarr" not in ev
    estado = estado_restaurar(ctx)
    assert estado["error"] == "precondition_failed" and estado["base_en_su_sitio"] is True


# ── F-15/AC-51: recuentos genéricos de todas las tablas base ───────────────────────────────────────────────────
def test_una_tabla_cargada_a_medias_se_detecta_por_el_recuento_generico(tmp_path):
    """AC-51: una tabla que no está en la lista de siempre (0030/0031 y futuras) también se cuenta."""
    ctx = preparar(tmp_path, sql=sql_dump(extra={"colecciones": 2}))
    r = ejecutar(ctx, extra_env={"FAKE_ENFORCE_STOP": "1", "FAKE_COUNT_colecciones": "1"})
    assert r.returncode != 0
    ev = eventos(ctx)
    assert "createdb zascarr_restaurando" in ev and "dropdb zascarr_restaurando" in ev
    assert "stop zascarr" not in ev
    estado = estado_restaurar(ctx)
    assert estado["resultado"] == "fallida" and estado["error"] == "verificacion_fallida"
    assert estado["base_en_su_sitio"] is True
    assert (ctx["estado_docker"] / "db.zascarr").exists()


def test_una_tabla_base_nueva_del_dump_se_cuenta_sin_tocar_el_script(tmp_path):
    """AC-51 (segunda mitad): una tabla base nueva con el recuento correcto pasa sin cambios en el script."""
    ctx = preparar(tmp_path, sql=sql_dump(extra={"tabla_nueva_2099": 4}))
    r = ejecutar(ctx, extra_env={"FAKE_ENFORCE_STOP": "1", "FAKE_COUNT_tabla_nueva_2099": "4"})
    assert r.returncode == 0, r.stdout + r.stderr
    assert estado_restaurar(ctx)["resultado"] == "hecha"


# ── Fallos en el cambio y en el arranque: vuelta atrás por renombrado ──────────────────────────────────────────
def test_fallo_al_renombrar_la_base_nueva_vuelve_atras_por_renombrado(tmp_path):
    """FR-22: si falla el segundo renombrado, la previa vuelve a ser `zascarr` y la nueva se retira sin tocar datos."""
    ctx = preparar(tmp_path)
    r = ejecutar(ctx, extra_env={"FAKE_ENFORCE_STOP": "1",
                                 "FAKE_RENAME_FAIL": "zascarr_restaurando>zascarr"})
    assert r.returncode != 0
    ev = eventos(ctx)
    assert "renombrar zascarr>zascarr_previa" in ev
    assert "renombrar zascarr_previa>zascarr" in ev                    # vuelta atrás
    assert "renombrar_fallido zascarr_restaurando>zascarr" in ev
    assert ev.index("renombrar zascarr_previa>zascarr") > ev.index("renombrar zascarr>zascarr_previa")
    assert ev.index("up zascarr") > ev.index("renombrar zascarr_previa>zascarr")
    assert "dropdb zascarr_restaurando" in ev
    assert "dropdb zascarr" not in ev
    estado = estado_restaurar(ctx)
    assert estado["resultado"] == "fallida" and estado["error"] == "cambio_fallido"
    assert estado["base_en_su_sitio"] is True
    assert (ctx["estado_docker"] / "db.zascarr").exists()
    assert not (ctx["estado_docker"] / "db.zascarr_previa").exists()
    assert not (ctx["estado_docker"] / "app_parada").exists()          # la app se vuelve a arrancar


def test_fallo_al_arrancar_deshace_por_renombrado_y_borra_la_fallida_solo_al_final(tmp_path):
    """FR-23/AC-32: se deshace sin borrar antes de recuperar; `zascarr_fallida` se borra solo tras comprobar."""
    ctx = preparar(tmp_path)
    r = ejecutar(ctx, extra_env={"FAKE_ENFORCE_STOP": "1", "FAKE_HEALTH_FALLS": "2",
                                 "HEALTH_TIMEOUT": "2"})
    assert r.returncode != 0
    ev = eventos(ctx)
    assert ev.count("up zascarr") >= 2
    assert "renombrar zascarr>zascarr_fallida" in ev
    assert "renombrar zascarr_previa>zascarr" in ev
    assert "dropdb zascarr_fallida" in ev
    assert ev.index("dropdb zascarr_fallida") > max(i for i, e in enumerate(ev) if e == "up zascarr")
    assert "dropdb zascarr" not in ev
    estado = estado_restaurar(ctx)
    assert estado["resultado"] == "fallida" and estado["error"] == "arranque_fallido"
    assert estado["base_en_su_sitio"] is True


def test_recuperacion_fallida_solo_si_la_copia_previa_y_la_previa_existen(tmp_path):
    """FR-22/AC-50: con la copia previa y `zascarr_previa` presentes ⇒ recuperacion_fallida y app parada."""
    ctx = preparar(tmp_path)
    r = ejecutar(ctx, extra_env={"FAKE_ENFORCE_STOP": "1", "FAKE_HEALTH_FALLS": "200",
                                 "FAKE_RENAME_FAIL": "zascarr_previa>zascarr",
                                 "HEALTH_TIMEOUT": "1"})
    assert r.returncode != 0
    ev = eventos(ctx)
    assert "renombrar zascarr>zascarr_fallida" in ev
    assert "renombrar_fallido zascarr_previa>zascarr" in ev
    assert "dropdb zascarr_fallida" not in ev
    estado = estado_restaurar(ctx)
    assert estado["error"] == "recuperacion_fallida"
    assert estado["base_en_su_sitio"] is False
    assert (ctx["estado_docker"] / "app_parada").exists()              # la app queda parada
    assert list(ctx["backup"].glob("rollback-safety_*.sql.gz"))


def test_sin_copia_previa_ni_previa_el_fallo_es_unexpected(tmp_path):
    """AC-50: `recuperacion_fallida` no se emite si falta lo que haría posible recuperar."""
    ctx = preparar(tmp_path)
    r = ejecutar(ctx, extra_env={"FAKE_ENFORCE_STOP": "1", "FAKE_HEALTH_FALLS": "200",
                                 "FAKE_RENAME_FAIL": "zascarr>zascarr_fallida,zascarr_previa>zascarr",
                                 "FAKE_OCULTA_PREVIA": "1", "HEALTH_TIMEOUT": "1"})
    assert r.returncode != 0
    estado = estado_restaurar(ctx)
    assert estado["error"] == "unexpected"
    assert estado["base_en_su_sitio"] is False


# ── Cerrojo (AC-36) ─────────────────────────────────────────────────────────────────────────────────────────────
def test_el_cerrojo_ocupado_sale_75_con_omitida_y_sin_escribir_ops_restaurar(tmp_path):
    """AC-36: cerrojo tomado ⇒ 75, `omitida.json` con `accion:"restaurar"` y sin tocar el estado de la restauración."""
    ctx = preparar(tmp_path)
    ruta = ctx["root"] / "ops.lock"
    with open(ruta, "w", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            r = ejecutar(ctx)
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
    assert r.returncode == 75, r.stdout + r.stderr
    omitida = json.loads((ctx["status"] / "omitida.json").read_text(encoding="utf-8"))
    assert omitida["accion"] == "restaurar"
    assert omitida["motivo"] == "operacion_en_curso"
    assert isinstance(omitida["omitida_epoch"], int)
    assert not (ctx["status"] / "ops-restaurar.json").exists()
    assert not any(e.startswith("createdb ") for e in eventos(ctx))
