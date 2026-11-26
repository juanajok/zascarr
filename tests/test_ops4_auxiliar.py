"""Auxiliar privilegiado aislado: no ejecuta systemd ni instala unidades."""
from __future__ import annotations

import json
import os

import pytest

from deploy.ops import protocolo_actualizar_v4_ops4 as protocolo
from deploy.ops import zascarr_actualizar_aux as auxiliar
from deploy.ops.escritor_estado_actualizar_ops4 import (
    ResultadoEscritura,
    escribir_estado,
    publicar_transicion,
)
from deploy.ops.zascarr_actualizar_aux import (
    UNIDAD,
    Respuesta,
)
from deploy.ops.zascarr_actualizar_aux import (
    procesar as procesar_real,
)
from zascarr.services.autorizacion_actualizacion import crear_autorizacion
from zascarr.services.ops_actualizacion_v4 import construir_peticion_v4

CLAVE = bytes(range(32))
ID = "a" * 32
AHORA = 1_800_000_000


def crear_testigo(id_: str = ID) -> bytes:
    return crear_autorizacion(clave=CLAVE, id_=id_, ahora=AHORA, ttl=60)


def peticion(*, id_: str = ID, ahora: int = AHORA, token: bytes | None = None) -> bytes:
    return construir_peticion_v4(
        CLAVE, id=id_, creada=ahora,
        autorizacion=crear_testigo() if token is None else token,
    )


class Dobles:
    def __init__(self, *, cerrojo=False, inicio=True,
                 escribir=ResultadoEscritura.OK,
                 transicionar=ResultadoEscritura.OK) -> None:
        self.escritura = escribir
        self.transicion = transicionar
        self.estados: list[dict] = []
        self.cerrojo = cerrojo
        self.inicio = inicio
        self.usados: set[str] = set()
        self.intentos: set[str] = set()
        self.llamadas: list[tuple[str, str]] = []

    def reclamar(self, id_: str) -> bool:
        self.llamadas.append(("reclamar", id_))
        if id_ in self.usados:
            return False
        self.usados.add(id_)
        return True

    def iniciar(self, unidad: str) -> bool:
        self.llamadas.append(("iniciar", unidad))
        return self.inicio

    def escribir(self, datos: dict):
        self.llamadas.append(("escribir", datos["estado"]))
        self.estados.append(datos)
        return self.escritura

    def transicionar(self, estado: str, *, ahora: int, id_: str,
                     inicio_epoch: int, fase: str, codigo: str):
        self.llamadas.append(("transicionar", estado))
        self.estados.append({
            "estado": estado, "ahora": ahora, "id": id_,
            "inicio_epoch": inicio_epoch, "fase": fase, "codigo": codigo,
        })
        return self.transicion

    def ocupado(self) -> bool:
        self.llamadas.append(("cerrojo", ""))
        return self.cerrojo


def procesar(linea: bytes, **kwargs) -> Respuesta:
    """Ejercita las pruebas históricas con dependencias B2 completas."""
    reclamador = kwargs["reclamar_uso"]
    doble = getattr(reclamador, "__self__", None)
    intentos = doble.intentos if isinstance(doble, Dobles) else set()

    def crear_intento(id_: str) -> bool:
        if id_ in intentos:
            return False
        intentos.add(id_)
        return True

    return procesar_real(
        linea, **kwargs, admitir=lambda: object(), liberar=lambda _token: None,
        leer_estado=lambda: None, crear_intento=crear_intento,
        existe_intento=lambda id_: id_ in intentos,
        reclamar_consumo=reclamador, esperar=lambda _id: "confirmada",
    )


def ejecutar(linea: bytes, dobles: Dobles) -> Respuesta:
    return procesar(
        linea, clave=CLAVE, ahora=AHORA, reclamar_uso=dobles.reclamar,
        iniciar=dobles.iniciar, cerrojo_ocupado=dobles.ocupado,
        escribir=dobles.escribir, transicionar=dobles.transicionar,
    )


def test_acepta_una_vez_y_usa_unidad_fija() -> None:
    dobles = Dobles()
    respuesta = ejecutar(peticion(), dobles)
    assert respuesta.resultado == "aceptada"
    assert respuesta.id == ID
    assert ("iniciar", UNIDAD) in dobles.llamadas
    assert UNIDAD == "zascarr-actualizar.service"
    cuerpo = json.loads(respuesta.linea())
    assert cuerpo == {"v": 4, "id": ID, "resultado": "aceptada", "codigo": "aceptada"}


def test_replay_no_vuelve_a_iniciar() -> None:
    dobles = Dobles()
    assert ejecutar(peticion(), dobles).codigo == "aceptada"
    respuesta = ejecutar(peticion(), dobles)
    assert respuesta.codigo == "repetida"
    assert [x for x in dobles.llamadas if x[0] == "iniciar"] == [("iniciar", UNIDAD)]


