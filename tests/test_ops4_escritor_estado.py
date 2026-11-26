"""Pruebas del escritor atómico y de la guarda de monotonía; sin sistema real.

El estado que lee la app corre con PUID:PGID sobre un montaje `ro`: el fichero
debe quedar `0640 root:<grupo>` (no `0600 root:root`) para que la app pueda
leerlo, y la guarda de transición no puede pisar un terminal.
"""
from __future__ import annotations

import json
import multiprocessing
import os
import stat

import pytest

from deploy.ops.escritor_estado_actualizar_ops4 import (
    CODIGO_EXITO,
    FASES,
    MAX_BYTES,
    MODO_ESTADO,
    UNIDAD,
    ResultadoEscritura,
    ResultadoLectura,
    calcular_transicion,
    escribir_estado,
    estado_inicial,
    leer_estado_estricto,
    propietario_servicio,
    publicar_transicion,
    validar_estado,
)

ID = "a" * 32
AHORA = 1_800_000_000
ESTADO = {
    "schema": 1, "id": ID, "estado": "aceptada",
    "inicio_epoch": AHORA, "actualizado_epoch": AHORA,
}


def _inicial(tmp_path, *, estado="en_curso", inicio=AHORA - 5, actualizado=AHORA - 5):
    ruta = tmp_path / "estado.json"
    assert escribir_estado(ruta, {
        "schema": 1, "id": ID, "estado": estado,
        "inicio_epoch": inicio, "actualizado_epoch": actualizado,
    }) is ResultadoEscritura.OK
    return ruta


def _leer(ruta):
    return json.loads(ruta.read_text(encoding="utf-8"))


# ── Publicación atómica ─────────────────────────────────────────────────────


def test_publica_json_canonico(tmp_path) -> None:
    destino = tmp_path / "estado.json"
    assert escribir_estado(destino, ESTADO) is ResultadoEscritura.OK
    assert json.loads(destino.read_text(encoding="utf-8")) == ESTADO
    assert destino.read_text(encoding="utf-8").startswith('{"actualizado_epoch":')


def test_original_permanece_si_falla_fsync_del_archivo(tmp_path) -> None:
    destino = tmp_path / "estado.json"
    destino.write_text('{"antiguo":true}\n', encoding="utf-8")

    def fsync_falla(_fd: int) -> None:
        raise OSError("fsync")

    assert escribir_estado(destino, ESTADO, fsync=fsync_falla) is ResultadoEscritura.INCIERTO
    assert destino.read_text(encoding="utf-8") == '{"antiguo":true}\n'
    assert not list(tmp_path.glob(".estado.json.tmp-*"))


def test_original_permanece_si_falla_rename(tmp_path) -> None:
    destino = tmp_path / "estado.json"
    destino.write_text('{"antiguo":true}\n', encoding="utf-8")

    def replace_falla(_a: str, _b: str, _fd: int) -> None:
        raise OSError("rename")

    assert escribir_estado(destino, ESTADO, replace=replace_falla) is ResultadoEscritura.INCIERTO
    assert destino.read_text(encoding="utf-8") == '{"antiguo":true}\n'
    assert not list(tmp_path.glob(".estado.json.tmp-*"))


def test_fallo_fsync_del_directorio_es_incierto(tmp_path) -> None:
    destino = tmp_path / "estado.json"
    llamadas = []

    def fsync_dos_veces(fd: int) -> None:
        llamadas.append(fd)
        if len(llamadas) == 2:
            raise OSError("directorio")

    assert escribir_estado(destino, ESTADO, fsync=fsync_dos_veces) is ResultadoEscritura.INCIERTO
    assert destino.exists()


@pytest.mark.parametrize("datos", [None, [], {"x": object()}, {"x": float("nan")}])
def test_datos_invalidos_no_publican(tmp_path, datos) -> None:
    destino = tmp_path / "estado.json"
    assert escribir_estado(destino, datos) is ResultadoEscritura.INVALIDO
    assert not destino.exists()


def test_tamano_excesivo(tmp_path) -> None:
    destino = tmp_path / "estado.json"
    assert escribir_estado(destino, {"x": "a" * MAX_BYTES}) is ResultadoEscritura.INVALIDO
    assert not destino.exists()


def test_directorio_inexistente_falla_cerrado(tmp_path) -> None:
    assert escribir_estado(tmp_path / "no" / "estado.json", ESTADO) is ResultadoEscritura.INVALIDO


