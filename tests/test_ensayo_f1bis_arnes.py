# ruff: noqa: E501
"""El ARNÉS del ensayo M4 fase 1 bis (`docs/design/m4-fase1bis/`) hace cumplir lo que el guion presenta como garantizado.

El guion promete: presupuesto de descarga que se corta mientras se descarga; almacenamiento y espacio libre vigilados; límites de
tiempo que se aplican dentro de la VM; una limpieza que no deja la VM viva ante errores o señales; identificación de la VM propia por
PID y atributos (sin señalar procesos ajenos); `ejecutar` que rechaza una preparación incompleta; precondiciones que impiden instalar;
apagado inmediato de las fuentes tras instalar. Aquí se comprueba con DOBLES y PROCESOS CONTROLADOS, sin arrancar QEMU, sin Docker y
sin red: una «VM» de mentira (`tests/_vm_falsa.py`), un contador de bytes recibidos que se mueve a voluntad y órdenes sustituidas.
"""
from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.name != "posix" or shutil.which("bash") is None or not Path("/proc/self/status").exists(),
    reason="requiere bash y /proc (Linux)",
)

REPO = Path(__file__).resolve().parents[1]
DOC = REPO / "docs" / "design" / "m4-fase1bis"
LIB, ANFITRION, EJECUTAR, PREPARAR = (DOC / n for n in ("lib-ensayo.sh", "anfitrion.sh", "vm-ejecutar.sh", "vm-preparar.sh"))
FALSA = Path(__file__).resolve().parent / "_vm_falsa.py"
ESPERAS = {"ESPERA_APAGADO_S": "2", "ESPERA_TERM_S": "2", "ESPERA_KILL_S": "3"}


def _bash(script: str, *, env: dict[str, str] | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-c", textwrap.dedent(script)], capture_output=True, text=True, timeout=timeout,
                          env={**os.environ, **ESPERAS, **(env or {})}, check=False)


def _lib(cuerpo: str, **kw) -> subprocess.CompletedProcess:
    return _bash(f'source "{LIB}"\n{cuerpo}', **kw)


def _vivo(pid: int) -> bool:
    try:
        estado = next(linea for linea in Path(f"/proc/{pid}/status").read_text().splitlines() if linea.startswith("State:"))
    except (FileNotFoundError, ProcessLookupError):
        return False
    return estado.split()[1] not in ("Z", "X")


def _esperar(condicion, segundos: float = 10.0) -> bool:
    fin = time.time() + segundos
    while time.time() < fin:
        if condicion():
            return True
        time.sleep(0.1)
    return condicion()


def _lanzar_falsa(directorio: Path, **opciones) -> int:
    pidfile = directorio / "qemu.pid"
    args = [sys.executable, str(FALSA), str(pidfile), str(directorio)]
    if opciones.get("ignora_term"):
        args.append("--ignora-term")
    if opciones.get("sin_disco"):
        args.append("--sin-disco")
    if "nombre" in opciones:
        args += ["--nombre", opciones["nombre"]]
    subprocess.run(args, check=True, timeout=20)
    return int(pidfile.read_text())


@pytest.fixture
def dir_ensayo(tmp_path: Path):
    d = tmp_path / "ensayo"
    d.mkdir()
    pids: list[int] = []
    yield d
    # Limpieza de seguridad: ninguna «VM» de mentira queda viva tras una prueba, pase lo que pase.
    pidfile = d / "qemu.pid"
    if pidfile.exists():
        with contextlib.suppress(ValueError):
            pids.append(int(pidfile.read_text()))
    for pid in pids:
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)


# ── lib-ensayo.sh: detección de procesos ────────────────────────────────────────────────────────────────────────────

class TestDeteccionDeQemu:

    def test_pgrep_con_nombre_exacto_no_sirve_y_procesos_qemu_si(self, dir_ensayo):
        """`pgrep -x qemu-system-x86_64` no casa nunca (el nombre de proceso se trunca a 15 caracteres); recorrer /proc sí."""
        pid = _lanzar_falsa(dir_ensayo)
        try:
            assert shutil.which("pgrep") is None or subprocess.run(["pgrep", "-x", "qemu-system-x86_64"], capture_output=True).returncode != 0
            r = _lib("procesos_qemu")
            assert str(pid) in r.stdout.split()
        finally:
            os.kill(pid, signal.SIGKILL)

    def test_un_proceso_cualquiera_no_cuenta(self):
        p = subprocess.Popen(["sleep", "30"])
        try:
            assert str(p.pid) not in _lib("procesos_qemu").stdout.split()
        finally:
            p.kill()
            p.wait()

    def test_un_zombi_no_esta_vivo(self):
        p = subprocess.Popen(["true"])
        time.sleep(0.5)                       # termina y queda zombi hasta que alguien haga wait()
        try:
            assert not _lib(f"proceso_vivo {p.pid}; echo $?").stdout.strip().startswith("0")
        finally:
            p.wait()


class TestIdentificacionDeLaVmPropia:

    def test_la_propia_se_reconoce(self, dir_ensayo):
        pid = _lanzar_falsa(dir_ensayo)
        try:
            assert _lib(f'vm_es_propia {pid} "{dir_ensayo}"; echo $?').stdout.strip() == "0"
        finally:
            os.kill(pid, signal.SIGKILL)

    @pytest.mark.parametrize("opciones", [{"nombre": "otra-vm"}, {"sin_disco": True}], ids=["otro-nombre", "sin-disco-propio"])
    def test_un_qemu_ajeno_no_se_reconoce(self, dir_ensayo, opciones):
        pid = _lanzar_falsa(dir_ensayo, **opciones)
        try:
            assert _lib(f'vm_es_propia {pid} "{dir_ensayo}"; echo $?').stdout.strip() == "1"
        finally:
            os.kill(pid, signal.SIGKILL)

    def test_un_proceso_que_no_es_qemu_no_se_reconoce(self, dir_ensayo):
        p = subprocess.Popen(["sleep", "30"])
        try:
            assert _lib(f'vm_es_propia {p.pid} "{dir_ensayo}"; echo $?').stdout.strip() == "1"
        finally:
            p.kill()
            p.wait()


# ── lib-ensayo.sh: parar la VM propia ───────────────────────────────────────────────────────────────────────────────

