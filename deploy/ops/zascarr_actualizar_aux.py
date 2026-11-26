#!/usr/bin/env python3
"""Auxiliar privilegiado y separado de la actualización OPS4; no instalado.

Socket-activado por `zascarr-actualizar.socket`, lee una línea v4, verifica
firma, frescura, testigo y consumo durable, comprueba el cerrojo y ordena
iniciar la unidad fija `zascarr-actualizar.service`. No recibe rama, rutas ni
shell; no registra el testigo ni la contraseña. No se instala ni se habilita en
producción desde este cambio.

La instantánea del intento es la v2 del contrato B1 (`estado_inicial`), se
publica con `escribir_estado` bajo el cerrojo del directorio y, si esa
escritura no confirma, no se inicia la unidad. Tras el start no se escribe
`en_curso`: el finalizador cierra el intento, y un fallo del start se marca con
`publicar_transicion` (fase `fin`, código cerrado), que no pisa un terminal.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import stat
import subprocess
import sys
import time

try:  # importado como paquete (pruebas): una sola identidad de módulo
    from .admision_ops4 import liberar_admision, tomar_admision  # noqa: E402
    from .escritor_estado_actualizar_ops4 import (  # noqa: E402
        CODIGO_OTRO,
        ESTADOS_TERMINALES,
        FASES,
        UNIDAD,
        ResultadoEscritura,
        ResultadoLectura,
        escribir_estado,
        estado_inicial,
        leer_estado_estricto,
        propietario_servicio,
        publicar_transicion,
    )
    from .protocolo_actualizar_v4_ops4 import (  # noqa: E402
        decodificar_autorizacion,
        parsear,
        verificar_firma,
    )
    from .registro_repeticiones_ops4 import (  # noqa: E402
        abrir_directorio_autorizaciones,
        abrir_directorio_intentos,
        crear_reclamador_durable,
        reclamar_intento,
    )
    from .verificador_autorizacion_ops4 import (  # noqa: E402
        CodigoAutorizacion,
        verificar_autorizacion,
        verificar_testigo_sin_consumo,
    )
except ImportError:  # instalado como script suelto en /usr/local/lib/zascarr
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
    from admision_ops4 import liberar_admision, tomar_admision  # noqa: E402
    from escritor_estado_actualizar_ops4 import (  # noqa: E402
        CODIGO_OTRO,
        ESTADOS_TERMINALES,
        FASES,
        UNIDAD,
        ResultadoEscritura,
        ResultadoLectura,
        escribir_estado,
        estado_inicial,
        leer_estado_estricto,
        propietario_servicio,
        publicar_transicion,
    )
    from protocolo_actualizar_v4_ops4 import (  # noqa: E402
        decodificar_autorizacion,
        parsear,
        verificar_firma,
    )
    from registro_repeticiones_ops4 import (  # noqa: E402
        abrir_directorio_autorizaciones,
        abrir_directorio_intentos,
        crear_reclamador_durable,
        reclamar_intento,
    )
    from verificador_autorizacion_ops4 import (  # noqa: E402
        CodigoAutorizacion,
        verificar_autorizacion,
        verificar_testigo_sin_consumo,
    )

RUTA_CERROJO = "/run/zascarr-ops.lock"
PATH_FIJO = "/usr/sbin:/usr/bin:/sbin:/bin"
TIEMPO_SYSTEMCTL_S = 5
TOLERANCIA_S = 120
MAX_LINEA = 4096


class Respuesta:
    def __init__(self, resultado: str, codigo: str, id_: str | None = None) -> None:
        self.resultado = resultado
        self.codigo = codigo
        self.id = id_

    def linea(self) -> bytes:
        return json.dumps(
            {"v": 4, "id": self.id, "resultado": self.resultado, "codigo": self.codigo},
            separators=(",", ":"),
        ).encode("ascii") + b"\n"


def rechazo(codigo: str, id_: str | None = None) -> Respuesta:
    return Respuesta("rechazada", codigo, id_)


def procesar(
    linea: bytes, *, clave: bytes, ahora: int,
    reclamar_uso, iniciar, cerrojo_ocupado, escribir=None, transicionar=None,
    admitir=None, liberar=None, leer_estado=None, crear_intento=None,
    borrar_intento=None, reclamar_consumo=None, esperar=None,
) -> Respuesta:
    """Admite una petición; con `admitir` usa el flujo B2, sin él el legado.

    El flujo B2 (P3–P12) toma el cerrojo de admisión, comprueba el de
    operaciones, lee el estado, verifica el testigo **sin consumir**, crea la
    marca de intento, escribe la reserva, arranca, espera la confirmación del
    trabajador y solo entonces consume. El flujo legado se conserva para las
    pruebas y llamadores antiguos; el auxiliar usa siempre B2.
    """
    if admitir is not None:
        return _procesar_b2(
            linea, clave=clave, ahora=ahora, iniciar=iniciar,
            cerrojo_ocupado=cerrojo_ocupado, escribir=escribir,
            transicionar=transicionar, admitir=admitir, liberar=liberar,
            leer_estado=leer_estado, crear_intento=crear_intento,
            borrar_intento=borrar_intento, reclamar_consumo=reclamar_consumo,
            esperar=esperar,
        )
    if type(clave) is not bytes or len(clave) != 32:
        return rechazo("no_disponible")
    if type(ahora) is not int or not 0 <= ahora < 2**63:
        return rechazo("no_disponible")
    objeto = parsear(linea)
    if objeto is None:
        return rechazo("esquema_invalido")
    id_ = objeto["id"]
    if not verificar_firma(clave, objeto):
        return rechazo("firma_invalida", id_)
    if abs(objeto["creada"] - ahora) > TOLERANCIA_S:
        return rechazo("caducada", id_)
    try:
        if cerrojo_ocupado():
            return rechazo("operacion_en_curso", id_)
    except Exception:  # noqa: BLE001
        return rechazo("no_disponible", id_)
    testigo = decodificar_autorizacion(objeto["autorizacion"])
    if testigo is None:
        return rechazo("autorizacion_invalida", id_)
    resultado = verificar_autorizacion(
        testigo, clave=clave, ahora=ahora, reclamar_uso=reclamar_uso, id_esperado=id_,
    )
    if resultado is CodigoAutorizacion.CADUCADA:
        return rechazo("caducada", id_)
    if resultado is CodigoAutorizacion.REPETIDA:
        return rechazo("repetida", id_)
    if resultado is CodigoAutorizacion.NO_DISPONIBLE:
        return rechazo("no_disponible", id_)
    if resultado is not CodigoAutorizacion.ACEPTADA:
        return rechazo("autorizacion_invalida", id_)
    try:
        inicial = estado_inicial(id_, ahora)
    except ValueError:
        return rechazo("no_disponible", id_)
    if escribir is not None and escribir(inicial) != ResultadoEscritura.OK:
        return rechazo("no_disponible", id_)
    try:
        iniciada = iniciar(UNIDAD)
    except Exception:  # noqa: BLE001
        return rechazo("no_disponible", id_)
    if iniciada is not True:
        if transicionar is not None:
            marca = transicionar(
                "fallida",
                ahora=ahora,
                id_=id_,
                inicio_epoch=inicial["inicio_epoch"],
                fase=FASES[-1],
                codigo=CODIGO_OTRO,
            )
            if marca is ResultadoEscritura.INCIERTO:
                # La publicación durable no se pudo confirmar: no se anuncia
                # aceptación ni se deja un estado parcial.
                return rechazo("no_disponible", id_)
        return rechazo("no_disponible", id_)
    # T-17: no se escribe `en_curso` después del start. El finalizador cierra;
    # una instantánea posterior podría pisar un terminal si la unidad acaba antes.
    return Respuesta("aceptada", "aceptada", id_)


def _marcar_incierta(transicionar, id_: str, inicio: int, ahora: int) -> None:
    if transicionar is None:
        return
    with contextlib.suppress(Exception):
        transicionar(
            "incierta", ahora=ahora, id_=id_, inicio_epoch=inicio,
            fase=FASES[-1], codigo=CODIGO_OTRO,
        )


def _procesar_b2(
    linea: bytes, *, clave: bytes, ahora: int, iniciar, cerrojo_ocupado,
    escribir, transicionar, admitir, liberar, leer_estado, crear_intento,
    borrar_intento, reclamar_consumo, esperar,
) -> Respuesta:
    """Flujo P3–P12 de B2: admisión, reserva, arranque y consumo confirmado."""
    if type(clave) is not bytes or len(clave) != 32:
        return rechazo("no_disponible")
    if type(ahora) is not int or not 0 <= ahora < 2**63:
        return rechazo("no_disponible")
    try:
        admision = admitir()
    except Exception:  # noqa: BLE001
        return rechazo("no_disponible")
    if admision is None:
        return rechazo("operacion_en_curso")
    try:
        objeto = parsear(linea)
        if objeto is None:
            return rechazo("esquema_invalido")
        id_ = objeto["id"]
        if not verificar_firma(clave, objeto):
            return rechazo("firma_invalida", id_)
        if abs(objeto["creada"] - ahora) > TOLERANCIA_S:
            return rechazo("caducada", id_)
        try:
            if cerrojo_ocupado():
                return rechazo("operacion_en_curso", id_)
        except Exception:  # noqa: BLE001
            return rechazo("no_disponible", id_)
        try:
            datos = leer_estado()
        except Exception:  # noqa: BLE001
            return rechazo("no_disponible", id_)
        if datos is not None:
            if not isinstance(datos, dict) or datos.get("estado") not in (
                ESTADOS_TERMINALES | {"aceptada", "en_curso"}
            ):
                return rechazo("no_disponible", id_)
            if datos.get("id") == id_:
                return rechazo("repetida", id_)
            if datos.get("estado") not in ESTADOS_TERMINALES:
                return rechazo("operacion_en_curso", id_)
        testigo = decodificar_autorizacion(objeto["autorizacion"])
        if testigo is None:
            return rechazo("autorizacion_invalida", id_)
        verificado = verificar_testigo_sin_consumo(
            testigo, clave=clave, ahora=ahora, id_esperado=id_,
        )
        if verificado is CodigoAutorizacion.CADUCADA:
            return rechazo("caducada", id_)
        if verificado is CodigoAutorizacion.NO_DISPONIBLE:
            return rechazo("no_disponible", id_)
        if verificado is not CodigoAutorizacion.ACEPTADA:
            return rechazo("autorizacion_invalida", id_)
        try:
            intento = crear_intento(id_)
        except Exception:  # noqa: BLE001
            return rechazo("no_disponible", id_)
        if intento is not True:
            return rechazo("repetida", id_)
        try:
            inicial = estado_inicial(id_, ahora)
        except ValueError:
            return rechazo("no_disponible", id_)
        if escribir(inicial) != ResultadoEscritura.OK:
            if borrar_intento is not None:
                with contextlib.suppress(Exception):
                    borrar_intento(id_)
            return rechazo("no_disponible", id_)
        try:
            iniciada = iniciar(UNIDAD)
        except Exception:  # noqa: BLE001
            iniciada = False
        if iniciada is not True:
            if transicionar is not None:
                with contextlib.suppress(Exception):
                    transicionar(
                        "fallida", ahora=ahora, id_=id_,
                        inicio_epoch=inicial["inicio_epoch"],
                        fase=FASES[-1], codigo=CODIGO_OTRO,
                    )
            return rechazo("no_disponible", id_)
        try:
            confirmada = esperar(id_) is True
        except Exception:  # noqa: BLE001
            confirmada = False
        if confirmada:
            try:
                consumida = (
                    reclamar_consumo(id_) if reclamar_consumo is not None else False
                )
            except Exception:  # noqa: BLE001
                consumida = False
            if consumida is True:
                return Respuesta("aceptada", "aceptada", id_)
            _marcar_incierta(transicionar, id_, inicial["inicio_epoch"], ahora)
            return Respuesta("incierta", "incierta", id_)
        _marcar_incierta(transicionar, id_, inicial["inicio_epoch"], ahora)
        if reclamar_consumo is not None:
            with contextlib.suppress(Exception):
                reclamar_consumo(id_)
        return Respuesta("incierta", "incierta", id_)
    finally:
        if liberar is not None:
            with contextlib.suppress(Exception):
                liberar(admision)


def _leer_clave(ruta: str) -> bytes | None:
    try:
        fd = os.open(ruta, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        return None
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) != 0o440
            or info.st_size not in (64, 65)
        ):
            return None
        datos = os.read(fd, 66)
    except OSError:
        return None
    finally:
        os.close(fd)
    if len(datos) == 65 and datos.endswith(b"\n"):
        datos = datos[:-1]
    if len(datos) != 64:
        return None
    try:
        clave = bytes.fromhex(datos.decode("ascii"))
    except (UnicodeDecodeError, ValueError):
        return None
    return clave if len(clave) == 32 else None


def _cerrojo_ocupado() -> bool:
    try:
        fd = os.open(RUTA_CERROJO, os.O_RDONLY)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def _iniciar(unidad: str) -> bool:
    try:
        resultado = subprocess.run(
            ["systemctl", "start", "--no-block", unidad],
            env={"PATH": PATH_FIJO}, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=TIEMPO_SYSTEMCTL_S, check=False, close_fds=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return resultado.returncode == 0


def _leer_linea() -> bytes:
    datos = b""
    while len(datos) <= MAX_LINEA:
        bloque = os.read(0, MAX_LINEA + 1 - len(datos))
        if not bloque:
            break
        datos += bloque
        if b"\n" in datos:
            break
    return datos


def _propietario_auxiliar(ruta_estado: str) -> tuple[int, int]:
    """Exige que el grupo efectivo coincida con el directorio de estado."""
    propietario = propietario_servicio(ruta_estado)
    if os.geteuid() != 0 or propietario is None or propietario != (0, os.getegid()):
        raise ValueError("El grupo del directorio de estado no coincide")
    return propietario


def main() -> int:
    dir_ops = os.environ.get("ZASCARR_OPS_DIR", "/var/lib/zascarr/ops")
    dir_ops4 = os.environ.get("ZASCARR_OPS4_DIR", "/var/lib/zascarr/ops4")
    ruta_estado = os.path.join(dir_ops, "actualizar-status.json")
    clave = _leer_clave(os.path.join(dir_ops, "actualizar.key"))
    linea = _leer_linea()
    fd_dir = None
    fd_intentos = None
    try:
        propietario = _propietario_auxiliar(ruta_estado)
        fd_ops4 = os.open(
            dir_ops4, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        try:
            info = os.fstat(fd_ops4)
            if (
                not stat.S_ISDIR(info.st_mode)
                or info.st_uid != 0
                or stat.S_IMODE(info.st_mode) != 0o700
            ):
                raise ValueError("El directorio ops4 no es seguro")
        finally:
            os.close(fd_ops4)
        ruta_admision = os.path.join(dir_ops4, "admision.lock")
        fd_dir = abrir_directorio_autorizaciones(
            os.path.join(dir_ops4, "consumidos"), uid_esperado=0, modo_esperado=0o700,
        )
        fd_intentos = abrir_directorio_intentos(
            os.path.join(dir_ops4, "intentos"), uid_esperado=0, modo_esperado=0o700,
        )
        reclamar = crear_reclamador_durable(fd_dir)

        def transicionar(
            estado: str, *, ahora: int, id_: str, inicio_epoch: int,
            fase: str, codigo: str,
        ) -> ResultadoEscritura:
            """Publica una transición del mismo intento bajo el cerrojo B1."""
            return publicar_transicion(
                ruta_estado, estado, ahora=ahora, id_=id_,
                inicio_epoch=inicio_epoch, fase=fase, codigo=codigo,
                propietario=propietario,
            )

        def leer_estado():
            lectura, datos = leer_estado_estricto(ruta_estado)
            if lectura is ResultadoLectura.AUSENTE:
                return None
            if lectura is not ResultadoLectura.OK or datos is None:
                raise ValueError("Estado no legible")
            return datos

        def esperar(id_: str) -> bool:
            limite = time.monotonic() + 5
            while time.monotonic() < limite:
                try:
                    lectura, datos = leer_estado_estricto(ruta_estado)
                except Exception:  # noqa: BLE001
                    return False
                if (
                    lectura is ResultadoLectura.OK
                    and isinstance(datos, dict)
                    and datos.get("id") == id_
                    and (
                        datos.get("estado") in ESTADOS_TERMINALES
                        or datos.get("estado") == "en_curso"
                    )
                ):
                    return True
                time.sleep(0.1)
            return False

        def crear_intento(id_: str) -> bool:
            return reclamar_intento(id_, directorio_fd=fd_intentos)

        def borrar_intento(id_: str) -> None:
            if (
                isinstance(id_, str) and len(id_) == 32
                and all(c in "0123456789abcdef" for c in id_)
            ):
                with contextlib.suppress(OSError):
                    os.unlink(os.path.join(dir_ops4, "intentos", id_))

        respuesta = procesar(
            linea, clave=clave or b"", ahora=int(time.time()),
            reclamar_uso=reclamar, iniciar=_iniciar, cerrojo_ocupado=_cerrojo_ocupado,
            escribir=lambda datos: escribir_estado(
                ruta_estado, datos, propietario=propietario,
            ),
            transicionar=transicionar,
            admitir=lambda: tomar_admision(ruta_admision),
            liberar=liberar_admision,
            leer_estado=leer_estado,
            crear_intento=crear_intento,
            borrar_intento=borrar_intento,
            reclamar_consumo=reclamar,
            esperar=esperar,
        )
    except Exception:  # noqa: BLE001 — nunca se devuelve un éxito dudoso
        respuesta = rechazo("no_disponible")
    finally:
        if fd_dir is not None:
            with contextlib.suppress(OSError):
                os.close(fd_dir)
        if fd_intentos is not None:
            with contextlib.suppress(OSError):
                os.close(fd_intentos)
    with contextlib.suppress(OSError):
        os.write(1, respuesta.linea())
    return 0


if __name__ == "__main__":
    sys.exit(main())
