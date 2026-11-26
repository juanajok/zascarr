#!/usr/bin/env python3
"""Oráculo determinista del contrato B1 (estado v2) para el pipeline.

Uso: python3 docs/design/ops4-b1-check.py <contrato|monotonia|reconciliacion>

Solo stdlib, sin red y **sin escrituras**: el contenedor de verificación tiene
la raíz y el montaje de solo lectura y no ofrece tmpfs, así que este oráculo
comprueba el núcleo puro del contrato (decisión de transición, validación y
reconciliación). La atomicidad, el fsync y los wrappers de fichero los cubre la
suite del proyecto y la VM de habilitación. Salida: 0 pasa; 42 falla la
aserción que este control representa; 1 error de preparación. El código 42 se
reserva para esa aserción: un fallo genérico no acredita RED.
"""

from __future__ import annotations

import os
import sys
import traceback

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for sub in (os.path.join(BASE, "deploy", "ops"), os.path.join(BASE, "src", "zascarr", "services")):
    if sub not in sys.path:
        sys.path.insert(0, sub)

ID = "0123456789abcdef0123456789abcdef"
OTRO_ID = "fedcba9876543210fedcba9876543210"
SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
AHORA = 1_700_000_000
SIN_NOTICIAS = 7200

CAMPOS_V2 = {
    "schema", "id", "unidad", "estado", "fase", "inicio_epoch", "actualizado_epoch",
    "head0", "sha_destino", "sha_actual", "resultado", "codigo",
}


def exige(cond: object, mensaje: str) -> None:
    if not cond:
        raise AssertionError(mensaje)


def inicial() -> dict[str, object]:
    return {
        "schema": 2, "id": ID, "unidad": "zascarr-actualizar.service",
        "estado": "aceptada", "fase": "aceptada",
        "inicio_epoch": AHORA, "actualizado_epoch": AHORA,
        "head0": None, "sha_destino": None, "sha_actual": None,
        "resultado": None, "codigo": None,
    }


def v1(**cambios: object) -> dict[str, object]:
    datos = {"schema": 1, "id": ID, "estado": "aceptada",
             "inicio_epoch": AHORA, "actualizado_epoch": AHORA}
    datos.update(cambios)
    return datos


def check_contrato(w, l) -> None:
    ini = w.estado_inicial(ID, AHORA)
    exige(set(ini) == CAMPOS_V2, "estado_inicial no tiene las 12 claves del esquema 2")
    exige(ini == inicial(), "estado_inicial no coincide con la instantánea del contrato")
    exige(w.validar_estado(ini), "un v2 recién creado no es válido")
    exige(w.validar_estado(v1()), "un v1 válido no es válido")
    for malo in (
        v1(estado="inventado"),
        v1(inicio_epoch=-1),
        {**v1(), "extra": 1},
        {**inicial(), "schema": 3},
        {**inicial(), "fase": "inventada"},
        {**inicial(), "head0": "corta"},
        {**inicial(), "resultado": "hecha"},
        {**inicial(), "estado": "hecha", "fase": "git", "resultado": "hecha"},
        {**inicial(), "sha_actual": SHA_C, "resultado": "incierta"},
    ):
        exige(not w.validar_estado(malo), "validar_estado acepta un estado fuera del contrato")

    it = l.interpretar_ultimo_intento(ini, ahora_epoch=AHORA + 1)
    exige(it is not None, "interpretar_ultimo_intento no devuelve el intento v2")
    exige(it.estado == l.EstadoActualizacion.ACEPTADA, "estado inicial distinto de aceptada")
    exige(it.fase == "aceptada", "fase inicial distinta de aceptada")
    exige((it.inicio_epoch, it.actualizado_epoch) == (AHORA, AHORA), "épocas iniciales alteradas")
    exige((it.head0, it.sha_destino, it.sha_actual) == (None, None, None), "hashes inventados")
    exige((it.resultado, it.codigo) == (None, None), "resultado inventado en no terminal")
    exige(it.sin_noticias is False, "aceptada fresca marcada sin noticias")
    antiguo = l.interpretar_ultimo_intento(v1(), ahora_epoch=AHORA + 1)
    exige(antiguo is not None and antiguo.fase == "aceptada", "v1 no se interpreta como aceptada")
    exige(antiguo.head0 is None and antiguo.resultado is None, "v1 inventa campos v2")

    nuevo = w.calcular_transicion(
        ini, "en_curso", ahora=AHORA + 10, fase="copia", head0=SHA_A, sha_destino=SHA_B,
    )
    exige(isinstance(nuevo, dict), "calcular_transicion no publica en_curso con hashes")
    exige(
        (nuevo["estado"], nuevo["fase"], nuevo["head0"], nuevo["sha_destino"])
        == ("en_curso", "copia", SHA_A, SHA_B),
        "la transición no conserva los campos del contrato",
    )
    exige(nuevo["actualizado_epoch"] == AHORA + 10, "la transición no actualiza la época")
    exige(nuevo["id"] == ID and nuevo["inicio_epoch"] == AHORA, "la transición cambia id/inicio")
    exige((nuevo["resultado"], nuevo["codigo"]) == (None, None), "resultado en no terminal")
    exige(w.validar_estado(nuevo), "la transición produce un estado inválido")

    final = w.calcular_transicion(
        nuevo, "hecha", ahora=AHORA + 20, fase="fin", codigo="success:exited:0",
    )
    exige(
        isinstance(final, dict)
        and (final["estado"], final["fase"], final["resultado"], final["codigo"])
        == ("hecha", "fin", "hecha", "success:exited:0"),
        "el terminal no escribe estado/resultado/código del contrato",
    )
    exige(w.validar_estado(final), "el terminal no valida")
    visto = l.interpretar_ultimo_intento(final, ahora_epoch=AHORA + 30)
    exige(visto is not None and visto.estado == l.EstadoActualizacion.HECHA, "no se ve el terminal")

    exige(
        isinstance(w.calcular_transicion(v1(), "en_curso", ahora=AHORA + 10, fase="git"), dict),
        "un v1 válido no puede transicionar a v2",
    )
    for args in ((ID, -1), ("no-hex", AHORA), (ID, "ahora")):
        try:
            w.estado_inicial(*args)
        except ValueError:
            pass
        else:
            raise AssertionError("estado_inicial acepta identidad o época inválidas")