class TestPararLaVmPropia:

    def test_apagado_cooperativo_confirma_que_murio_antes_de_borrar_el_pid(self, dir_ensayo):
        pid = _lanzar_falsa(dir_ensayo)
        r = _lib(f'parar_vm_propia "{dir_ensayo}" "{dir_ensayo}/qemu.pid"; echo "rc=$?"; [[ -e "{dir_ensayo}/qemu.pid" ]] && echo PIDFILE || echo SIN_PIDFILE')
        assert "rc=0" in r.stdout and "SIN_PIDFILE" in r.stdout, r.stdout + r.stderr
        assert _esperar(lambda: not _vivo(pid))

    def test_una_que_ignora_term_se_mata_con_kill_en_tiempo_acotado(self, dir_ensayo):
        pid = _lanzar_falsa(dir_ensayo, ignora_term=True)
        t0 = time.time()
        r = _lib(f'parar_vm_propia "{dir_ensayo}" "{dir_ensayo}/qemu.pid"; echo "rc=$?"')
        assert "rc=0" in r.stdout, r.stdout + r.stderr
        assert not _vivo(pid) and time.time() - t0 < 20

    def test_si_no_consigue_matarla_no_borra_el_pid_ni_dice_que_esta_apagada(self, dir_ensayo):
        """`kill` sustituido por una función que no hace nada: el proceso sigue vivo → código 1 y el pidfile se conserva."""
        pid = _lanzar_falsa(dir_ensayo)
        try:
            r = _lib(f'kill() {{ :; }}\nparar_vm_propia "{dir_ensayo}" "{dir_ensayo}/qemu.pid"; echo "rc=$?"')
            assert "rc=1" in r.stdout, r.stdout + r.stderr
            assert (dir_ensayo / "qemu.pid").exists() and _vivo(pid)
        finally:
            os.kill(pid, signal.SIGKILL)

    def test_un_pid_ajeno_no_se_senala_jamas(self, dir_ensayo):
        ajeno = subprocess.Popen(["sleep", "60"])
        try:
            (dir_ensayo / "qemu.pid").write_text(f"{ajeno.pid}\n")
            r = _lib(f'parar_vm_propia "{dir_ensayo}" "{dir_ensayo}/qemu.pid"; echo "rc=$?"')
            assert "rc=3" in r.stdout and "NO se toca" in r.stderr, r.stdout + r.stderr
            assert ajeno.poll() is None, "se mató un proceso ajeno"
            assert (dir_ensayo / "qemu.pid").exists(), "se borró el pidfile de un proceso que no era la VM"
        finally:
            ajeno.kill()
            ajeno.wait()

    def test_un_qemu_de_otra_vm_tampoco(self, dir_ensayo):
        pid = _lanzar_falsa(dir_ensayo, nombre="otra-vm")
        try:
            r = _lib(f'parar_vm_propia "{dir_ensayo}" "{dir_ensayo}/qemu.pid"; echo "rc=$?"')
            assert "rc=3" in r.stdout and _vivo(pid)
        finally:
            os.kill(pid, signal.SIGKILL)

    def test_un_pid_muerto_se_limpia(self, dir_ensayo):
        p = subprocess.Popen(["true"])
        p.wait()
        (dir_ensayo / "qemu.pid").write_text(f"{p.pid}\n")
        r = _lib(f'parar_vm_propia "{dir_ensayo}" "{dir_ensayo}/qemu.pid"; echo "rc=$?"')
        assert "rc=0" in r.stdout and not (dir_ensayo / "qemu.pid").exists()


# ── lib-ensayo.sh: presupuesto de descarga ──────────────────────────────────────────────────────────────────────────

GENERADOR = """
C="$1"; printf 0 > "$C"
( while :; do n=$(cat "$C"); printf '%s' $((n + 20971520)) > "$C"; sleep 0.2; done ) &
GEN=$!
contador_rx_bytes() { cat "$C"; }
"""


class TestPresupuestoDeDescarga:

    def test_se_corta_mientras_se_descarga_y_mata_el_grupo_entero(self, tmp_path):
        """20 MiB cada 0,2 s (≈100 MiB/s): con tope 100 y margen 20 el corte es a 80 MiB, y el comando (y su hijo) mueren."""
        c = tmp_path / "rx"
        t0 = time.time()
        r = _lib(f"""{GENERADOR}
            INTERVALO_S=0.1 con_limite_de_descarga 100 20 -- bash -c 'sleep 61.37 & wait'
            echo "rc=$?"
            kill $GEN 2>/dev/null
        """.replace('"$1"', f'"{c}"').replace('C="$1"', f'C="{c}"'))
        assert "rc=4" in r.stdout, r.stdout + r.stderr
        assert "SE CORTA" in r.stderr and "consumo tras el corte" in r.stderr
        assert time.time() - t0 < 4, "el corte tardó: debe ser inmediato (TERM al grupo), no esperar al KILL de respaldo"
        assert subprocess.run(["pgrep", "-f", "sleep 61.37"], capture_output=True).returncode != 0, "quedó vivo un hijo del comando cortado"

    def test_el_corte_es_al_umbral_y_no_al_tope(self, tmp_path):
        c = tmp_path / "rx"
        r = _lib(f"""C="{c}"; printf 0 > "$C"
            contador_rx_bytes() {{ cat "$C"; }}
            ( sleep 0.3; printf %s $((95 * 1048576)) > "$C" ) &
            INTERVALO_S=0.1 con_limite_de_descarga 100 20 -- bash -c 'sleep 30'
            echo "rc=$?"
        """)
        assert "rc=4" in r.stdout and "95 MiB ≥ umbral de corte 80 MiB" in r.stderr, r.stdout + r.stderr

    def test_por_debajo_del_umbral_devuelve_el_codigo_del_comando(self, tmp_path):
        c = tmp_path / "rx"
        r = _lib(f"""C="{c}"; printf %s $((10 * 1048576)) > "$C"
            contador_rx_bytes() {{ cat "$C"; }}
            INTERVALO_S=0.1 con_limite_de_descarga 100 20 -- bash -c 'sleep 0.5; exit 7'
            echo "rc=$?"
        """)
        assert "rc=7" in r.stdout and "SE CORTA" not in r.stderr, r.stdout + r.stderr

    def test_el_consumo_previo_a_la_ejecucion_cuenta_con_rx_base_bytes(self, tmp_path):
        """El presupuesto es del script entero, no de cada orden: lo ya descargado antes cuenta."""
        c = tmp_path / "rx"
        r = _lib(f"""C="{c}"; printf %s $((90 * 1048576)) > "$C"
            contador_rx_bytes() {{ cat "$C"; }}
            RX_BASE_BYTES=0 INTERVALO_S=0.1 con_limite_de_descarga 100 20 -- bash -c 'sleep 30'
            echo "rc=$?"
        """)
        assert "rc=4" in r.stdout, r.stdout + r.stderr


