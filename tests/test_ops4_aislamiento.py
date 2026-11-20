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
    RAIZ / "deploy" / "ops" / "verificador_autorizacion_ops4.py",
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


def test_la_admision_de_host_no_esta_conectada_al_auxiliar() -> None:
    auxiliar = (RAIZ / "deploy" / "ops" / "zascarr_ops.py").read_text(encoding="utf-8")
    for nombre in ("admision_host_actualizar_ops4",):
        assert nombre not in auxiliar
        for ruta in (RAIZ / "src" / "zascarr").rglob("*.py"):
            assert nombre not in ruta.read_text(encoding="utf-8"), ruta


def test_el_escritor_de_estado_no_esta_conectado() -> None:
    auxiliar = (RAIZ / "deploy" / "ops" / "zascarr_ops.py").read_text(encoding="utf-8")
    for nombre in ("escritor_estado_actualizar_ops4", "modelo_fases_actualizacion_ops4"):
        assert nombre not in auxiliar
        for ruta in (RAIZ / "src" / "zascarr").rglob("*.py"):
            assert nombre not in ruta.read_text(encoding="utf-8"), ruta


def test_el_transporte_de_actualizacion_no_esta_conectado() -> None:
    for ruta in list((RAIZ / "src" / "zascarr" / "web").rglob("*.py")) + list(
        (RAIZ / "src" / "zascarr" / "api").rglob("*.py")
    ) + [RAIZ / "src" / "zascarr" / "main.py"]:
        texto = ruta.read_text(encoding="utf-8")
        assert "actualizacion_transporte" not in texto, ruta


def test_el_ejecutor_fijo_no_esta_conectado() -> None:
    auxiliar = (RAIZ / "deploy" / "ops" / "zascarr_ops.py").read_text(encoding="utf-8")
    assert "ejecutor_actualizar_ops4" not in auxiliar
    for ruta in (RAIZ / "src" / "zascarr").rglob("*.py"):
        assert "ejecutor_actualizar_ops4" not in ruta.read_text(encoding="utf-8"), ruta


def test_el_limite_de_intentos_no_esta_conectado() -> None:
    auxiliar = (RAIZ / "deploy" / "ops" / "zascarr_ops.py").read_text(encoding="utf-8")
    assert "limite_intentos_actualizar_ops4" not in auxiliar
    for ruta in (RAIZ / "src" / "zascarr").rglob("*.py"):
        assert "limite_intentos_actualizar_ops4" not in ruta.read_text(encoding="utf-8"), ruta


def test_el_registro_antirrepeticion_no_esta_conectado() -> None:
    nombre = "registro_repeticiones_ops4"
    paths = list((RAIZ / "src" / "zascarr").rglob("*.py"))
    paths += [RAIZ / "deploy" / "ops" / "zascarr_ops.py", RAIZ / "scripts" / "instalar_ops.sh"]
    for path in paths:
        assert nombre not in path.read_text(encoding="utf-8"), path


def test_la_autorizacion_app_host_no_esta_conectada() -> None:
    nombres = ("autorizacion_actualizacion", "verificador_autorizacion_ops4")
    for nombre in nombres:
        for ruta in (RAIZ / "src" / "zascarr").rglob("*.py"):
            if ruta.name == "autorizacion_actualizacion.py":
                continue
            assert nombre not in ruta.read_text(encoding="utf-8"), ruta
        assert nombre not in (RAIZ / "deploy" / "ops" / "zascarr_ops.py").read_text(
            encoding="utf-8"
        )
    for ruta in (
        RAIZ / "src" / "zascarr" / "main.py",
        RAIZ / "scripts" / "instalar_ops.sh",
    ):
        assert "autorizacion_actualizacion" not in ruta.read_text(encoding="utf-8"), ruta


def test_el_emisor_de_autorizacion_no_hace_io_ni_red() -> None:
    ruta = RAIZ / "src" / "zascarr" / "services" / "autorizacion_actualizacion.py"
    texto = ruta.read_text(encoding="utf-8")
    for token in ("open(", "Path(", "subprocess", "socket", "docker", "update.sh"):
        assert token not in texto, token


