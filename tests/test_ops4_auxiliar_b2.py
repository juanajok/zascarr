"""B2b: el auxiliar reserva, arranca y consume solo tras confirmar."""
from __future__ import annotations

import os

import pytest

from deploy.ops.escritor_estado_actualizar_ops4 import (
    UNIDAD,
    ResultadoEscritura,
)
from deploy.ops.zascarr_actualizar_aux import procesar
from zascarr.services.autorizacion_actualizacion import crear_autorizacion
from zascarr.services.ops_actualizacion_v4 import construir_peticion_v4

CLAVE = bytes(range(32))
ID = "a" * 32
AHORA = 1_800_000_000


def peticion(id_: str = ID) -> bytes:
    return construir_peticion_v4(
        CLAVE, id=id_, creada=AHORA,
        autorizacion=crear_autorizacion(clave=CLAVE, id_=id_, ahora=AHORA, ttl=60),
    )


class Dobles:
    def __init__(self, *, admision=True, cerrojo=False, intento=True,
                 escribir=ResultadoEscritura.OK, inicio=True,
                 confirmada="confirmada", consumo=True, estado=None,
                 existe=False) -> None:
        self.admision = admision
        self.cerrojo = cerrojo
        self.intento = intento
        self.escritura = escribir
        self.inicio = inicio
        self.confirmada = confirmada
        self.consumo = consumo
        self.estado = estado
        self.existe = existe
        self.llamadas: list[tuple[str, object]] = []

    def admitir(self):
        self.llamadas.append(("admitir", ""))
        return "adm" if self.admision else None

    def liberar(self, token) -> None:
        self.llamadas.append(("liberar", token))

    def leer_estado(self):
        self.llamadas.append(("leer", ""))
        return self.estado

    def existe_intento(self, id_: str) -> bool:
        self.llamadas.append(("existe_intento", id_))
        return self.existe

    def crear_intento(self, id_: str) -> bool:
        self.llamadas.append(("intento", id_))
        return self.intento

    def borrar_intento(self, id_: str) -> None:
        self.llamadas.append(("borrar_intento", id_))

    def escribir(self, datos: dict):
        self.llamadas.append(("escribir", datos["estado"]))
        return self.escritura

    def iniciar(self, unidad: str) -> bool:
        self.llamadas.append(("iniciar", unidad))
        return self.inicio

    def esperar(self, id_: str) -> str:
        self.llamadas.append(("esperar", id_))
        return self.confirmada

    def consumir(self, id_: str) -> bool:
        self.llamadas.append(("consumo", id_))
        return self.consumo

    def transicionar(self, estado: str, **_kwargs):
        self.llamadas.append(("transicionar", estado))
        return ResultadoEscritura.OK

    def ocupado(self) -> bool:
        self.llamadas.append(("cerrojo", ""))
        return self.cerrojo


def ejecutar(dobles: Dobles, *, token: bytes | None = None):
    return procesar(
        peticion() if token is None else token,
        clave=CLAVE, ahora=AHORA, reclamar_uso=lambda _id: True,
        iniciar=dobles.iniciar, cerrojo_ocupado=dobles.ocupado,
        escribir=dobles.escribir, transicionar=dobles.transicionar,
        admitir=dobles.admitir, liberar=dobles.liberar,
        leer_estado=dobles.leer_estado, crear_intento=dobles.crear_intento,
        borrar_intento=dobles.borrar_intento,
        reclamar_consumo=dobles.consumir, esperar=dobles.esperar,
        existe_intento=dobles.existe_intento,
    )


def _pos(dobles: Dobles, nombre: str) -> int:
    return next(i for i, (n, _) in enumerate(dobles.llamadas) if n == nombre)


def test_reserva_arranca_confirma_y_consume_en_orden() -> None:
    dobles = Dobles()
    respuesta = ejecutar(dobles)
    assert respuesta.codigo == "aceptada"
    assert _pos(dobles, "intento") < _pos(dobles, "escribir")
    assert _pos(dobles, "escribir") < _pos(dobles, "iniciar")
    assert _pos(dobles, "iniciar") < _pos(dobles, "esperar")
    assert _pos(dobles, "esperar") < _pos(dobles, "consumo")
    assert dobles.llamadas[-1] == ("liberar", "adm")


def test_admision_ocupada_no_toca_nada() -> None:
    dobles = Dobles(admision=False)
    respuesta = ejecutar(dobles)
    assert respuesta.codigo == "operacion_en_curso"
    assert respuesta.id == ID
    assert dobles.llamadas == [("admitir", "")]


def test_cerrojo_ocupado_no_reserva_ni_consume() -> None:
    dobles = Dobles(cerrojo=True)
    respuesta = ejecutar(dobles)
    assert respuesta.codigo == "operacion_en_curso"
    assert ("escribir", "aceptada") not in dobles.llamadas
    assert ("intento", ID) not in dobles.llamadas
    assert not any(n == "consumo" for n, _ in dobles.llamadas)
    assert dobles.llamadas[-1] == ("liberar", "adm")


def test_estado_activo_mismo_id_es_repetida() -> None:
    dobles = Dobles(estado={"id": ID, "estado": "en_curso"})
    respuesta = ejecutar(dobles)
    assert respuesta.codigo == "repetida"
    assert ("iniciar", UNIDAD) not in dobles.llamadas


def test_estado_activo_ajeno_es_ocupado() -> None:
    dobles = Dobles(estado={"id": "b" * 32, "estado": "en_curso"})
    respuesta = ejecutar(dobles)
    assert respuesta.codigo == "operacion_en_curso"
    assert ("iniciar", UNIDAD) not in dobles.llamadas


