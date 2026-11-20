"""Barreras estáticas entre experimentos OPS4 y el código en servicio."""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
EXPERIMENTOS = (
    RAIZ / "deploy" / "ops" / "experimento_objetos_ops4.py",
    RAIZ / "deploy" / "ops" / "experimento_identidad_ops4.py",
    RAIZ / "deploy" / "ops" / "modelo_aprobacion_ops4.py",
    RAIZ / "deploy" / "ops" / "experimento_estado_unidad_ops4.py",
    RAIZ / "deploy" / "ops" / "experimento_registro_aprobacion_ops4.py",
    RAIZ / "deploy" / "ops" / "protocolo_actualizar_ops4.py",
)
PROHIBIDO = (
    "subprocess", "socket", "urllib", "http.client", "Popen", "os.system",
    "docker", "update.sh",
)


def test_los_experimentos_no_se_importan_desde_runtime() -> None:
    rutas = list((RAIZ / "src" / "zascarr").rglob("*.py"))
    rutas += [RAIZ / "deploy" / "ops" / "zascarr_ops.py"]
    for ruta in rutas:
        texto = ruta.read_text(encoding="utf-8")
        assert "experimento_" not in texto, ruta
        assert "modelo_aprobacion_ops4" not in texto, ruta
        assert "protocolo_actualizar_ops4" not in texto, ruta
        if ruta.name != "solicitud_actualizacion.py":
            assert "ops_actualizacion_protocolo" not in texto, ruta


def test_experimentos_sin_procesos_red_ni_ejecucion() -> None:
    for ruta in EXPERIMENTOS:
        assert ruta.is_file(), ruta
        texto = ruta.read_text(encoding="utf-8")
        for token in PROHIBIDO:
            assert token not in texto, (ruta, token)


def test_la_ui_no_menciona_ejecutar_actualizaciones() -> None:
    plantillas = (RAIZ / "src" / "zascarr" / "web" / "templates").rglob("*.html")
    for ruta in plantillas:
        texto = ruta.read_text(encoding="utf-8").lower()
        assert "actualizar ahora" not in texto, ruta
        assert "hx-post=\"/ui/actualizar" not in texto, ruta


def test_experimentos_no_realizan_io_ni_persisten() -> None:
    for ruta in EXPERIMENTOS:
        texto = ruta.read_text(encoding="utf-8")
        for token in ("open(", "Path(", "tempfile", "shutil", "sqlite3", "import os"):

            assert token not in texto, (ruta, token)


def test_el_servicio_de_solicitud_no_esta_conectado_a_la_web() -> None:
    rutas = list((RAIZ / "src" / "zascarr" / "web").rglob("*.py"))
    rutas += list((RAIZ / "src" / "zascarr" / "api").rglob("*.py"))
    rutas.append(RAIZ / "src" / "zascarr" / "main.py")
    for ruta in rutas:
        texto = ruta.read_text(encoding="utf-8")
        assert "solicitud_actualizacion" not in texto, ruta
        assert "ops_actualizacion_protocolo" not in texto, ruta


def test_la_admision_de_actualizacion_no_esta_conectada_al_auxiliar() -> None:
    auxiliar = (RAIZ / "deploy" / "ops" / "zascarr_ops.py").read_text(encoding="utf-8")
    assert "admision_actualizar_ops4" not in auxiliar
    for ruta in (RAIZ / "src" / "zascarr").rglob("*.py"):
        assert "admision_actualizar_ops4" not in ruta.read_text(encoding="utf-8"), ruta


def test_lectores_nuevos_no_estan_conectados_al_auxiliar() -> None:
    auxiliar = (RAIZ / "deploy" / "ops" / "zascarr_ops.py").read_text(encoding="utf-8")
    for nombre in ("lector_credenciales_ops4", "prueba_viva_ops4"):
        assert nombre not in auxiliar
        for ruta in (RAIZ / "src" / "zascarr").rglob("*.py"):
            assert nombre not in ruta.read_text(encoding="utf-8"), ruta