def check_monotonia(w, l) -> None:
    ini = inicial()
    antes = dict(ini)
    en_curso = w.calcular_transicion(
        ini, "en_curso", ahora=AHORA + 10, fase="copia", head0=SHA_A, sha_destino=SHA_B,
    )
    exige(isinstance(en_curso, dict), "siembra de transición")
    exige(ini == antes, "calcular_transicion muta el estado de entrada")

    for titulo, resultado in (
        ("la fase no puede retroceder",
         w.calcular_transicion(en_curso, "en_curso", ahora=AHORA + 11, fase="preparacion")),
        ("head0 no puede cambiar una vez fijado",
         w.calcular_transicion(en_curso, "en_curso", ahora=AHORA + 11, fase="git", head0=SHA_C)),
        ("sha_destino no puede cambiar una vez fijado",
         w.calcular_transicion(en_curso, "en_curso", ahora=AHORA + 11, fase="git", sha_destino=SHA_C)),
        ("el reloj no puede retroceder",
         w.calcular_transicion(en_curso, "en_curso", ahora=AHORA + 5, fase="git")),
        ("un id ajeno no puede transicionar",
         w.calcular_transicion(en_curso, "en_curso", ahora=AHORA + 11, fase="git", id_=OTRO_ID)),
        ("un inicio ajeno no puede transicionar",
         w.calcular_transicion(en_curso, "en_curso", ahora=AHORA + 11, fase="git",
                               inicio_epoch=AHORA + 1)),
        ("un hash no vuelve a null",
         w.calcular_transicion(en_curso, "en_curso", ahora=AHORA + 11, fase="git", head0=None)),
        ("un terminal exige fase fin",
         w.calcular_transicion(en_curso, "hecha", ahora=AHORA + 11, fase="git")),
        ("un terminal no admite código abierto",
         w.calcular_transicion(en_curso, "hecha", ahora=AHORA + 11, fase="fin", codigo="libre")),
        ("no se vuelve a aceptada",
         w.calcular_transicion(en_curso, "aceptada", ahora=AHORA + 11, fase="git")),
    ):
        exige(resultado is None, titulo)

    exige(w.calcular_transicion(en_curso, "en_curso", ahora=AHORA + 11, fase="git") is not None,
          "la misma fase con avance debe aceptarse")
    exige(w.calcular_transicion(en_curso, "en_curso", ahora=AHORA + 11, fase="git",
                                sha_actual=SHA_C) is not None,
          "sha_actual puede avanzar")
    exige(w.calcular_transicion(en_curso, "en_curso", ahora=AHORA + 11, fase="git",
                                sha_actual=SHA_C, codigo=None) is not None,
          "codigo nulo explícito no debe romper")
    incierto = w.calcular_transicion(
        en_curso, "incierta", ahora=AHORA + 20, fase="fin", codigo="otro",
    )
    exige(isinstance(incierto, dict) and incierto["resultado"] == "incierta"
          and incierto["codigo"] == "otro", "no se publica el terminal incierto")
    exige(w.calcular_transicion(incierto, "hecha", ahora=AHORA + 30, fase="fin") is None,
          "un terminal no se pisa")
    exige(
        l.interpretar_ultimo_intento(incierto, ahora_epoch=AHORA + 40).estado
        == l.EstadoActualizacion.INCIERTA,
        "el lector no respeta el terminal incierto",
    )

    elevado = w.calcular_transicion(v1(), "en_curso", ahora=AHORA + 10, fase="preparacion")
    exige(
        isinstance(elevado, dict) and set(elevado) == CAMPOS_V2
        and elevado["id"] == ID and elevado["fase"] == "preparacion"
        and elevado["head0"] is None,
        "la elevación de v1 a v2 pierde identidad, fase o nulos",
    )
    exige(not w.validar_estado({**inicial(), "extra": 1}), "una clave de más es válida")
    exige(not w.validar_estado({**inicial(), "schema": 3}), "un esquema desconocido es válido")
    exige(not w.validar_estado({**inicial(), "fase": "inventada"}), "una fase abierta es válida")
    exige(not w.validar_estado(None) and not w.validar_estado([]), "un no-objeto es válido")
    exige(w.calcular_transicion(None, "en_curso", ahora=AHORA) is None, "transiciona desde nada")
    exige(w.calcular_transicion(v1(estado="hecha"), "hecha", ahora=AHORA + 1, fase="fin") is None,
          "transiciona desde un terminal v1")


