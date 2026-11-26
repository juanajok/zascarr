#!/usr/bin/env python3
"""Oráculo determinista del contrato B1 (estado v2) para el pipeline.

Uso: python3 docs/design/ops4-b1-check.py <contrato|monotonia|reconciliacion>

Solo stdlib. No red. Escribe sus ficheros de estado en /dev/shm (el contenedor
de verificación es de raíz de solo lectura). Salida: 0 pasa; 42 falla la
aserción que este control representa; 1 error de preparación. El código 42 se
reserva para la aserción del contrato: un fallo genérico no acredita RED.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import traceback

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for sub in (os.path.join(BASE, "deploy", "ops"), os.path.join(BASE, "src", "zascarr", "services")):
    if sub not in sys.path:
        sys.path.insert(0, sub)

UNIDAD = "zascarr-actualizar.service"
ID = "0123456789abcdef0123456789abcdef"
OTRO_ID = "fedcba9876543210fedcba9876543210"
SHA_A = "a" * 40
SHA_B = "b" * 40
AHORA = 1_700_000_000
SIN_NOTICIAS = 7200

CAMPOS_V2 = {
    "schema", "id", "unidad", "estado", "fase", "inicio_epoch", "actualizado_epoch",
    "head0", "sha_destino", "sha_actual", "resultado", "codigo",
}
CAMPOS_V1 = {"schema", "id", "estado", "inicio_epoch", "actualizado_epoch"}


def exige(cond: object, mensaje: str) -> None:
    if not cond:
        raise AssertionError(mensaje)


def inicial(estado: str = "aceptada", fase: str = "aceptada") -> dict[str, object]:
    return {
        "schema": 2, "id": ID, "unidad": UNIDAD, "estado": estado, "fase": fase,
        "inicio_epoch": AHORA, "actualizado_epoch": AHORA,
        "head0": None, "sha_destino": None, "sha_actual": None,
        "resultado": None, "codigo": None,
    }


def bruto(ruta: str, datos: dict[str, object]) -> None:
    with open(ruta, "wb") as salida:
        salida.write(json.dumps(datos, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    os.chmod(ruta, 0o640)


def instantanea(w, ruta: str) -> dict[str, object]:
    lectura, datos = w.leer_estado_estricto(ruta)
    exige(lectura == w.ResultadoLectura.OK, "el lector estricto no acepta el estado publicado")
    exige(isinstance(datos, dict), "el lector estricto no devuelve objeto")
    return datos


def bytes_de(ruta: str) -> bytes:
    with open(ruta, "rb") as entrada:
        return entrada.read()


def check_contrato(w, f, l, tools) -> None:
    ruta = tools("estado.json")
    ini = w.estado_inicial(ID, AHORA)
    exige(set(ini) == CAMPOS_V2, "estado_inicial no tiene las 12 claves del esquema 2")
    exige(ini == inicial(), "estado_inicial no coincide con la instantánea inicial del contrato")
    exige(w.escribir_estado(ruta, ini) == w.ResultadoEscritura.OK, "no publica la instantánea v2")
    exige(instantanea(w, ruta) == ini, "el round-trip v2 no devuelve lo publicado")
    texto = bytes_de(ruta)
    exige(texto.endswith(b"\n") and b" " not in texto, "el estado no se publica canónico con LF")

    it = l.leer_ultimo_intento(ruta, ahora_epoch=AHORA + 1)
    exige(it is not None, "el lector de la app no devuelve el último intento")
    exige(it.estado == l.EstadoActualizacion.ACEPTADA, "estado inicial distinto de aceptada")
    exige(it.fase == "aceptada", "fase inicial distinta de aceptada")
    exige((it.inicio_epoch, it.actualizado_epoch) == (AHORA, AHORA), "épocas iniciales alteradas")
    exige(it.head0 is None and it.sha_destino is None and it.sha_actual is None, "hashes inventados")
    exige(it.resultado is None and it.codigo is None, "resultado inventado en no terminal")
    exige(it.sin_noticias is False, "aceptada fresca marcada sin noticias")
    exige(
        l.leer_estado_actualizacion(ruta, id_esperado=ID, ahora_epoch=AHORA + 1)
        == l.EstadoActualizacion.ACEPTADA,
        "el lector correlacionado no acepta v2",
    )
    exige(
        l.leer_estado_actualizacion(ruta, id_esperado=OTRO_ID, ahora_epoch=AHORA + 1)
        == l.EstadoActualizacion.INCIERTA,
        "un id ajeno no falla cerrado",
    )

    v1 = {"schema": 1, "id": ID, "estado": "aceptada",
          "inicio_epoch": AHORA, "actualizado_epoch": AHORA}
    ruta_v1 = tools("v1.json")
    exige(w.escribir_estado(ruta_v1, v1) == w.ResultadoEscritura.OK, "no publica el esquema 1")
    exige(instantanea(w, ruta_v1) == v1, "el round-trip v1 cambió el objeto")
    antiguo = l.leer_ultimo_intento(ruta_v1, ahora_epoch=AHORA + 1)
    exige(antiguo is not None and antiguo.fase == "aceptada", "v1 no se lee como aceptada")
    exige(antiguo.head0 is None and antiguo.resultado is None, "v1 inventa campos v2")

    exige(
        w.publicar_transicion(
            ruta, "en_curso", ahora=AHORA + 10, fase="copia",
            head0=SHA_A, sha_destino=SHA_B,
        ) == w.ResultadoEscritura.OK,
        "no publica la transición a en_curso con hashes",
    )
    datos = instantanea(w, ruta)
    exige(
        (datos["estado"], datos["fase"], datos["head0"], datos["sha_destino"])
        == ("en_curso", "copia", SHA_A, SHA_B),
        "la transición no conserva los campos del contrato",
    )
    exige(datos["actualizado_epoch"] == AHORA + 10, "la transición no actualiza la época")
    exige(datos["id"] == ID and datos["inicio_epoch"] == AHORA, "la transición cambia id/inicio")
    exige(datos["resultado"] is None and datos["codigo"] is None, "resultado en no terminal")

    exige(f.main(["--ruta", ruta, "--fase", "git"]) == 0, "el CLI no publica una fase intermedia")
    datos = instantanea(w, ruta)
    exige((datos["fase"], datos["estado"]) == ("git", "en_curso"), "la fase intermedia no avanza")
    exige(datos["head0"] == SHA_A, "la fase intermedia pierde head0")

    exige(
        f.main(["--ruta", ruta, "--resultado", "hecha", "--codigo", "success:exited:0"]) == 0,
        "el CLI no cierra el intento",
    )
    datos = instantanea(w, ruta)
    exige(
        (datos["estado"], datos["fase"], datos["resultado"], datos["codigo"])
        == ("hecha", "fin", "hecha", "success:exited:0"),
        "el cierre no escribe estado/resultado/código del contrato",
    )
    exige(
        l.leer_ultimo_intento(ruta, ahora_epoch=datos["actualizado_epoch"] + 1).estado
        == l.EstadoActualizacion.HECHA,
        "el lector de la app no ve el terminal",
    )

    ausente = tools("ausente.json")
    exige(f.main(["--ruta", ausente, "--resultado", "hecha"]) == 0, "sin estado debe devolver 0")
    exige(not os.path.exists(ausente), "el CLI inventó un estado")
    exige(f.main(["--ruta", ruta, "--resultado", "inventado"]) == 2, "resultado abierto no es 2")
    exige(f.main(["--ruta", ruta, "--fase", "preparacion", "--head0", "corta"]) == 2, "SHA corto no es 2")


def check_monotonia(w, f, l, tools) -> None:
    ruta = tools("mono.json")
    exige(w.escribir_estado(ruta, w.estado_inicial(ID, AHORA)) == w.ResultadoEscritura.OK, "siembra")
    exige(
        w.publicar_transicion(ruta, "en_curso", ahora=AHORA + 10, fase="copia",
                              head0=SHA_A, sha_destino=SHA_B) == w.ResultadoEscritura.OK,
        "siembra de transición",
    )
    antes = bytes_de(ruta)
    exige(
        w.publicar_transicion(ruta, "en_curso", ahora=AHORA + 11, fase="preparacion")
        == w.ResultadoEscritura.INVALIDO,
        "la fase no puede retroceder",
    )
    exige(bytes_de(ruta) == antes, "un rechazo de fase reescribió el estado")
    exige(
        w.publicar_transicion(ruta, "en_curso", ahora=AHORA + 11, fase="git", head0=SHA_B)
        == w.ResultadoEscritura.INVALIDO,
        "head0 no puede cambiar una vez fijado",
    )
    exige(
        w.publicar_transicion(ruta, "en_curso", ahora=AHORA + 5, fase="git")
        == w.ResultadoEscritura.INVALIDO,
        "el reloj no puede retroceder",
    )
    exige(
        w.publicar_transicion(ruta, "en_curso", ahora=AHORA + 11, fase="git", id_=OTRO_ID)
        == w.ResultadoEscritura.INVALIDO,
        "un id ajeno no puede transicionar",
    )
    exige(bytes_de(ruta) == antes, "un rechazo de monotonía reescribió el estado")
    exige(
        w.publicar_transicion(ruta, "incierta", ahora=AHORA + 20, fase="fin", codigo="otro")
        == w.ResultadoEscritura.OK,
        "no publica un terminal incierto",
    )
    cerrado = bytes_de(ruta)
    exige(
        w.publicar_transicion(ruta, "hecha", ahora=AHORA + 30, fase="fin") == w.ResultadoEscritura.INVALIDO,
        "un terminal no se pisa",
    )
    exige(bytes_de(ruta) == cerrado, "el rechazo del terminal reescribió el estado")
    datos = instantanea(w, ruta)
    exige((datos["resultado"], datos["codigo"]) == ("incierta", "otro"), "terminal sin resultado/código")
    exige(
        l.leer_ultimo_intento(ruta, ahora_epoch=AHORA + 40).estado == l.EstadoActualizacion.INCIERTA,
        "el lector no respeta el terminal incierto",
    )

    ruta_v1 = tools("mono-v1.json")
    v1 = {"schema": 1, "id": ID, "estado": "aceptada",
          "inicio_epoch": AHORA, "actualizado_epoch": AHORA}
    bruto(ruta_v1, v1)
    exige(
        w.publicar_transicion(ruta_v1, "en_curso", ahora=AHORA + 10, fase="preparacion")
        == w.ResultadoEscritura.OK,
        "un v1 válido debe poder transicionar a v2",
    )
    elevado = instantanea(w, ruta_v1)
    exige(
        set(elevado) == CAMPOS_V2 and elevado["id"] == ID and elevado["fase"] == "preparacion",
        "la elevación de v1 a v2 pierde identidad o fase",
    )

    malo = tools("malo.json")
    exige(
        w.escribir_estado(malo, {**inicial(), "extra": 1}) == w.ResultadoEscritura.INVALIDO,
        "una clave de más no es inválida",
    )
    exige(not os.path.exists(malo), "un estado inválido se publicó")
    exige(
        w.escribir_estado(malo, {**inicial(), "schema": 3}) == w.ResultadoEscritura.INVALIDO,
        "un esquema desconocido no es inválido",
    )
    exige(
        w.escribir_estado(malo, {**inicial(), "fase": "inventada"}) == w.ResultadoEscritura.INVALIDO,
        "una fase abierta no es inválida",
    )
    for args in ((ID, -1), ("no-hex", AHORA), (ID, "ahora")):
        try:
            w.estado_inicial(*args)
        except ValueError:
            pass
        else:
            raise AssertionError("estado_inicial acepta identidad o época inválidas")


def check_reconciliacion(w, f, l, tools) -> None:
    ruta = tools("recon.json")
    exige(w.escribir_estado(ruta, w.estado_inicial(ID, AHORA)) == w.ResultadoEscritura.OK, "siembra")
    fresco = l.leer_ultimo_intento(ruta, ahora_epoch=AHORA + SIN_NOTICIAS - 1)
    exige(fresco is not None and fresco.estado == l.EstadoActualizacion.ACEPTADA, "fresco mal leído")
    exige(fresco.sin_noticias is False, "fresco marcado sin noticias")
    viejo = l.leer_ultimo_intento(ruta, ahora_epoch=AHORA + SIN_NOTICIAS)
    exige(viejo is not None, "viejo desaparece en vez de reconciliarse")
    exige(viejo.estado == l.EstadoActualizacion.INCIERTA, "un activo sin noticias no es incierto")
    exige(viejo.sin_noticias is True, "sin_noticias no se marca")
    exige(viejo.estado != l.EstadoActualizacion.FALLIDA, "sin noticias no es un fallo")

    exige(
        w.publicar_transicion(ruta, "en_curso", ahora=AHORA + 10, fase="build") == w.ResultadoEscritura.OK,
        "transición",
    )
    exige(
        l.leer_ultimo_intento(ruta, ahora_epoch=AHORA + 10 + SIN_NOTICIAS).sin_noticias is True,
        "en_curso antiguo no se reconcilia",
    )
    exige(
        w.publicar_transicion(ruta, "hecha", ahora=AHORA + 20, fase="fin", codigo="success:exited:0")
        == w.ResultadoEscritura.OK,
        "terminal",
    )
    exige(
        l.leer_ultimo_intento(ruta, ahora_epoch=AHORA + 10_000_000).estado == l.EstadoActualizacion.HECHA,
        "un terminal antiguo deja de ser terminal",
    )
    exige(
        l.leer_ultimo_intento(ruta, ahora_epoch=AHORA + 10_000_000).sin_noticias is False,
        "un terminal no es sin noticias",
    )

    futuro = tools("futuro.json")
    datos = {**inicial(), "actualizado_epoch": AHORA + 100}
    bruto(futuro, datos)
    exige(l.leer_ultimo_intento(futuro, ahora_epoch=AHORA) is None, "una época futura no es inválida")
    exige(l.leer_ultimo_intento(tools("nada.json"), ahora_epoch=AHORA) is None, "ausente no es None")
    roto = tools("roto.json")
    with open(roto, "wb") as salida:
        salida.write(b"{no es json}\n")
    os.chmod(roto, 0o640)
    exige(l.leer_ultimo_intento(roto, ahora_epoch=AHORA) is None, "JSON roto no es None")
    sobra = tools("sobra.json")
    bruto(sobra, {**inicial(), "extra": 1})
    exige(l.leer_ultimo_intento(sobra, ahora_epoch=AHORA) is None, "clave de más no es None")
    enlace = tools("enlace.json")
    os.symlink(ruta, enlace)
    exige(l.leer_ultimo_intento(enlace, ahora_epoch=AHORA) is None, "un enlace no se sigue")
    exige(l.leer_ultimo_intento(ruta, ahora_epoch=-1) is None, "un reloj inválido no falla cerrado")

    exige(
        l.leer_estado_actualizacion(ruta, id_esperado=ID, ahora_epoch=AHORA + 30)
        == l.EstadoActualizacion.HECHA,
        "el lector correlacionado no acepta el v2 cerrado",
    )


CHECKS = {
    "contrato": check_contrato,
    "monotonia": check_monotonia,
    "reconciliacion": check_reconciliacion,
}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in CHECKS:
        print("uso: ops4-b1-check.py contrato|monotonia|reconciliacion", file=sys.stderr)
        return 1
    try:
        import escritor_estado_actualizar_ops4 as w
        import estado_actualizar_ops4 as f
        import estado_actualizacion as l
    except (ImportError, SyntaxError):
        traceback.print_exc()
        return 1
    raiz = tempfile.mkdtemp(prefix="b1-", dir="/dev/shm")
    contador = {"n": 0}

    def tools(nombre: str) -> str:
        contador["n"] += 1
        return os.path.join(raiz, f"{contador['n']}-{nombre}")

    try:
        CHECKS[argv[1]](w, f, l, tools)
    except AssertionError as exc:
        print(f"FALLO {argv[1]}: {exc}", file=sys.stderr)
        return 42
    except Exception:  # noqa: BLE001 — un fallo de comportamiento no es infraestructura
        traceback.print_exc()
        print(f"FALLO {argv[1]}: excepción de comportamiento", file=sys.stderr)
        return 42
    finally:
        shutil.rmtree(raiz, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
