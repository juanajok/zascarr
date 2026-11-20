"""Barreras estáticas entre experimentos OPS4 y el código en servicio."""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
EXPERIMENTOS = (
    RAIZ / "deploy" / "ops" / "experimento_objetos_ops4.py",
    RAIZ / "deploy" / "ops" / "experimento_identidad_ops4.py",
    RAIZ / "deploy" / "ops" / "modelo_aprobacion_ops4.py",
)
PROHIBIDO = (
    "subprocess", "socket", "urllib", "http.client", "Popen", "systemctl",
    "os.system", "docker", "update.sh",
)


def test_los_experimentos_no_se_importan_desde_runtime() -> None:
    rutas = list((RAIZ / "src" / "zascarr").rglob("*.py"))
    rutas += [RAIZ / "deploy" / "ops" / "zascarr_ops.py"]
    for ruta in rutas:
        texto = ruta.read_text(encoding="utf-8")
        assert "experimento_" not in texto, ruta
        assert "modelo_aprobacion_ops4" not in texto, ruta


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