def test_la_composicion_de_autorizacion_no_se_importa_desde_runtime() -> None:
    rutas = list((RAIZ / "src" / "zascarr").rglob("*.py"))
    rutas += [
        RAIZ / "deploy" / "ops" / "zascarr_ops.py",
        RAIZ / "src" / "zascarr" / "main.py",
        RAIZ / "scripts" / "instalar_ops.sh",
    ]
    for ruta in rutas:
        if ruta.name == "autorizacion_actualizacion.py":
            continue
        texto = ruta.read_text(encoding="utf-8")
        assert "preparar_autorizacion" not in texto, ruta
        assert "ResultadoAutorizacion" not in texto, ruta


def test_el_emisor_no_usa_la_clave_del_auxiliar_ni_registra() -> None:
    ruta = RAIZ / "src" / "zascarr" / "services" / "autorizacion_actualizacion.py"
    texto = ruta.read_text(encoding="utf-8")
    for token in ("ops_key_file", "ops.key", "get_settings", "logging", "logger", "print("):
        assert token not in texto, token


def test_el_verificador_no_lee_hashes_ni_la_bd() -> None:
    ruta = RAIZ / "deploy" / "ops" / "verificador_autorizacion_ops4.py"
    texto = ruta.read_text(encoding="utf-8").lower()
    for token in (
        "pbkdf2", "auth_password_hash", "asyncpg", "sqlalchemy", "select(",
        "database_url", "session",
    ):
        assert token not in texto, token


def test_el_registro_de_autorizacion_no_se_conecta_a_runtime_ni_al_auxiliar() -> None:
    nombre = "registro_repeticiones_ops4"
    auxiliar = (RAIZ / "deploy" / "ops" / "zascarr_ops.py").read_text(encoding="utf-8")
    assert nombre not in auxiliar
    assert nombre not in (RAIZ / "scripts" / "instalar_ops.sh").read_text(encoding="utf-8")
    for ruta in (RAIZ / "src" / "zascarr").rglob("*.py"):
        assert nombre not in ruta.read_text(encoding="utf-8"), ruta


def test_el_lector_de_clave_dedicada_no_esta_conectado() -> None:
    nombre = "clave_autorizacion"
    for ruta in (RAIZ / "src" / "zascarr").rglob("*.py"):
        if ruta.name == "clave_autorizacion.py":
            continue
        assert nombre not in ruta.read_text(encoding="utf-8"), ruta
    for ruta in (
        RAIZ / "deploy" / "ops" / "zascarr_ops.py",
        RAIZ / "scripts" / "instalar_ops.sh",
    ):
        assert nombre not in ruta.read_text(encoding="utf-8"), ruta


def test_el_protocolo_v4_no_esta_conectado() -> None:
    for nombre in (
        "protocolo_actualizar_v4_ops4", "admision_v4_actualizar_ops4",
        "ops_actualizacion_v4",
    ):
        for ruta in (RAIZ / "src" / "zascarr").rglob("*.py"):
            if ruta.name == "ops_actualizacion_v4.py":
                continue
            assert nombre not in ruta.read_text(encoding="utf-8"), ruta
        assert nombre not in (RAIZ / "deploy" / "ops" / "zascarr_ops.py").read_text(
            encoding="utf-8"
        )
        assert nombre not in (RAIZ / "scripts" / "instalar_ops.sh").read_text(
            encoding="utf-8"
        )


def test_el_transporte_v4_no_esta_conectado() -> None:
    nombre = "actualizacion_transporte_v4"
    for ruta in (RAIZ / "src" / "zascarr").rglob("*.py"):
        if ruta.name == "actualizacion_transporte_v4.py":
            continue
        assert nombre not in ruta.read_text(encoding="utf-8"), ruta
    assert nombre not in (RAIZ / "deploy" / "ops" / "zascarr_ops.py").read_text(
        encoding="utf-8"
    )