def test_cerrojo_ocupado_no_consume_ni_inicia() -> None:
    dobles = Dobles(cerrojo=True)
    respuesta = ejecutar(peticion(), dobles)
    assert respuesta.codigo == "operacion_en_curso"
    assert dobles.llamadas == [("cerrojo", "")]


@pytest.mark.parametrize("linea", [b"", b"x\n", peticion() + b"\n", peticion()[:-1] + b"\r\n"])
def test_esquema_invalido_no_consume(linea) -> None:
    dobles = Dobles()
    respuesta = ejecutar(linea, dobles)
    assert respuesta.codigo == "esquema_invalido"
    assert dobles.llamadas == []


def test_firma_incorrecta_no_consume_ni_inicia() -> None:
    dobles = Dobles()
    objeto = protocolo.parsear(peticion())
    assert objeto is not None
    objeto["firma"] = "0" * 64
    linea = json.dumps(objeto, separators=(",", ":")).encode() + b"\n"
    respuesta = procesar(
        linea, clave=CLAVE, ahora=AHORA, reclamar_uso=dobles.reclamar,
        iniciar=dobles.iniciar, cerrojo_ocupado=dobles.ocupado,
        escribir=dobles.escribir, transicionar=dobles.transicionar,
    )
    assert respuesta.codigo == "firma_invalida"
    assert dobles.llamadas == []


@pytest.mark.parametrize("linea,ahora,esperado", [
    (peticion(ahora=AHORA - 121), AHORA, "caducada"),
    (
        peticion(token=crear_autorizacion(
            clave=CLAVE, id_=ID, ahora=AHORA - 100, ttl=10,
        )),
        AHORA, "caducada",
    ),
])
def test_caducidad_y_ligadura_no_inician(linea, ahora, esperado) -> None:
    dobles = Dobles()
    respuesta = procesar(
        linea, clave=CLAVE, ahora=ahora, reclamar_uso=dobles.reclamar,
        iniciar=dobles.iniciar, cerrojo_ocupado=dobles.ocupado,
        escribir=dobles.escribir, transicionar=dobles.transicionar,
    )
    assert respuesta.codigo == esperado
    assert [x for x in dobles.llamadas if x[0] == "iniciar"] == []


def test_id_de_testigo_ajeno_no_consume() -> None:
    dobles = Dobles()
    linea = peticion(token=crear_autorizacion(clave=CLAVE, id_="b" * 32, ahora=AHORA))
    respuesta = ejecutar(linea, dobles)
    assert respuesta.codigo == "autorizacion_invalida"
    assert [x for x in dobles.llamadas if x[0] == "reclamar"] == []


def test_fallo_de_inicio_no_se_presenta_como_exito() -> None:
    dobles = Dobles(inicio=False)
    respuesta = ejecutar(peticion(), dobles)
    assert respuesta.codigo == "incierta"
    assert [x for x in dobles.llamadas if x[0] == "iniciar"] == [("iniciar", UNIDAD)]


def test_clave_invalida_no_consume() -> None:
    dobles = Dobles()
    respuesta = procesar(
        peticion(), clave=b"x" * 31, ahora=AHORA, reclamar_uso=dobles.reclamar,
        iniciar=dobles.iniciar, cerrojo_ocupado=dobles.ocupado,
        escribir=dobles.escribir, transicionar=dobles.transicionar,
    )
    assert respuesta.codigo == "no_disponible"
    assert dobles.llamadas == []


# ── T-17: el auxiliar no escribe nada después del start ─────────────────────


def test_escribe_aceptada_antes_de_iniciar_y_nada_despues() -> None:
    dobles = Dobles()
    respuesta = ejecutar(peticion(), dobles)
    assert respuesta.codigo == "aceptada"
    assert [e["estado"] for e in dobles.estados] == ["aceptada"]
    assert all(e["id"] == ID for e in dobles.estados)
    posicion_escritura = dobles.llamadas.index(("escribir", "aceptada"))
    posicion_inicio = dobles.llamadas.index(("iniciar", UNIDAD))
    assert posicion_escritura < posicion_inicio


def test_si_no_puede_escribir_estado_no_inicia() -> None:
    dobles = Dobles(escribir=ResultadoEscritura.INCIERTO)
    respuesta = ejecutar(peticion(), dobles)
    assert respuesta.codigo == "no_disponible"
    assert [x for x in dobles.llamadas if x[0] == "iniciar"] == []


def test_auxiliar_rechaza_grupo_directorio_distinto_a_gid_efectivo(monkeypatch) -> None:
    monkeypatch.setattr(auxiliar, "propietario_servicio", lambda _ruta: (0, 12345))
    monkeypatch.setattr(auxiliar.os, "geteuid", lambda: 0)
    monkeypatch.setattr(auxiliar.os, "getegid", lambda: 12346)
    with pytest.raises(ValueError):
        auxiliar._propietario_auxiliar("/ruta/no/usada")