# ── lib-ensayo.sh: vigilante del anfitrión ──────────────────────────────────────────────────────────────────────────

class TestVigilanteDelAnfitrion:

    def test_poco_espacio_libre_para_la_vm_y_deja_el_motivo(self, dir_ensayo):
        pid = _lanzar_falsa(dir_ensayo)
        r = _lib(f"""libre_gb() {{ echo 3; }}
            vigilante_anfitrion "{dir_ensayo}" "{dir_ensayo}/qemu.pid" 10 25 0.2
            echo "salio rc=$?"
        """, timeout=40)
        assert "salio rc=0" in r.stdout, r.stdout + r.stderr
        assert "espacio libre 3 GiB < 10 GiB" in (dir_ensayo / ".parada").read_text()
        assert _esperar(lambda: not _vivo(pid))

    def test_almacenamiento_por_encima_del_limite_para_la_vm(self, dir_ensayo):
        pid = _lanzar_falsa(dir_ensayo)
        (dir_ensayo / "grande.bin").write_bytes(b"x" * 5000)
        r = _lib(f"""libre_gb() {{ echo 400; }}
            ALMACEN_MAX_BYTES=1000 vigilante_anfitrion "{dir_ensayo}" "{dir_ensayo}/qemu.pid" 10 25 0.2
            echo "salio rc=$?"
        """, timeout=40)
        assert "salio rc=0" in r.stdout
        assert "almacenamiento" in (dir_ensayo / ".parada").read_text()
        assert _esperar(lambda: not _vivo(pid))

    def test_sin_exceso_no_toca_nada(self, dir_ensayo):
        pid = _lanzar_falsa(dir_ensayo)
        try:
            p = subprocess.Popen(["bash", "-c", f'source "{LIB}"; libre_gb() {{ echo 400; }}; vigilante_anfitrion "{dir_ensayo}" "{dir_ensayo}/qemu.pid" 10 25 0.2'])
            time.sleep(1.5)
            assert p.poll() is None and _vivo(pid) and not (dir_ensayo / ".parada").exists()
            p.kill()
            p.wait()
        finally:
            os.kill(pid, signal.SIGKILL)


# ── anfitrion.sh: ciclo de vida con dobles ─────────────────────────────────────────────────────────────────────────

def _doble_anfitrion(dir_ensayo: Path, tmp_path: Path, *, prep: str, extra: str = "", orden: str = "cmd_preparar") -> tuple[str, dict[str, str]]:
    fase1 = tmp_path / "fase1"
    fase1.mkdir(exist_ok=True)
    for n in ("preparacion.qcow2", "base-debian12.qcow2", "ensayo_key", "seed.iso"):
        (fase1 / n).write_text("x")
    cand = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or "0" * 40
    guion = f"""
        source "{ANFITRION}"
        cmd_verificar() {{ return 0; }}
        crear_bundle() {{ : > "${{DIR}}/candidato.bundle"; : > "${{DIR}}/bootstrap.sh"; }}
        qemu-img() {{ local a=("$@"); : > "${{a[-2]}}"; }}
        arrancar() {{ python3 "{FALSA}" "${{PIDFILE}}" "${{DIR}}"; }}
        esperar_ssh() {{ return 0; }}
        scp_vm() {{ return 0; }}
        solicitar_apagado() {{ :; }}
        ssh_remoto() {{
            local seg=$1; shift
            case "$*" in
                *vm-preparar.sh*|*vm-ejecutar.sh*) {prep} ;;
                *) : ;;
            esac
        }}
        {extra}
        {orden}
    """
    env = {"ZASCARR_ENSAYO_DIR": str(dir_ensayo), "ZASCARR_FASE1_DIR": str(fase1), "CANDIDATO": cand,
           "INTERVALO_VIGILANTE_S": "0.3", **ESPERAS}
    return guion, env


PREP_BIEN = 'echo "descargado hasta ahora: 123 MiB (tope 600 MiB)"; echo "PREPARACIÓN TERMINADA"; return 0'
PREP_FALLA = 'echo "algo falló"; return 4'
PREP_SIN_FIN = 'echo "descargado hasta ahora: 5 MiB"; return 0'


