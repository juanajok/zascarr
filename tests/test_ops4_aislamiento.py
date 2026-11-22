"""Barreras de la historia B limpia: sin v3, experimentos ni conexiones extra."""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MUERTOS = (
    "protocolo_actualizar_ops4.py",
    "admision_actualizar_ops4.py",
    "admision_host_actualizar_ops4.py",
    "ejecutor_actualizar_ops4.py",
    "lector_credenciales_ops4.py",
    "limite_intentos_actualizar_ops4.py",
    "modelo_aprobacion_ops4.py",
    "modelo_fases_actualizacion_ops4.py",
    "ops_actualizacion_protocolo.py",
    "prueba_viva_ops4.py",
    "validar_inventario_ops4.py",
)
MUERTOS_SRC = (
    "zascarr.services.actualizacion_transporte import",
    "zascarr.services.solicitud_actualizacion import",
    "zascarr.services.ops_actualizacion_protocolo import",
)


def test_no_quedan_modulos_de_protocolo_v3_ni_experimentos() -> None:
    for nombre in MUERTOS:
        assert not list((RAIZ / "deploy").rglob(nombre)), nombre
    assert not list((RAIZ / "deploy").rglob("experimento_*"))
    for nombre in MUERTOS_SRC:
        modulo = nombre.split()[0].replace(".", "/") + ".py"
        assert not (RAIZ / "src" / modulo).exists(), modulo


def test_el_runtime_no_importa_los_modulos_muertos() -> None:
    rutas = list((RAIZ / "src" / "zascarr").rglob("*.py"))
    rutas += [RAIZ / "deploy" / "ops" / "zascarr_ops.py"]
    for ruta in rutas:
        texto = ruta.read_text(encoding="utf-8")
        for nombre in MUERTOS_SRC:
            assert nombre not in texto, (ruta, nombre)
        for nombre in MUERTOS:
            assert f"deploy.ops.{nombre[:-3]}" not in texto, (ruta, nombre)


def test_solo_la_puerta_web_usa_el_servicio_v4() -> None:
    consumidores = []
    for ruta in (RAIZ / "src" / "zascarr").rglob("*.py"):
        if "solicitud_actualizacion_v4" in ruta.read_text(encoding="utf-8"):
            consumidores.append(ruta)
    assert consumidores == [RAIZ / "src" / "zascarr" / "web" / "actualizacion.py"]


def test_el_auxiliar_no_se_importa_desde_la_app() -> None:
    for ruta in (RAIZ / "src" / "zascarr").rglob("*.py"):
        assert "zascarr_actualizar_aux" not in ruta.read_text(encoding="utf-8"), ruta


def test_la_unidad_no_esta_en_el_instalador_de_copias() -> None:
    texto = (RAIZ / "scripts" / "instalar_ops.sh").read_text(encoding="utf-8")
    assert "zascarr-actualizar" not in texto
    assert "actualizar.key" not in texto


def test_la_app_no_importa_el_codigo_privilegiado_del_host() -> None:
    for ruta in (RAIZ / "src" / "zascarr").rglob("*.py"):
        texto = ruta.read_text(encoding="utf-8")
        assert "deploy.ops" not in texto, ruta
        assert "from deploy" not in texto, ruta


def test_el_instalador_copia_todo_lo_que_importa_el_auxiliar() -> None:
    aux = (RAIZ / "deploy" / "ops" / "zascarr_actualizar_aux.py").read_text(encoding="utf-8")
    instalador = (RAIZ / "scripts" / "instalar_actualizacion_ops4.sh").read_text(encoding="utf-8")
    for modulo in (
        "protocolo_actualizar_v4_ops4",
        "verificador_autorizacion_ops4",
        "registro_repeticiones_ops4",
        "escritor_estado_actualizar_ops4",
    ):
        assert f"from {modulo} import" in aux, modulo
        assert modulo in instalador, modulo
    assert "zascarr-estado-actualizar-ops4" in instalador


def test_el_auxiliar_y_la_unidad_usan_python_aislado() -> None:
    unidad = (RAIZ / "deploy" / "systemd" / "zascarr-actualizar@.service").read_text(encoding="utf-8")
    assert "/usr/bin/python3 -I" in unidad
    assert "Environment=PYTHONPATH=" not in unidad
    assert "ReadWritePaths=@ZASCARR_DATA_DIR@/ops4 @ZASCARR_DATA_DIR@/ops" in unidad