@pytest.mark.parametrize("fsync,replace", [(None, None), (lambda _f: None, None)])
def test_callbacks_invalidos_no_publican(tmp_path, fsync, replace) -> None:
    destino = tmp_path / "estado.json"
    resultado = escribir_estado(destino, ESTADO, fsync=fsync, replace=replace)
    assert resultado is ResultadoEscritura.INCIERTO
    assert not destino.exists() or json.loads(destino.read_text()) == ESTADO


# ── Permisos del fichero de estado (H-5) ────────────────────────────────────


def test_fichero_queda_0640_para_que_la_app_pueda_leerlo(tmp_path) -> None:
    destino = tmp_path / "estado.json"
    assert escribir_estado(destino, ESTADO) is ResultadoEscritura.OK
    assert MODO_ESTADO == 0o640
    assert stat.S_IMODE(destino.stat().st_mode) == 0o640
    assert not destino.stat().st_mode & stat.S_IWGRP
    assert not destino.stat().st_mode & stat.S_IWOTH


def test_propietario_explicito_se_aplica(tmp_path) -> None:
    destino = tmp_path / "estado.json"
    resultado = escribir_estado(
        destino, ESTADO, propietario=(os.getuid(), os.getgid()),
    )
    assert resultado is ResultadoEscritura.OK
    info = destino.stat()
    assert (info.st_uid, info.st_gid) == (os.getuid(), os.getgid())
    assert stat.S_IMODE(info.st_mode) == 0o640