class TestCicloDeVidaDelAnfitrion:

    def _correr(self, dir_ensayo, tmp_path, prep, **kw):
        guion, env = _doble_anfitrion(dir_ensayo, tmp_path, prep=prep, **kw)
        return _bash(guion, env=env, timeout=60), env

    def _sin_vm_viva(self, dir_ensayo):
        pid = dir_ensayo / "qemu.pid"
        return not pid.exists() or not _vivo(int(pid.read_text() or 0))

    def test_preparacion_correcta_escribe_el_marcador_y_comprueba_que_la_vm_murio(self, dir_ensayo, tmp_path):
        r, _ = self._correr(dir_ensayo, tmp_path, PREP_BIEN)
        assert r.returncode == 0, r.stdout + r.stderr
        marca = (dir_ensayo / "preparacion.ok").read_text()
        assert "RC=0" in marca and "DESCARGA_MIB=123" in marca and "PREP_BYTES=" in marca
        assert not (dir_ensayo / "qemu.pid").exists() and "VM apagada y comprobada" in (dir_ensayo / "cronologia.txt").read_text()

    @pytest.mark.parametrize("prep", [PREP_FALLA, PREP_SIN_FIN], ids=["rc-distinto-de-cero", "sin-marca-de-fin"])
    def test_preparacion_fallida_o_incompleta_no_escribe_marcador_y_apaga_la_vm(self, dir_ensayo, tmp_path, prep):
        r, _ = self._correr(dir_ensayo, tmp_path, prep)
        assert r.returncode != 0
        assert not (dir_ensayo / "preparacion.ok").exists(), "un marcador de preparación completa tras una preparación fallida"
        assert self._sin_vm_viva(dir_ensayo)

    def test_una_senal_durante_la_preparacion_no_deja_la_vm_viva(self, dir_ensayo, tmp_path):
        """El comando remoto largo va en segundo plano y se espera con `wait`: la señal se atiende AL MOMENTO, no al final de la ventana."""
        guion, env = _doble_anfitrion(dir_ensayo, tmp_path, prep='sleep 25; return 0')
        p = subprocess.Popen(["bash", "-c", textwrap.dedent(guion)], env={**os.environ, **env}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            assert _esperar(lambda: (dir_ensayo / "qemu.pid").exists(), 20), "no llegó a arrancar la VM de mentira"
            pid = int((dir_ensayo / "qemu.pid").read_text())
            time.sleep(1.0)
            t0 = time.time()
            p.send_signal(signal.SIGTERM)
            p.wait(timeout=30)
            assert time.time() - t0 < 15, "tardó en atender la señal (el trap esperó al final de la orden en primer plano)"
            assert _esperar(lambda: not _vivo(pid)), "la VM quedó viva tras SIGTERM"
            assert not (dir_ensayo / "qemu.pid").exists()
            assert not (dir_ensayo / "preparacion.ok").exists()
            assert "LIMPIEZA" in (dir_ensayo / "cronologia.txt").read_text()
        finally:
            if p.poll() is None:
                p.kill()

    def test_un_limite_del_anfitrion_durante_la_preparacion_para_la_vm_y_la_marca_como_fallida(self, dir_ensayo, tmp_path):
        r, _ = self._correr(dir_ensayo, tmp_path, 'sleep 3; echo "PREPARACIÓN TERMINADA"; return 0', extra="libre_gb() { echo 2; }")
        assert r.returncode != 0
        assert "PARADA POR LÍMITE DEL ANFITRIÓN" in r.stderr, r.stdout + r.stderr
        assert not (dir_ensayo / "preparacion.ok").exists(), "una preparación interrumpida por un límite se dio por buena"
        assert self._sin_vm_viva(dir_ensayo)

    def test_si_el_pidfile_apunta_a_otro_proceso_no_se_toca_y_se_avisa(self, dir_ensayo, tmp_path):
        ajeno = subprocess.Popen(["sleep", "60"])
        try:
            guion, env = _doble_anfitrion(dir_ensayo, tmp_path, prep=PREP_BIEN,
                                          extra='arrancar() { echo "' + str(ajeno.pid) + '" > "${PIDFILE}"; }')
            r = _bash(guion, env=env, timeout=60)
            assert ajeno.poll() is None, "se mató un proceso ajeno por estar en el pidfile"
            assert r.returncode != 0 and "no es la VM de este ensayo" in (r.stdout + r.stderr)
        finally:
            ajeno.kill()
            ajeno.wait()


class TestEjecutarExigeUnaPreparacionCompleta:

    def _marcador(self, d: Path, cand: str, rc: str = "0") -> None:
        prep = d / "f1bis-prep.qcow2"
        prep.write_text("overlay")
        (d / "preparacion.ok").write_text(
            f"CANDIDATO={cand}\nRC={rc}\nPREP_BYTES={prep.stat().st_size}\nPREP_MTIME={int(prep.stat().st_mtime)}\nDESCARGA_MIB=10\n")

    def _ejecutar(self, d, tmp_path):
        guion, env = _doble_anfitrion(d, tmp_path, prep=PREP_BIEN, orden='exigir_preparacion_completa; echo "rc=$?"',
                                      extra='arrancar() { echo ARRANCO >> "${DIR}/arranques.txt"; }')
        return _bash(guion, env=env), env

    def test_sin_marcador_se_rechaza(self, dir_ensayo, tmp_path):
        (dir_ensayo / "f1bis-prep.qcow2").write_text("overlay")        # el disco existe, pero la preparación no se completó
        r, _ = self._ejecutar(dir_ensayo, tmp_path)
        assert "rc=1" in r.stdout and "falta" in r.stderr

    def test_marcador_de_otro_candidato(self, dir_ensayo, tmp_path):
        self._marcador(dir_ensayo, "f" * 40)
        r, _ = self._ejecutar(dir_ensayo, tmp_path)
        assert "rc=1" in r.stdout and "otro candidato" in r.stderr

    def test_marcador_con_error(self, dir_ensayo, tmp_path):
        guion, env = _doble_anfitrion(dir_ensayo, tmp_path, prep=PREP_BIEN)
        self._marcador(dir_ensayo, env["CANDIDATO"], rc="4")
        r, _ = self._ejecutar(dir_ensayo, tmp_path)
        assert "rc=1" in r.stdout and "terminó con error" in r.stderr

    def test_el_disco_cambio_despues_de_preparar(self, dir_ensayo, tmp_path):
        _, env = _doble_anfitrion(dir_ensayo, tmp_path, prep=PREP_BIEN)
        self._marcador(dir_ensayo, env["CANDIDATO"])
        (dir_ensayo / "f1bis-prep.qcow2").write_text("modificado después")
        r, _ = self._ejecutar(dir_ensayo, tmp_path)
        assert "rc=1" in r.stdout and "cambió después de preparar" in r.stderr

    def test_parada_registrada_por_un_limite(self, dir_ensayo, tmp_path):
        _, env = _doble_anfitrion(dir_ensayo, tmp_path, prep=PREP_BIEN)
        self._marcador(dir_ensayo, env["CANDIDATO"])
        (dir_ensayo / ".parada").write_text("espacio libre 3 GiB < 10 GiB")
        r, _ = self._ejecutar(dir_ensayo, tmp_path)
        assert "rc=1" in r.stdout and "interrumpió" in r.stderr

    def test_no_se_reutiliza_una_ejecucion_previa(self, dir_ensayo, tmp_path):
        _, env = _doble_anfitrion(dir_ensayo, tmp_path, prep=PREP_BIEN)
        self._marcador(dir_ensayo, env["CANDIDATO"])
        (dir_ensayo / "f1bis-ejec.qcow2").write_text("anterior")
        r, _ = self._ejecutar(dir_ensayo, tmp_path)
        assert "rc=1" in r.stdout and "ejecución previa" in r.stderr

    def test_la_preparacion_completa_se_acepta(self, dir_ensayo, tmp_path):
        _, env = _doble_anfitrion(dir_ensayo, tmp_path, prep=PREP_BIEN)
        self._marcador(dir_ensayo, env["CANDIDATO"])
        r, _ = self._ejecutar(dir_ensayo, tmp_path)
        assert "rc=0" in r.stdout, r.stdout + r.stderr

    def test_cmd_ejecutar_no_llega_a_arrancar_la_vm_sin_preparacion_completa(self, dir_ensayo, tmp_path):
        (dir_ensayo / "f1bis-prep.qcow2").write_text("overlay")
        guion, env = _doble_anfitrion(dir_ensayo, tmp_path, prep=PREP_BIEN, orden="cmd_ejecutar",
                                      extra='arrancar() { echo ARRANCO >> "${DIR}/arranques.txt"; }')
        r = _bash(guion, env=env)
        assert r.returncode != 0 and not (dir_ensayo / "arranques.txt").exists(), "arrancó la VM sin una preparación completa"


# ── vm-ejecutar.sh: precondiciones, orden y órdenes ────────────────────────────────────────────────────────────────

def _ejecutar(cuerpo: str, tmp_path: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return _bash(f'export EV="{tmp_path}/ev" RAIZ="{tmp_path}/opt"\nsource "{EJECUTAR}"\n{cuerpo}', env=env)


class TestPrecondicionesYOrden:

    def test_una_precondicion_fallida_impide_instalar(self, tmp_path):
        r = _ejecutar("""
            seccion_antes() { fail A-10 "HAY salida a Internet"; return 1; }
            seccion_instalacion() { echo "INSTALACION EJECUTADA (error)"; }
            seccion_cierre() { echo cierre; }
            principal antes instalacion; echo "rc=$?"
        """, tmp_path)
        assert "INSTALACION EJECUTADA" not in r.stdout and "rc=2" in r.stdout, r.stdout
        assert "PRECONDICIÓN FALLIDA" in r.stdout and "NO del producto" in r.stdout

    def test_el_orden_apaga_las_fuentes_justo_tras_instalar(self, tmp_path):
        r = _ejecutar("""
            for s in antes instalacion fuentes_iniciales salud credenciales reejecucion originales fuentes_persistencia cierre; do
                eval "seccion_$s() { echo \\"SECCION $s\\"; }"
            done
            principal
        """, tmp_path)
        orden = [linea.split()[1] for linea in r.stdout.splitlines() if linea.startswith("SECCION ")]
        assert orden == ["antes", "instalacion", "fuentes_iniciales", "salud", "credenciales", "reejecucion", "originales",
                         "fuentes_persistencia", "cierre"], orden

    def test_si_las_fuentes_no_quedan_apagadas_no_se_sigue(self, tmp_path):
        r = _ejecutar("""
            seccion_antes() { :; }; seccion_instalacion() { :; }
            seccion_fuentes_iniciales() { return 1; }
            seccion_salud() { echo "SALUD EJECUTADA (error)"; }
            seccion_cierre() { echo cierre; }
            principal antes instalacion fuentes_iniciales salud; echo "rc=$?"
        """, tmp_path)
        assert "SALUD EJECUTADA" not in r.stdout and "rc=1" in r.stdout and "X-02" in r.stdout

    def test_si_falla_la_instalacion_no_se_mide_el_resto(self, tmp_path):
        r = _ejecutar("""
            seccion_antes() { :; }
            seccion_instalacion() { fail I-01 "RC=1"; }
            seccion_fuentes_iniciales() { echo "FUENTES (error)"; }
            seccion_originales() { echo "originales comparados"; }
            seccion_cierre() { echo cierre; }
            principal antes instalacion fuentes_iniciales; echo "rc=$?"
        """, tmp_path)
        assert "FUENTES (error)" not in r.stdout and "originales comparados" in r.stdout and "rc=1" in r.stdout

    def test_controles_positivos_fallidos_no_permiten_interpretar_denegaciones(self, tmp_path):
        r = _ejecutar("""
            ENVF=/no/existe; REPO=/no/existe; SVC=nadie1; OTRO=nadie2
            como() { return 1; }          # ni el servicio ni el ordinario pueden leer/crear nada: controles positivos en FAIL
            negar() { echo "NEGAR EJECUTADO (error)"; }
            seccion_identidades; echo "rc=$?"
        """, tmp_path)
        assert "NEGAR EJECUTADO" not in r.stdout and "rc=2" in r.stdout and "C-13" in r.stdout

    def test_una_denegacion_que_falla_es_parada_de_seguridad_con_codigo_3(self, tmp_path):
        env = tmp_path / "falso.env"
        env.write_text("DB_PASSWORD=sintetica\n")
        r = _ejecutar(f"""
            ENVF="{env}"; REPO=/etc; SVC=nadie1; OTRO=nadie2
            como() {{ return 0; }}          # TODO tiene éxito: los controles pasan Y los intentos de acceso también
            ( seccion_identidades ); echo "rc=$?"
        """, tmp_path)
        assert "PARADA DE SEGURIDAD" in r.stdout and "rc=3" in r.stdout


class TestOrdenesDelGuion:

    def test_docker_exec_mantiene_abierta_la_entrada_estandar(self, tmp_path):
        """`docker exec` sin -i no entrega el programa del heredoc: F-03 no ejecutaría nada. El doble solo responde si recibe -i."""
        d = tmp_path / "bin"
        d.mkdir()
        (d / "docker").write_text('#!/bin/bash\nif [[ " $* " == *" -i "* ]]; then cat >/dev/null; printf "prowlarr_enabled=False\\ntransmission_enabled=False\\namule_enabled=False\\nforum_enabled=False\\n"; fi\n')
        (d / "docker").chmod(0o755)
        r = _ejecutar("integraciones_efectivas", tmp_path, env={"PATH": f"{d}:{os.environ['PATH']}"})
        assert r.stdout.count("=False") == 4, r.stdout + r.stderr

    def test_no_quedan_las_ordenes_que_no_funcionan_en_debian(self):
        for f in (EJECUTAR, ANFITRION, PREPARAR, LIB):
            texto = "\n".join(linea for linea in f.read_text().splitlines() if not linea.lstrip().startswith("#"))   # sin comentarios
            assert "stat -c %U -h" not in texto and "stat -h" not in texto, f"{f.name}: `stat -h` no existe"
            assert "pgrep -x qemu" not in texto, f"{f.name}: `pgrep -x` con un nombre de 18 caracteres no casa nunca"
            assert "|| true\n    vigilar_espacio" not in texto

    def test_runtime_settings_solo_exporta_los_cuatro_flags(self):
        texto = EJECUTAR.read_text()
        assert "jsonb_pretty" not in texto and "- 'secret_key'" not in texto, "se volcaría la configuración de runtime entera"
        assert "comicvine_enabled" in texto and "concat_ws" in texto

    def test_f10_no_es_pass_incondicional(self):
        texto = EJECUTAR.read_text()
        assert "grep -q '^PASS A-10'" in texto, "F-10 debe depender de que A-10 se haya comprobado"

    def test_el_limite_de_tiempo_se_aplica_dentro_de_la_vm(self):
        texto = ANFITRION.read_text()
        assert texto.count("sudo timeout --kill-after=30") == 2, "preparar y ejecutar deben llevar `timeout` remoto, no solo en el cliente SSH"
        assert "wait $!" in texto, "el comando remoto va en segundo plano para que el `trap` se atienda al momento"

    def test_la_construccion_va_bajo_el_limite_de_descarga(self):
        texto = PREPARAR.read_text()
        assert "con_limite_de_descarga" in texto and "docker build" in texto
        assert "MB" not in texto.replace("MiB", "").replace("MIB", ""), "unidades: MiB, no MB"


# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# 2.ª devolución de #242
# ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════════

# ── El corte termina el GRUPO entero, no solo el líder ───────────────────────────────────────────────────────────────

class TestElCorteTerminaElGrupoEntero:
    """Que el líder muera con TERM no prueba que haya terminado el grupo: un hijo que ignora TERM seguía vivo y no se enviaba el KILL."""

    CONTADOR = """
        C="{c}"; printf %s $((95 * 1048576)) > "$C"
        contador_rx_bytes() {{ cat "$C"; }}
        export RX_BASE_BYTES=0
    """

    def test_lider_muere_con_term_y_un_hijo_lo_ignora(self, tmp_path):
        hijo = tmp_path / "hijo.pid"
        r = _lib(self.CONTADOR.format(c=tmp_path / "rx") + f"""
            ORDEN='bash -c "trap \\"\\" TERM; echo \\$\\$ > {hijo}; while :; do sleep 0.2; done" & while [ ! -s {hijo} ]; do sleep 0.1; done; wait'
            ESPERA_TERM_S=1 INTERVALO_S=0.1 con_limite_de_descarga 100 20 -- bash -c "$ORDEN"
            echo "rc=$?"
        """, timeout=40)
        assert "rc=4" in r.stdout, r.stdout + r.stderr
        assert hijo.exists(), "el hijo que ignora TERM no llegó a arrancar: la prueba no demuestra nada"
        assert not _vivo(int(hijo.read_text())), "el hijo que ignora TERM sigue vivo tras el corte"
        pid_hijo = int(hijo.read_text())
        assert _esperar(lambda: not _vivo(pid_hijo))

    def test_si_algun_miembro_sobrevive_se_devuelve_5_y_no_4(self, tmp_path):
        hijo = tmp_path / "hijo.pid"
        r = _lib(self.CONTADOR.format(c=tmp_path / "rx") + f"""
            kill() {{ :; }}            # nada se puede matar: el grupo sigue vivo
            ORDEN='exec >/dev/null 2>&1 </dev/null; sleep 33.7 & echo $! > {hijo}; wait'      # sin tuberías abiertas: el test no espera al huérfano
            ESPERA_TERM_S=1 ESPERA_KILL_S=1 INTERVALO_S=0.1 con_limite_de_descarga 100 20 -- bash -c "$ORDEN"
            echo "rc=$?"
        """, timeout=40)
        try:
            assert "rc=5" in r.stdout and "siguen vivos miembros del grupo" in r.stderr, r.stdout + r.stderr
        finally:
            if hijo.exists():
                with contextlib.suppress(ProcessLookupError):
                    os.kill(int(hijo.read_text()), signal.SIGKILL)

    def test_la_red_se_corta_antes_de_matar_el_grupo(self, tmp_path):
        orden = tmp_path / "orden.txt"
        r = _lib(self.CONTADOR.format(c=tmp_path / "rx") + f"""
            cortar_red() {{ echo "CORTAR_RED" >> {orden}; }}
            kill() {{ echo "KILL $*" >> {orden}; command kill "$@"; }}
            INTERVALO_S=0.1 con_limite_de_descarga 100 20 -- bash -c 'sleep 33.9 & wait'
            echo "rc=$?"
        """, timeout=40)
        lineas = orden.read_text().splitlines()
        assert lineas[0] == "CORTAR_RED" and any(x.startswith("KILL") for x in lineas[1:]), (lineas, r.stderr)

    def test_miembros_vivos_del_grupo_ve_a_todos_y_no_cuenta_zombis(self):
        # Un grupo con líder y dos hijos (uno de ellos en otra rama): se ven los tres.
        p = subprocess.Popen(["setsid", "bash", "-c", "sleep 31.1 & sleep 31.2 & wait"])
        time.sleep(0.7)
        try:
            vivos = _lib(f"miembros_vivos_del_grupo {p.pid}").stdout.split()
            assert len(vivos) == 3, vivos
        finally:
            _lib(f"kill -KILL -- -{p.pid}")
            p.wait()


# ── Tope de red en el núcleo ────────────────────────────────────────────────────────────────────────────────────────

class TestTopeDeRedEnElNucleo:

    def test_las_reglas_cargadas_son_las_esperadas(self, tmp_path):
        r = _lib(f"""
            nft() {{ if [[ "$1" == "-f" ]]; then cat > "{tmp_path}/reglas.nft"; else echo 'iifname "ens3" quota over 588 mbytes drop'; fi; }}
            instalar_tope_de_red 600 ens3; echo "rc=$?"
        """)
        reglas = (tmp_path / "reglas.nft").read_text()
        assert "rc=0" in r.stdout, r.stdout + r.stderr
        assert "hook prerouting" in reglas, "debe ver también el tráfico reenviado a los contenedores de la construcción (prerouting)"
        assert 'iifname "ens3" tcp dport 22 accept' in reglas and reglas.index("dport 22 accept") < reglas.index("quota over")
        assert "quota over 588 mbytes drop" in reglas, "la cuota debe ser el 98 % del tope (600 → 588)"

    def test_cortar_red_añade_un_drop_total_detras_de_la_excepcion_del_ssh(self, tmp_path):
        r = _lib(f"""nft() {{ echo "$*" >> "{tmp_path}/nft.txt"; }}
            cortar_red_nft ens3""")
        assert (tmp_path / "nft.txt").read_text().strip() == 'add rule inet f1bis entrada iifname ens3 drop', r.stderr

    def test_si_no_se_puede_cargar_el_tope_la_preparacion_no_descarga(self):
        texto = PREPARAR.read_text()
        i = texto.index("instalar_tope_de_red")
        assert i < texto.index("docker build"), "el tope se instala ANTES de construir"
        assert "NO se pudo instalar el tope de red en el núcleo" in texto and "exit 4" in texto[i:i + 400]


NETNS_SCRIPT = """
set -e
LIB="$1"; source "$LIB"
ip link set lo up
instalar_tope_de_red 5 veth0 >/dev/null              # cuota = 98 % de 5 MiB → 4 MiB
unshare -n sleep 60 & B=$!
sleep 0.5
ip link add veth0 type veth peer name veth1
ip link set veth1 netns $B
ip addr add 10.9.0.1/24 dev veth0; ip link set veth0 up
nsenter -t $B -n bash -c 'ip link set lo up; ip addr add 10.9.0.2/24 dev veth1; ip link set veth1 up'
recibir() {  # recibir PUERTO ENVIAR_MIB → imprime los MiB recibidos
python3 - "$1" "$2" <<'PY' &
import socket, sys
puerto = int(sys.argv[1])
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(("10.9.0.1", puerto)); s.listen(1)
s.settimeout(8)
try:
    c, _ = s.accept()
except Exception:
    print("RECIBIDO_MIB 0.0"); sys.exit()
total = 0; c.settimeout(3)
try:
    while True:
        d = c.recv(65536)
        if not d: break
        total += len(d)
except Exception: pass
print("RECIBIDO_MIB", round(total / 1048576, 2))
PY
RP=$!
sleep 0.4
nsenter -t $B -n python3 - "$1" "$2" <<'PY' || true
import socket, sys
s = socket.socket(); s.settimeout(4)
try:
    s.connect(("10.9.0.1", int(sys.argv[1])))
    for _ in range(int(sys.argv[2])): s.sendall(b"x" * 1048576)
except Exception: pass
PY
wait $RP
}
echo "A $(recibir 5000 30)"
cortar_red_nft veth0
echo "B $(recibir 5001 3)"
echo "C $(recibir 22 3)"
kill $B 2>/dev/null || true
"""


def _netns_disponible() -> bool:
    if shutil.which("unshare") is None or shutil.which("nft") is None or shutil.which("ip") is None or shutil.which("nsenter") is None:
        return False
    r = subprocess.run(["unshare", "-Urn", "bash", "-c", "ip link add t0 type dummy && nft list ruleset >/dev/null"],
                       capture_output=True, timeout=20, check=False)
    return r.returncode == 0


@pytest.mark.skipif(not _netns_disponible(), reason="NO EJECUTADA: requiere espacios de nombres de usuario y de red sin privilegios, nft, ip y nsenter")
class TestTopeDeRedFuncional:
    """Con el núcleo de verdad (un espacio de nombres de red con un par veth): el tope y el corte son reales, no un doble."""

    def test_la_cuota_descarta_lo_que_pasa_del_tope_el_corte_lo_descarta_todo_y_el_ssh_pasa(self, tmp_path):
        s = tmp_path / "netns.sh"
        s.write_text(NETNS_SCRIPT)
        r = subprocess.run(["unshare", "-Urn", "bash", str(s), str(LIB)], capture_output=True, text=True, timeout=90, check=False)
        salida = {linea.split()[0]: float(linea.split()[-1]) for linea in r.stdout.splitlines() if linea[:2] in ("A ", "B ", "C ")}
        assert set(salida) == {"A", "B", "C"}, r.stdout + r.stderr
        assert 3.5 <= salida["A"] <= 4.2, f"con tope 5 MiB (cuota 4 MiB) se recibieron {salida['A']} MiB de 30 enviados"
        assert salida["B"] == 0.0, f"con la red cortada se recibieron {salida['B']} MiB"
        assert salida["C"] >= 2.9, f"el SSH (puerto 22) debía pasar siempre y recibió {salida['C']} MiB de 3"


# ── Plazo único de la fase ──────────────────────────────────────────────────────────────────────────────────────────

RELOJ = """
RELOJ="${DIR}/reloj.txt"; printf 1000000 > "${RELOJ}"
ahora() { cat "${RELOJ}"; }
avanzar() { printf %s $(( $(cat "${RELOJ}") + $1 )) > "${RELOJ}"; }
"""


class TestPlazoUnicoDeLaFase:

    def _correr(self, dir_ensayo, tmp_path, *, extra: str, prep: str = PREP_BIEN):
        guion, env = _doble_anfitrion(dir_ensayo, tmp_path, prep=prep, extra=RELOJ + extra)
        return _bash(guion, env=env, timeout=60)

    def _estado(self, dir_ensayo):
        crono = (dir_ensayo / "cronologia.txt").read_text() if (dir_ensayo / "cronologia.txt").exists() else ""
        parada = (dir_ensayo / ".parada").read_text() if (dir_ensayo / ".parada").exists() else ""
        return crono, parada

    def test_tope_de_paso_usa_el_tiempo_restante_menos_la_reserva(self, dir_ensayo, tmp_path):
        guion, env = _doble_anfitrion(dir_ensayo, tmp_path, prep=PREP_BIEN, orden="""
            DIR="${DIR}"; mkdir -p "$DIR"; cronologia() { :; }
            """ + RELOJ + """
            iniciar_plazo 45                      # 2700 s
            echo "a=$(tope_de_paso 120)"          # sobra: 120
            avanzar 2500; echo "b=$(tope_de_paso 120)"   # restan 200 ≤ reserva 300 → 0
            printf 1000000 > "$RELOJ"; iniciar_plazo 45; avanzar 2350; echo "c=$(tope_de_paso 120)"   # restan 350 − 300 = 50
        """)
        r = _bash(guion, env=env)
        assert "a=120" in r.stdout and "b=0" in r.stdout and "c=50" in r.stdout, r.stdout + r.stderr

    def test_un_arranque_lento_impide_el_siguiente_paso_y_se_limpia(self, dir_ensayo, tmp_path):
        r = self._correr(dir_ensayo, tmp_path, extra='''
            arrancar() { python3 "''' + str(FALSA) + '''" "${PIDFILE}" "${DIR}"; avanzar 2600; }       # el arranque se come el plazo
            ssh_remoto() { echo "ORDEN_REMOTA $*" >> "${DIR}/remoto.txt"; }
            scp_vm() { echo "SCP $*" >> "${DIR}/scp.txt"; return 0; }
        ''')
        crono, parada = self._estado(dir_ensayo)
        assert r.returncode != 0
        assert "plazo agotado" in parada and "PLAZO AGOTADO" in crono, (crono, parada, r.stderr)
        assert "copiar el bundle" in parada, "debe pararse en el PRIMER paso que ya no tiene tiempo, no en uno posterior"
        assert not (dir_ensayo / "scp.txt").exists(), "se copió algo con el plazo agotado"
        assert not (dir_ensayo / "remoto.txt").exists(), "se lanzó una orden remota con el plazo agotado"
        assert not (dir_ensayo / "preparacion.ok").exists()
        pid = dir_ensayo / "qemu.pid"
        assert not pid.exists() or not _vivo(int(pid.read_text())), "la VM quedó viva"

    def test_una_copia_lenta_impide_lo_que_sigue(self, dir_ensayo, tmp_path):
        r = self._correr(dir_ensayo, tmp_path, extra='''
            scp_vm() { echo "SCP $*" >> "${DIR}/scp.txt"; avanzar 2500; return 0; }                   # la primera copia agota el plazo
            ssh_remoto() { echo "ORDEN_REMOTA $*" >> "${DIR}/remoto.txt"; }
        ''')
        crono, parada = self._estado(dir_ensayo)
        assert r.returncode != 0 and "plazo agotado" in parada, (crono, parada, r.stderr)
        assert (dir_ensayo / "scp.txt").read_text().count("SCP") == 1, "se hizo otra copia con el plazo agotado"
        assert not (dir_ensayo / "remoto.txt").exists()

    def test_la_espera_de_ssh_la_corta_el_plazo_y_no_el_numero_de_intentos(self, dir_ensayo, tmp_path):
        guion, env = _doble_anfitrion(dir_ensayo, tmp_path, prep=PREP_BIEN, orden="""
            DIR="${DIR}"; mkdir -p "$DIR"; cronologia() { :; }
            """ + RELOJ + """
            ssh_remoto() { echo x >> "${DIR}/intentos.txt"; avanzar 100; return 1; }
            esperar_ssh() { local i; for i in $(seq 1 "${INTENTOS_SSH:-60}"); do (( $(restante) > RESERVA_CIERRE_S )) || return 1; ssh_remoto 15 true 2>/dev/null && return 0; sleep "${PAUSA_SSH_S:-4}"; done; return 1; }
            iniciar_plazo 45
            esperar_ssh; echo "rc=$?"
        """)
        # La prueba usa la MISMA definición de esperar_ssh que el script real: se comprueba que el texto coincide.
        real = ANFITRION.read_text()
        assert "(( $(restante) > RESERVA_CIERRE_S )) || return 1" in real
        r = _bash(guion, env={**env, "PAUSA_SSH_S": "0"})
        intentos = (dir_ensayo / "intentos.txt").read_text().count("x")
        assert "rc=1" in r.stdout and intentos < 60 and 20 <= intentos <= 25, (intentos, r.stdout, r.stderr)

    def test_la_espera_real_de_ssh_se_corta_por_plazo(self, dir_ensayo, tmp_path):
        """La función REAL de anfitrion.sh (no una copia) con un ssh que siempre falla y un reloj que avanza 100 s por intento."""
        guion, env = _doble_anfitrion(dir_ensayo, tmp_path, prep=PREP_BIEN, orden="""
            mkdir -p "$DIR"; cronologia() { :; }
            ssh_remoto() { echo x >> "${DIR}/intentos.txt"; avanzar 100; return 1; }
            unset -f esperar_ssh; source "$ANFITRION_SRC" 2>/dev/null || true
            iniciar_plazo 45
            esperar_ssh; echo "rc=$?"
        """, extra=RELOJ)
        # `source` del anfitrión redefine las funciones (incluidos los dobles): se vuelven a poner después.
        guion = guion.replace('unset -f esperar_ssh; source "$ANFITRION_SRC" 2>/dev/null || true', "")
        guion = guion.replace("        esperar_ssh() { return 0; }\n", "")                    # quita el doble: se usa la función real
        r = _bash(guion, env={**env, "PAUSA_SSH_S": "0"})
        intentos = (dir_ensayo / "intentos.txt").read_text().count("x")
        assert "rc=1" in r.stdout and 20 <= intentos <= 25, (intentos, r.stdout, r.stderr)

    def test_el_limite_de_la_orden_remota_es_lo_que_queda_menos_la_reserva(self, dir_ensayo, tmp_path):
        r = self._correr(dir_ensayo, tmp_path, extra='''
            scp_vm() { avanzar 100; return 0; }                                                          # 100 s ya gastados
            ssh_remoto() { local seg=$1; shift
                case "$*" in *vm-preparar.sh*) echo "CLIENTE=${seg} ORDEN=$*" >> "${DIR}/remoto.txt"; echo "PREPARACIÓN TERMINADA";; esac; }
        ''')
        assert r.returncode == 0, r.stdout + r.stderr
        linea = (dir_ensayo / "remoto.txt").read_text()
        import re
        interno = int(re.search(r"timeout --kill-after=30 (\d+)", linea).group(1))
        cliente = int(re.search(r"CLIENTE=(\d+)", linea).group(1))
        # 2700 s de fase − 300 s de reserva − 300 s gastados por los tres scp (100 cada uno) = 2100 s; menos los 30 s de kill-after
        assert interno <= 2700 - 300 - 300 - 30, interno
        assert cliente == interno + 30 + 60, (cliente, interno)

    def test_la_ejecucion_tambien_respeta_el_plazo(self, dir_ensayo, tmp_path):
        prep = dir_ensayo / "f1bis-prep.qcow2"
        prep.write_text("overlay")
        _, env = _doble_anfitrion(dir_ensayo, tmp_path, prep=PREP_BIEN)
        (dir_ensayo / "preparacion.ok").write_text(
            f"CANDIDATO={env['CANDIDATO']}\nRC=0\nPREP_BYTES={prep.stat().st_size}\nPREP_MTIME={int(prep.stat().st_mtime)}\n")
        guion, env = _doble_anfitrion(dir_ensayo, tmp_path, prep=PREP_BIEN, orden="cmd_ejecutar", extra=RELOJ + '''
            arrancar() { python3 "''' + str(FALSA) + '''" "${PIDFILE}" "${DIR}"; avanzar 3500; }
            ssh_remoto() { echo "ORDEN_REMOTA" >> "${DIR}/remoto.txt"; }
        ''')
        r = _bash(guion, env=env, timeout=60)
        assert r.returncode != 0 and not (dir_ensayo / "remoto.txt").exists()
        assert "plazo agotado" in (dir_ensayo / ".parada").read_text()
        pid = dir_ensayo / "qemu.pid"
        assert not pid.exists() or not _vivo(int(pid.read_text()))