def check_reconciliacion(w, l) -> None:
    ini = inicial()
    fresco = l.interpretar_ultimo_intento(ini, ahora_epoch=AHORA + SIN_NOTICIAS - 1)
    exige(fresco is not None and fresco.estado == l.EstadoActualizacion.ACEPTADA, "fresco mal leído")
    exige(fresco.sin_noticias is False, "fresco marcado sin noticias")
    justo = l.interpretar_ultimo_intento(ini, ahora_epoch=AHORA + SIN_NOTICIAS)
    exige(justo is not None and justo.estado == l.EstadoActualizacion.INCIERTA,
          "un activo sin noticias no es incierto")
    exige(justo.sin_noticias is True, "sin_noticias no se marca en el límite")
    exige(justo.estado != l.EstadoActualizacion.FALLIDA, "sin noticias no es un fallo")

    en_curso = w.calcular_transicion(ini, "en_curso", ahora=AHORA + 10, fase="build")
    viejo = l.interpretar_ultimo_intento(en_curso, ahora_epoch=AHORA + 10 + SIN_NOTICIAS)
    exige(viejo is not None and viejo.estado == l.EstadoActualizacion.INCIERTA,
          "en_curso antiguo no se reconcilia")
    exige(viejo.fase == "build", "la reconciliación pierde la fase")
    exige(viejo.head0 is None and viejo.sha_destino is None, "la reconciliación inventa hashes")

    hecha = w.calcular_transicion(en_curso, "hecha", ahora=AHORA + 20, fase="fin",
                                  codigo="success:exited:0")
    terminal = l.interpretar_ultimo_intento(hecha, ahora_epoch=AHORA + 10_000_000)
    exige(terminal is not None and terminal.estado == l.EstadoActualizacion.HECHA,
          "un terminal antiguo deja de ser terminal")
    exige(terminal.sin_noticias is False, "un terminal no es sin noticias")
    exige(terminal.resultado == "hecha" and terminal.codigo == "success:exited:0",
          "el terminal no conserva resultado/código")

    for titulo, datos in (
        ("época futura", {**ini, "actualizado_epoch": AHORA + 100}),
        ("clave de más", {**ini, "extra": 1}),
        ("hash mal formado", {**ini, "head0": "corta"}),
        ("fase inventada", {**ini, "fase": "inventada"}),
        ("esquema desconocido", {**ini, "schema": 3}),
        ("resultado en no terminal", {**ini, "resultado": "hecha"}),
        ("unidad ajena", {**ini, "unidad": "otra.service"}),
    ):
        exige(
            l.interpretar_ultimo_intento(datos, ahora_epoch=AHORA + 1) is None,
            f"interpretar_ultimo_intento acepta {titulo}",
        )
    exige(l.interpretar_ultimo_intento(None, ahora_epoch=AHORA) is None, "None no es None")
    exige(l.interpretar_ultimo_intento(ini, ahora_epoch=-1) is None, "reloj inválido no falla cerrado")
    exige(l.interpretar_ultimo_intento(ini, ahora_epoch=AHORA - 1) is None,
          "una época futura respecto del reloj no es inválida")


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
        import estado_actualizacion as l
    except (ImportError, SyntaxError):
        traceback.print_exc()
        return 1
    try:
        CHECKS[argv[1]](w, l)
    except AssertionError as exc:
        print(f"FALLO {argv[1]}: {exc}", file=sys.stderr)
        return 42
    except Exception:  # noqa: BLE001 — comportamiento ausente o roto, no infraestructura
        traceback.print_exc()
        print(f"FALLO {argv[1]}: excepción de comportamiento", file=sys.stderr)
        return 42
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