@pytest.mark.parametrize("estado", ["aceptada", "en_curso"])
def test_estado_activo_antiguo_no_se_sustituye(estado) -> None:
    dobles = Dobles(estado={
        "id": "b" * 32, "estado": estado,
        "actualizado_epoch": AHORA - 10000, "inicio_epoch": AHORA - 10000,
    })
    respuesta = ejecutar(dobles)
    assert respuesta.codigo == "operacion_en_curso"
    assert not any(n in {"transicionar", "escribir", "iniciar"} for n, _ in dobles.llamadas)


def test_reserva_aceptada_reciente_sigue_ocupada() -> None:
    dobles = Dobles(estado={
        "id": "b" * 32, "estado": "aceptada",
        "actualizado_epoch": AHORA - 1, "inicio_epoch": AHORA - 1,
    })
    respuesta = ejecutar(dobles)
    assert respuesta.codigo == "operacion_en_curso"
    assert ("iniciar", UNIDAD) not in dobles.llamadas


def test_intento_preexistente_se_rechaza_antes_de_verificar() -> None:
    dobles = Dobles(existe=True)
    respuesta = ejecutar(dobles)
    assert respuesta.codigo == "repetida"
    assert ("existe_intento", ID) in dobles.llamadas
    assert ("iniciar", UNIDAD) not in dobles.llamadas
    assert not any(n == "consumo" for n, _ in dobles.llamadas)


def test_intento_existente_no_arranca_ni_consume() -> None:
    dobles = Dobles(intento=False)
    respuesta = ejecutar(dobles)
    assert respuesta.codigo == "repetida"
    assert ("iniciar", UNIDAD) not in dobles.llamadas
    assert not any(n == "consumo" for n, _ in dobles.llamadas)


@pytest.mark.parametrize("resultado", [ResultadoEscritura.INCIERTO, ResultadoEscritura.INVALIDO])
def test_reserva_no_confirmada_conserva_intento_y_no_arranca(resultado) -> None:
    dobles = Dobles(escribir=resultado)
    respuesta = ejecutar(dobles)
    assert respuesta.codigo == "no_disponible"
    assert ("intento", ID) in dobles.llamadas
    assert ("iniciar", UNIDAD) not in dobles.llamadas
    assert ("borrar_intento", ID) not in dobles.llamadas
    assert not any(n == "consumo" for n, _ in dobles.llamadas)


def test_escritura_incierta_conserva_marca_real_y_bloquea_reintento(tmp_path) -> None:
    from deploy.ops.registro_repeticiones_ops4 import reclamar_intento

    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    dobles = Dobles(escribir=ResultadoEscritura.INCIERTO)
    dobles.crear_intento = lambda id_: reclamar_intento(id_, directorio_fd=fd)
    try:
        assert ejecutar(dobles).codigo == "no_disponible"
        assert (tmp_path / ID).is_file()
        # Simula que la lectura del estado no encuentra la reserva tras caída.
        assert ejecutar(dobles).codigo == "repetida"
        assert ("iniciar", UNIDAD) not in dobles.llamadas
    finally:
        os.close(fd)


@pytest.mark.parametrize("resultado", [False, RuntimeError(), TimeoutError()])
def test_inicio_no_confirmado_conserva_reserva_y_consume(resultado) -> None:
    dobles = Dobles(inicio=False)
    if isinstance(resultado, Exception):
        def iniciar(_unidad):
            raise resultado
        dobles.iniciar = iniciar
    respuesta = ejecutar(dobles)
    assert respuesta.codigo == "incierta"
    assert ("consumo", ID) in dobles.llamadas
    assert ("borrar_intento", ID) not in dobles.llamadas
    assert not any(n == "transicionar" for n, _ in dobles.llamadas)


@pytest.mark.parametrize("espera", ["sin", RuntimeError(), TimeoutError()])
def test_sin_confirmacion_responde_incierta_y_consume(espera) -> None:
    dobles = Dobles(confirmada="sin")
    if isinstance(espera, Exception):
        def esperar(_id):
            raise espera
        dobles.esperar = esperar
    respuesta = ejecutar(dobles)
    assert respuesta.codigo == "incierta"
    assert not any(n == "transicionar" for n, _ in dobles.llamadas)
    assert ("consumo", ID) in dobles.llamadas
    assert ("borrar_intento", ID) not in dobles.llamadas


def test_terminal_fallida_no_se_presenta_como_aceptada() -> None:
    dobles = Dobles(confirmada="fallida")
    respuesta = ejecutar(dobles)
    assert respuesta.codigo == "incierta"
    assert ("consumo", ID) in dobles.llamadas


def test_consumo_fallido_tras_confirmar_responde_incierta() -> None:
    dobles = Dobles(consumo=False)
    respuesta = ejecutar(dobles)
    assert respuesta.codigo == "incierta"
    assert not any(n == "transicionar" for n, _ in dobles.llamadas)


def test_caducada_no_reserva_ni_consume() -> None:
    caducada = construir_peticion_v4(
        CLAVE, id=ID, creada=AHORA - 121,
        autorizacion=crear_autorizacion(clave=CLAVE, id_=ID, ahora=AHORA - 121, ttl=60),
    )
    dobles2 = Dobles()
    respuesta2 = ejecutar(dobles2, token=caducada)
    assert respuesta2.codigo == "caducada"
    assert not any(n in {"escribir", "iniciar", "consumo"} for n, _ in dobles2.llamadas)