def test_propietario_servicio_usa_el_grupo_del_directorio(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    destino = tmp_path / "estado.json"
    assert propietario_servicio(destino) == (0, tmp_path.stat().st_gid)


def test_propietario_servicio_sin_privilegios_no_cambia_dueno(monkeypatch) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    assert propietario_servicio("/var/lib/zascarr/ops/actualizar-status.json") is None


# ── Lector estricto ─────────────────────────────────────────────────────────


def test_lector_estricto_acepta_el_esquema_1(tmp_path) -> None:
    ruta = _inicial(tmp_path)
    lectura, datos = leer_estado_estricto(ruta)
    assert lectura is ResultadoLectura.OK
    assert datos is not None and datos["id"] == ID


@pytest.mark.parametrize("payload", [
    b"",
    b"[]",
    b'{"schema":1,"schema":1}',
    b'{"schema":1}',
    f'{{"schema":1,"id":"{ID}","estado":"aceptada","inicio_epoch":1,'
    f'"actualizado_epoch":1,"extra":1}}'.encode(),
    f'{{"schema":2,"id":"{ID}","estado":"aceptada","inicio_epoch":1,'
    f'"actualizado_epoch":1}}'.encode(),
    b'{"schema":1,"id":"zz","estado":"aceptada","inicio_epoch":1,"actualizado_epoch":1}',
    f'{{"schema":1,"id":"{ID}","estado":"raro","inicio_epoch":1,'
    f'"actualizado_epoch":1}}'.encode(),
    f'{{"schema":1,"id":"{ID}","estado":"aceptada","inicio_epoch":2,'
    f'"actualizado_epoch":1}}'.encode(),
])
def test_lector_estricto_falla_cerrado(tmp_path, payload) -> None:
    ruta = tmp_path / "estado.json"
    ruta.write_bytes(payload)
    lectura, datos = leer_estado_estricto(ruta)
    assert lectura is ResultadoLectura.INVALIDO
    assert datos is None


def test_lector_estricto_no_sigue_enlaces_ni_abre_directorios(tmp_path) -> None:
    real = _inicial(tmp_path)
    enlace = tmp_path / "enlace.json"
    enlace.symlink_to(real)
    assert leer_estado_estricto(enlace)[0] is ResultadoLectura.INVALIDO
    assert leer_estado_estricto(tmp_path)[0] is ResultadoLectura.INVALIDO
    assert leer_estado_estricto(tmp_path / "no-existe.json")[0] is ResultadoLectura.AUSENTE


def test_lector_estricto_rechaza_grupo_o_otros_con_escritura(tmp_path) -> None:
    ruta = _inicial(tmp_path)
    ruta.chmod(0o664)
    assert leer_estado_estricto(ruta)[0] is ResultadoLectura.INVALIDO


# ── Guarda de monotonía (publicar_transicion) ───────────────────────────────


def test_transicion_conserva_id_e_inicio_y_actualiza_epoch(tmp_path) -> None:
    ruta = _inicial(tmp_path)
    assert publicar_transicion(
        ruta, "hecha", ahora=AHORA + 10, id_=ID, inicio_epoch=AHORA - 5,
        fase="fin", codigo="success:exited:0",
    ) is ResultadoEscritura.OK
    datos = _leer(ruta)
    assert datos["estado"] == "hecha"
    assert datos["id"] == ID
    assert datos["inicio_epoch"] == AHORA - 5
    assert datos["actualizado_epoch"] == AHORA + 10


def test_terminal_no_se_pisa(tmp_path) -> None:
    ruta = _inicial(tmp_path, estado="hecha")
    for nuevo in ("en_curso", "fallida", "incierta"):
        assert publicar_transicion(
            ruta, nuevo, ahora=AHORA + 10, id_=ID, inicio_epoch=AHORA - 5,
        ) is ResultadoEscritura.INVALIDO
    datos = _leer(ruta)
    assert datos["estado"] == "hecha"
    assert datos["actualizado_epoch"] == AHORA - 5


def test_no_baja_actualizado_epoch(tmp_path) -> None:
    ruta = _inicial(tmp_path, inicio=AHORA - 5, actualizado=AHORA)
    assert publicar_transicion(
        ruta, "hecha", ahora=AHORA - 1, id_=ID, inicio_epoch=AHORA - 5,
        fase="fin", codigo="success:exited:0",
    ) is ResultadoEscritura.INVALIDO
    assert _leer(ruta)["estado"] == "en_curso"


@pytest.mark.parametrize("cambios", [
    {"id_": "b" * 32, "inicio_epoch": AHORA - 5},
    {"id_": ID, "inicio_epoch": AHORA - 100},
])
def test_rechaza_cambiar_id_o_inicio(tmp_path, cambios) -> None:
    ruta = _inicial(tmp_path)
    assert publicar_transicion(
        ruta, "hecha", ahora=AHORA + 10, fase="fin",
        codigo="success:exited:0", **cambios,
    ) is ResultadoEscritura.INVALIDO
    assert _leer(ruta)["estado"] == "en_curso"


def test_reloj_invertido_no_escribe(tmp_path) -> None:
    ruta = _inicial(tmp_path, inicio=AHORA + 100, actualizado=AHORA + 100)
    assert publicar_transicion(
        ruta, "hecha", ahora=AHORA, id_=ID, inicio_epoch=AHORA + 100,
        fase="fin", codigo="success:exited:0",
    ) is ResultadoEscritura.INVALIDO
    datos = _leer(ruta)
    assert datos["estado"] == "en_curso"
    assert datos["actualizado_epoch"] == AHORA + 100


def test_sin_estado_no_crea_nada(tmp_path) -> None:
    ruta = tmp_path / "no-existe.json"
    assert publicar_transicion(
        ruta, "hecha", ahora=AHORA, id_=ID, inicio_epoch=AHORA - 5,
        fase="fin", codigo="success:exited:0",
    ) is ResultadoEscritura.INVALIDO
    assert not ruta.exists()


def test_transicion_con_fallo_durable_es_incierta_y_no_pisa(tmp_path) -> None:
    ruta = _inicial(tmp_path)

    def fsync_falla(_fd: int) -> None:
        raise OSError("fsync")

    assert publicar_transicion(
        ruta, "hecha", ahora=AHORA + 10, id_=ID, inicio_epoch=AHORA - 5,
        fase="fin", codigo="success:exited:0", fsync=fsync_falla,
    ) is ResultadoEscritura.INCIERTO
    assert _leer(ruta)["estado"] == "en_curso"


@pytest.mark.parametrize("estado", ["", "ok", "HECHA", None, 1])
def test_transicion_solo_acepta_estados_cerrados(tmp_path, estado) -> None:
    ruta = _inicial(tmp_path)
    assert publicar_transicion(ruta, estado, ahora=AHORA) is ResultadoEscritura.INVALIDO


# ── Contrato v2 y cerrojo de publicación (B1) ───────────────────────────────


def test_estado_inicial_v2_y_validacion_cerrada(tmp_path) -> None:
    ini = estado_inicial(ID, AHORA)
    assert set(ini) == {
        "schema", "id", "unidad", "estado", "fase", "inicio_epoch",
        "actualizado_epoch", "head0", "sha_destino", "sha_actual",
        "resultado", "codigo",
    }
    assert (ini["schema"], ini["unidad"], ini["estado"]) == (2, UNIDAD, "aceptada")
    assert ini["fase"] == FASES[0]
    assert ini["head0"] is None and ini["resultado"] is None
    assert validar_estado(ini) and validar_estado(ESTADO)
    assert not validar_estado({**ini, "extra": 1})
    assert not validar_estado({**ini, "fase": "fin"})
    assert not validar_estado({**ini, "estado": "hecha", "fase": "git", "resultado": "hecha"})

    ruta = tmp_path / "estado.json"
    assert escribir_estado(ruta, ini) is ResultadoEscritura.OK
    assert _leer(ruta) == ini


def test_calcular_transicion_es_pura_y_monotona() -> None:
    ini = estado_inicial(ID, AHORA)
    antes = json.loads(json.dumps(ini))
    transicion = calcular_transicion(
        ini, "en_curso", ahora=AHORA + 10, fase="copia",
        head0="a" * 40, sha_destino="b" * 40,
    )
    assert ini == antes, "calcular_transicion no puede mutar la entrada"
    assert transicion is not None
    assert (transicion["estado"], transicion["fase"]) == ("en_curso", "copia")
    assert (transicion["head0"], transicion["sha_destino"]) == ("a" * 40, "b" * 40)
    assert calcular_transicion(transicion, "en_curso", ahora=AHORA + 11, fase="preparacion") is None
    assert calcular_transicion(
        transicion, "en_curso", ahora=AHORA + 11, fase="git", head0="c" * 40,
    ) is None
    assert calcular_transicion(transicion, "en_curso", ahora=AHORA + 9, fase="git") is None
    terminal = calcular_transicion(
        transicion, "hecha", ahora=AHORA + 20, fase="fin", codigo=CODIGO_EXITO,
    )
    assert terminal is not None
    assert (terminal["resultado"], terminal["codigo"]) == ("hecha", CODIGO_EXITO)
    assert calcular_transicion(terminal, "en_curso", ahora=AHORA + 21, fase="git") is None
    assert calcular_transicion(ESTADO, "en_curso", ahora=AHORA + 10, fase="preparacion") is not None


def _transicionar_en_bucle(ruta, vueltas: int) -> None:
    for _ in range(vueltas):
        lectura, actual = leer_estado_estricto(ruta)
        if lectura is not ResultadoLectura.OK or actual is None:
            return
        if actual["estado"] in {"hecha", "fallida", "incierta"}:
            return
        publicar_transicion(
            ruta, "en_curso", ahora=actual["actualizado_epoch"] + 1, fase="git",
        )


def _cerrar_terminal(ruta) -> None:
    for _ in range(2000):
        lectura, actual = leer_estado_estricto(ruta)
        if lectura is not ResultadoLectura.OK or actual is None:
            # El lector estricto devuelve INVALIDO si el inodo cambia mientras
            # lo lee (reemplazo atómico); un lector que sondea debe reintentar.
            continue
        if actual["estado"] == "hecha":
            return
        if publicar_transicion(
            ruta, "hecha", ahora=actual["actualizado_epoch"] + 1,
            fase="fin", codigo=CODIGO_EXITO,
        ) is ResultadoEscritura.OK:
            return


def test_publicacion_concurrente_no_pierde_terminal(tmp_path) -> None:
    """Dos procesos publican a la vez: el terminal nunca se pierde por la carrera."""
    ruta = tmp_path / "estado.json"
    assert escribir_estado(ruta, estado_inicial(ID, AHORA)) is ResultadoEscritura.OK
    contexto = multiprocessing.get_context("fork")
    fases = contexto.Process(target=_transicionar_en_bucle, args=(ruta, 400))
    cierre = contexto.Process(target=_cerrar_terminal, args=(ruta,))
    fases.start()
    cierre.start()
    fases.join(60)
    cierre.join(60)
    assert fases.exitcode == 0 and cierre.exitcode == 0
    datos = _leer(ruta)
    assert datos["estado"] == "hecha"
    assert (datos["fase"], datos["resultado"], datos["codigo"]) == ("fin", "hecha", CODIGO_EXITO)