def test_auxiliar_acepta_propietario_y_gid_coincidentes(monkeypatch) -> None:
    monkeypatch.setattr(auxiliar, "propietario_servicio", lambda _ruta: (0, 12345))
    monkeypatch.setattr(auxiliar.os, "geteuid", lambda: 0)
    monkeypatch.setattr(auxiliar.os, "getegid", lambda: 12345)
    assert auxiliar._propietario_auxiliar("/ruta/no/usada") == (0, 12345)


def test_fchown_eperm_rechaza_sin_iniciar_unidad(tmp_path, monkeypatch) -> None:
    dobles = Dobles()
    ruta = tmp_path / "estado.json"

    def denegar(_fd: int, _uid: int, _gid: int) -> None:
        raise PermissionError("EPERM simulado")

    monkeypatch.setattr(os, "fchown", denegar)
    respuesta = procesar(
        peticion(), clave=CLAVE, ahora=AHORA, reclamar_uso=dobles.reclamar,
        iniciar=dobles.iniciar, cerrojo_ocupado=dobles.ocupado,
        escribir=lambda datos: escribir_estado(ruta, datos, propietario=(0, 12345)),
    )
    assert respuesta.codigo == "no_disponible"
    assert ID not in dobles.usados
    assert ID in dobles.intentos
    assert not any(llamada[0] == "iniciar" for llamada in dobles.llamadas)
    assert not ruta.exists()
    assert not list(tmp_path.glob(".estado.json.tmp-*"))


def test_inicio_no_confirmado_conserva_reserva() -> None:
    dobles = Dobles(inicio=False)
    respuesta = ejecutar(peticion(), dobles)
    assert respuesta.codigo == "incierta"
    assert [e["estado"] for e in dobles.estados] == ["aceptada"]
    assert not any(llamada[0] == "transicionar" for llamada in dobles.llamadas)


def _ruta_estado(tmp_path):
    return tmp_path / "actualizar-status.json"


def _callbacks_reales(ruta):
    def escribir(datos: dict):
        return escribir_estado(ruta, datos)

    def transicionar(estado: str, *, ahora: int, id_: str,
                     inicio_epoch: int, fase: str, codigo: str):
        return publicar_transicion(
            ruta, estado, ahora=ahora, id_=id_, inicio_epoch=inicio_epoch,
            fase=fase, codigo=codigo,
        )

    return escribir, transicionar


def test_terminal_escrito_por_el_finalizador_no_se_pisa_tras_start_exitoso(tmp_path) -> None:
    ruta = _ruta_estado(tmp_path)
    escribir, transicionar = _callbacks_reales(ruta)
    estado_final = {}

    def iniciar(unidad: str) -> bool:
        # El finalizador cierra la unidad (terminal) antes de que el auxiliar vuelva.
        actual = json.loads(ruta.read_text(encoding="utf-8"))
        assert publicar_transicion(
            ruta, "hecha", ahora=actual["actualizado_epoch"] + 1,
            id_=actual["id"], inicio_epoch=actual["inicio_epoch"],
            fase="fin", codigo="success:exited:0",
        ) is ResultadoEscritura.OK
        estado_final["leido"] = "hecha"
        return True

    respuesta = procesar(
        peticion(), clave=CLAVE, ahora=AHORA, reclamar_uso=lambda _id: True,
        iniciar=iniciar, cerrojo_ocupado=lambda: False,
        escribir=escribir, transicionar=transicionar,
    )
    assert respuesta.codigo == "aceptada"
    assert json.loads(ruta.read_text(encoding="utf-8"))["estado"] == "hecha"


def test_terminal_escrito_por_el_finalizador_no_se_pisa_si_falla_el_start(tmp_path) -> None:
    ruta = _ruta_estado(tmp_path)
    escribir, transicionar = _callbacks_reales(ruta)

    def iniciar(unidad: str) -> bool:
        # Carrera T-17: el finalizador dejó terminal antes de que el auxiliar anote fallida.
        actual = json.loads(ruta.read_text(encoding="utf-8"))
        assert publicar_transicion(
            ruta, "hecha", ahora=actual["actualizado_epoch"] + 1,
            id_=actual["id"], inicio_epoch=actual["inicio_epoch"],
            fase="fin", codigo="success:exited:0",
        ) is ResultadoEscritura.OK
        return False

    respuesta = procesar(
        peticion(), clave=CLAVE, ahora=AHORA, reclamar_uso=lambda _id: True,
        iniciar=iniciar, cerrojo_ocupado=lambda: False,
        escribir=escribir, transicionar=transicionar,
    )
    assert respuesta.codigo == "incierta"
    assert json.loads(ruta.read_text(encoding="utf-8"))["estado"] == "hecha"
