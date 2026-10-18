# ruff: noqa: E501
"""La ubicación del `.env` tiene que ser de fiar de punta a punta (C5).

Un `.env` en 600 `root:root` no está a salvo si OTRA cuenta puede borrarlo y poner otro, o cambiar un componente de su
ruta: el permiso de unlink/rename lo da la CARPETA que contiene la entrada, no el fichero. Por eso se recorre cada
componente de la ruta LÓGICA (no la física: resolverla de golpe pierde los enlaces intermedios, y un enlace en una
carpeta que otro puede escribir se puede reapuntar); cada carpeta ha de ser de root y no admitir escritura de grupo ni
de otros (el bit pegajoso vale en las intermedias: nadie puede renombrar lo que no es suyo), y un enlace solo se admite
si es de root, está en una carpeta de fiar y su destino también lo es.

Aquí, en bash de verdad y sobre un árbol sintético, sin ser root. Quien «es de fiar» se parametriza
(`_CRED_UIDS_CONFIABLES`, por defecto solo root) para poder probarlo con las cuentas de la máquina de pruebas, y el recorrido
se corta en la carpeta temporal de pytest (`CRED_CONFIAR_DESDE`): lo que hay por encima es de la máquina, no del código.
Que el instalador real corta de verdad lo miden los escenarios de `test_credenciales_aisladas.py` como root.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="requiere bash")

LIB = Path(__file__).resolve().parents[1] / "scripts" / "_credenciales.sh"


def _bash(cuerpo: str, base: Path, *, confiables: str | None = None, cwd: Path | None = None,
          entorno: dict[str, str] | None = None):
    confiables = confiables if confiables is not None else str(os.getuid())
    guion = (
        'set -uo pipefail\nwarn() { echo "AVISO: $*" >&2; }\n'
        f'source "{LIB}"\n_CRED_UIDS_CONFIABLES="{confiables}"\nCRED_CONFIAR_DESDE="{base}"\n{cuerpo}\n'
    )
    return subprocess.run(["bash", "-c", guion], capture_output=True, text=True, timeout=30, check=False, cwd=cwd,
                          env={**os.environ, **(entorno or {})})


@pytest.fixture
def base(tmp_path: Path) -> Path:
    """Carpeta base de la prueba (700, mía): lo de por encima no se examina."""
    b = tmp_path / "base"
    b.mkdir(mode=0o700)
    return b


def _raiz(base: Path, *partes: str, modo: int = 0o755) -> Path:
    ruta = base.joinpath(*partes)
    ruta.mkdir(parents=True, exist_ok=True)
    for p in [ruta, *[q for q in ruta.parents if base in q.parents or q == base]]:
        if p != base:
            p.chmod(modo)
    (ruta / ".env").write_text("DB_PASSWORD=x\n", encoding="utf-8")
    (ruta / ".env").chmod(0o600)
    return ruta


def _veredicto(base: Path, env: Path, **kw):
    r = _bash(f'ubicacion_insegura "{env}"; echo "RC=$?"', base, **kw)
    motivo = r.stdout.replace(f"RC={r.stdout.strip().rsplit('RC=', 1)[-1]}", "").strip()
    return r.stdout.strip().rsplit("RC=", 1)[-1], motivo


def test_una_ubicacion_de_fiar_es_segura(base):
    env = _raiz(base, "opt", "zascarr") / ".env"
    rc, motivo = _veredicto(base, env)
    assert rc == "1" and motivo == "", motivo


@pytest.mark.parametrize("modo", [0o775, 0o757, 0o777, 0o722])
def test_la_carpeta_del_env_escribible_por_otros_es_insegura(base, modo):
    raiz = _raiz(base, "opt", "zascarr")
    raiz.chmod(modo)
    rc, motivo = _veredicto(base, raiz / ".env")
    assert rc == "0" and "escrib" in motivo and str(raiz) in motivo


def test_la_carpeta_del_env_con_bit_pegajoso_sigue_siendo_insegura(base):
    """El bit pegajoso protege entradas AJENAS en una carpeta compartida (como /tmp); aquí la entrada es el `.env`
    y la carpeta es la suya: no se admite escritura de otros."""
    raiz = _raiz(base, "opt", "zascarr")
    raiz.chmod(0o1777)
    assert _veredicto(base, raiz / ".env")[0] == "0"


def test_la_carpeta_de_otra_cuenta_es_insegura(base):
    """El caso medido: `/opt/zascarr` era de `media`. Aquí «de fiar» es solo root, y las carpetas son mías."""
    env = _raiz(base, "opt", "zascarr") / ".env"
    rc, motivo = _veredicto(base, env, confiables="0")
    assert rc == "0" and "propiedad" in motivo


def test_un_antecesor_escribible_por_otros_es_inseguro(base):
    env = _raiz(base, "pub", "zascarr") / ".env"
    (base / "pub").chmod(0o777)
    rc, motivo = _veredicto(base, env)
    assert rc == "0" and str(base / "pub") in motivo


def test_un_antecesor_con_bit_pegajoso_es_aceptable(base):
    env = _raiz(base, "tmpx", "zascarr") / ".env"
    (base / "tmpx").chmod(0o1777)
    assert _veredicto(base, env)[0] == "1"


def test_un_antecesor_de_otra_cuenta_es_inseguro(base):
    """Su dueño puede renombrar `zascarr` y poner otra carpeta en su lugar (el caso de un home)."""
    env = _raiz(base, "home", "ana", "zascarr") / ".env"
    rc, motivo = _veredicto(base, env, confiables="0")
    assert rc == "0" and "propiedad" in motivo


def test_el_env_como_enlace_simbolico_es_inseguro(base):
    raiz = _raiz(base, "opt", "zascarr")
    real = base / "otro.env"
    real.write_text("DB_PASSWORD=x\n", encoding="utf-8")
    (raiz / ".env").unlink()
    (raiz / ".env").symlink_to(real)
    rc, motivo = _veredicto(base, raiz / ".env")
    assert rc == "0" and "enlace" in motivo


def test_un_enlace_en_una_carpeta_que_otro_puede_escribir_es_inseguro_aunque_apunte_a_un_destino_seguro(base):
    """El hueco de validar solo la ruta FÍSICA: `…/atajo → …/real` resuelve a una ruta limpia, pero quien puede escribir
    en la carpeta del enlace lo reapunta cuando quiera."""
    real = _raiz(base, "real", "zascarr")
    publica = base / "publica"
    publica.mkdir()
    publica.chmod(0o777)
    (publica / "atajo").symlink_to(real.parent)
    rc, motivo = _veredicto(base, publica / "atajo" / "zascarr" / ".env")
    assert rc == "0" and ("abierto" in motivo or "escrib" in motivo)


def test_un_enlace_de_una_cuenta_que_no_es_de_fiar_es_inseguro_aunque_su_carpeta_este_cerrada(base):
    real = _raiz(base, "real", "zascarr")
    carpeta = base / "enlaces"
    carpeta.mkdir(mode=0o755)
    (carpeta / "atajo").symlink_to(real.parent)
    rc, motivo = _veredicto(base, carpeta / "atajo" / "zascarr" / ".env", confiables="0")
    assert rc == "0" and "propiedad" in motivo


def test_un_enlace_de_fiar_a_un_destino_de_fiar_es_seguro(base):
    """Como `/opt → /mnt/disco/opt`: legítimo si el enlace, su carpeta y su destino son de fiar."""
    real = _raiz(base, "real", "zascarr")
    carpeta = base / "enlaces"
    carpeta.mkdir(mode=0o755)
    (carpeta / "atajo").symlink_to(real.parent)
    rc, motivo = _veredicto(base, carpeta / "atajo" / "zascarr" / ".env")
    assert rc == "1", motivo


def test_un_enlace_de_fiar_cuyo_destino_no_es_de_fiar_es_inseguro(base):
    abierto = _raiz(base, "abierto", "zascarr")
    abierto.chmod(0o777)
    carpeta = base / "enlaces"
    carpeta.mkdir(mode=0o755)
    (carpeta / "atajo").symlink_to(abierto.parent)
    assert _veredicto(base, carpeta / "atajo" / "zascarr" / ".env")[0] == "0"


def test_un_enlace_relativo_se_resuelve_desde_su_carpeta(base):
    real = _raiz(base, "real", "zascarr")
    carpeta = base / "enlaces"
    carpeta.mkdir(mode=0o755)
    (carpeta / "atajo").symlink_to("../real")
    assert real.exists()
    assert _veredicto(base, carpeta / "atajo" / "zascarr" / ".env")[0] == "1"


def test_un_bucle_de_enlaces_es_inseguro_y_termina(base):
    carpeta = base / "enlaces"
    carpeta.mkdir(mode=0o755)
    (carpeta / "a").symlink_to(carpeta / "b")
    (carpeta / "b").symlink_to(carpeta / "a")
    rc, _ = _veredicto(base, carpeta / "a" / "zascarr" / ".env")
    assert rc == "0"


def test_los_puntos_punto_no_se_resuelven_en_silencio(base):
    """`../` puede saltarse un enlace que el recorrido sí miró: se rechaza en vez de interpretarlo."""
    raiz = _raiz(base, "opt", "zascarr")
    rc, motivo = _veredicto(base, raiz / ".." / "zascarr" / ".env")
    assert rc == "0" and ".." in motivo


def test_una_ruta_relativa_se_toma_desde_el_directorio_actual(base):
    raiz = _raiz(base, "opt", "zascarr")
    r = _bash('ubicacion_insegura ".env"; echo "RC=$?"', base, cwd=raiz)
    assert r.stdout.strip().endswith("RC=1")


def test_no_se_toca_nada(base):
    raiz = _raiz(base, "opt", "zascarr")
    raiz.chmod(0o777)
    antes = (oct(raiz.stat().st_mode), raiz.stat().st_uid, sorted(p.name for p in raiz.iterdir()))
    _veredicto(base, raiz / ".env")
    assert antes == (oct(raiz.stat().st_mode), raiz.stat().st_uid, sorted(p.name for p in raiz.iterdir()))


# ── Rutas con un salto de línea (C5: se examina el camino REALMENTE utilizado) ───────────────────────────────────────
# Separar con `tr '/' '\n'` convertía también los saltos de línea del nombre en separadores: `/base/uno<LF>dos/zascarr`
# se examinaba como `/base/uno/dos/zascarr`, y si esa segunda estructura existía y era segura, el antecesor real (abierto a
# la escritura) pasaba. La prueba monta LAS DOS estructuras: sin la segunda, pasaría simplemente porque no encuentra nada.

def _con_lf(base: Path, *, real_abierta: bool = True) -> tuple[Path, Path]:
    """→ (ruta real con LF, ruta alternativa segura que resulta de leer el LF como `/`)."""
    real_dir = base / "uno\ndos"
    real_dir.mkdir(mode=0o755)
    if real_abierta:
        real_dir.chmod(0o777)
    zas = real_dir / "zascarr"
    zas.mkdir(mode=0o755)
    (zas / ".env").write_text("DB_PASSWORD=x\n", encoding="utf-8")
    (zas / ".env").chmod(0o600)
    falsa = base / "uno" / "dos" / "zascarr"
    falsa.mkdir(parents=True, mode=0o755)
    (falsa / ".env").write_text("DB_PASSWORD=x\n", encoding="utf-8")
    (falsa / ".env").chmod(0o600)
    for d in (base / "uno", base / "uno" / "dos", falsa):
        d.chmod(0o755)
    return zas / ".env", falsa / ".env"


def _interno(base: Path, ruta: Path, estricto: int = 1):
    r = _bash('_cred_camino_inseguro "$RUTA" ' + str(estricto) + ' 0; echo "RC=$?"', base, entorno={"RUTA": str(ruta.parent)})
    cuerpo, _, rc = r.stdout.rpartition("RC=")
    return rc.strip(), cuerpo


def test_el_antecesor_real_con_lf_se_examina_y_no_su_homonimo_con_barra(base):
    real, falsa = _con_lf(base)
    assert real.exists() and falsa.exists()
    assert _interno(base, falsa)[0] == "1"                      # la alternativa es segura (control positivo)
    rc, motivo = _interno(base, real)
    assert rc == "0" and "escrib" in motivo and "uno\ndos" in motivo, (rc, motivo)


def test_un_lf_en_el_nombre_no_se_confunde_con_dos_componentes_aunque_todo_sea_seguro(base):
    """Control: con la estructura real segura, el comprobador la acepta (no rechaza por rechazar)."""
    real, falsa = _con_lf(base, real_abierta=False)
    assert _interno(base, real)[0] == "1" and _interno(base, falsa)[0] == "1"


def test_un_destino_de_enlace_con_lf_tambien_se_examina_entero(base):
    real, _ = _con_lf(base)
    carpeta = base / "enlaces"
    carpeta.mkdir(mode=0o755)
    (carpeta / "atajo").symlink_to(real.parent.parent)       # → …/uno<LF>dos
    r = _bash('_cred_camino_inseguro "$RUTA" 1 0; echo "RC=$?"', base,
              entorno={"RUTA": str(carpeta / "atajo" / "zascarr")})
    assert r.stdout.rpartition("RC=")[2].strip() == "0" and "escrib" in r.stdout


def test_un_destino_de_enlace_que_acaba_en_lf_no_pierde_el_salto_al_leerlo(base):
    """`$(readlink …)` quita los saltos de línea FINALES: el destino leído sería otra carpeta."""
    abierta = base / "dest\n"
    abierta.mkdir(mode=0o777)
    abierta.chmod(0o777)
    (abierta / "zascarr").mkdir(mode=0o755)
    segura = base / "dest"
    (segura / "zascarr").mkdir(parents=True, mode=0o755)
    segura.chmod(0o755)
    carpeta = base / "enlaces"
    carpeta.mkdir(mode=0o755)
    (carpeta / "atajo").symlink_to(str(abierta))
    r = _bash('_cred_camino_inseguro "$RUTA" 1 0; echo "RC=$?"', base, entorno={"RUTA": str(carpeta / "atajo" / "zascarr")})
    assert r.stdout.rpartition("RC=")[2].strip() == "0", r.stdout


def test_la_entrada_publica_rechaza_cualquier_ruta_con_lf_con_un_mensaje_claro(base):
    """Además de examinarlo bien, las funciones públicas lo rechazan: el resto del instalador captura rutas con `$(…)` (que
    recorta saltos de línea) y recorre listados línea a línea."""
    real, falsa = _con_lf(base, real_abierta=False)
    for env in (real, falsa.parent / "uno\n" / ".env"):
        r = _bash('ubicacion_insegura "$RUTA"; echo "RC=$?"', base, entorno={"RUTA": str(env)})
        if env == real:
            assert r.stdout.rpartition("RC=")[2].strip() == "0" and "salto de línea" in r.stdout, r.stdout
    r = _bash('ubicacion_insegura "$RUTA"; echo "RC=$?"', base, entorno={"RUTA": str(falsa)})
    assert r.stdout.strip().endswith("RC=1")                    # sin LF y segura: se acepta
