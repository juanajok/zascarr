#!/usr/bin/env python3
# ruff: noqa: E501
"""Simulación de un Android de gama baja con Chrome (U16, #203): perfil EMULADO, no un teléfono.

Reutiliza `MEDIR`/`resumir` de `medir_u16.py` y `Navegador` de `../ui-baseline/capturar.py`. Sobre el ensayo aislado (contenedores Debian 12
«bookworm» en x86-64: la misma base que la imagen de la Pi, pero NO una Pi ni arm64) aplica a Chrome de escritorio un perfil de móvil
Android modesto: agente de usuario de Chrome para Android, pantalla táctil con densidad 2×, CPU 4× más lenta y red de ~1,6 Mbit/s con 150 ms.
Por cada pantalla y ancho mide **lo mismo** que `medir_u16.py` (desborde lateral, fuente calculada de los campos y alto de los controles).
(Una prueba de «toque» —comprobar con `elementFromPoint` que nada tapa un control— se probó y se **descartó**: devolvía `null` con la CPU
ralentizada por llevar el control a pantalla antes de que terminara el desplazamiento; no la publico porque no es fiable.)

    python3 docs/design/ui-u16/simular_android_u16.py http://127.0.0.1:18000 docs/design/ui-u16 SHA_DESPLEGADO

Limitaciones que NO se pueden saltar: Chrome emulado no es Chrome en un teléfono (motor de entrada, teclado, rendimiento y fuentes reales
cambian) y esto no dice nada de Safari en iOS (WebKit, no instalado aquí). No sustituye a la ronda en dispositivos reales.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent


def _cargar(nombre: str, ruta: Path):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


capturar = _cargar("capturar", AQUI.parent / "ui-baseline" / "capturar.py")
medir = _cargar("medir_u16", AQUI / "medir_u16.py")

#: (ancho, alto): los tres anchos de la tarjeta con alturas habituales de Android modesto.
PANTALLAS_ANDROID = [(360, 640), (390, 780), (414, 736)]
MODELO = "SM-A105F"          # Samsung Galaxy A10 (Android 9/10): solo el texto del agente de usuario, no el aparato

async def perfil(nav, ancho: int, alto: int, version: str) -> None:
    ua = f"Mozilla/5.0 (Linux; Android 10; {MODELO}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} Mobile Safari/537.36"
    await nav.cdp("Emulation.setUserAgentOverride", userAgent=ua, platform="Linux armv8l", acceptLanguage="es-ES,es")
    await nav.cdp("Emulation.setDeviceMetricsOverride", width=ancho, height=alto, deviceScaleFactor=2, mobile=True)
    await nav.cdp("Emulation.setTouchEmulationEnabled", enabled=True, maxTouchPoints=5)
    await nav.cdp("Emulation.setCPUThrottlingRate", rate=4)
    await nav.cdp("Network.emulateNetworkConditions", offline=False, latency=150, downloadThroughput=200_000, uploadThroughput=100_000)
    await nav.cdp("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "light"}, {"name": "pointer", "value": "coarse"}])


async def main(base: str, salida: Path, sha: str) -> None:
    nav = capturar.Navegador()
    res: dict = {"simulado": True, "sha_desplegado_en_el_ensayo": sha, "perfil": {"modelo_en_el_agente": MODELO, "cpu": "4x más lenta", "red": "1,6 Mbit/s, 150 ms",
                 "densidad": 2, "pantallas": PANTALLAS_ANDROID}, "pantallas": {}}
    try:
        await nav.abrir()
        await capturar.comprobar_entorno(nav, base, "principal")
        res["chrome_del_navegador"] = nav.version.get("Browser")
        version = res["chrome_del_navegador"].split("/")[-1]
        capturar.post_form(base, "/ui/legal/accept", {"acepto_1": "on", "acepto_2": "on", "acepto_3": "on"})
        await nav.vista({"nombre": "e", "w": 1280, "h": 900, "movil": False}, "light")
        await nav.ir(base + "/ui/biblioteca", espera=0.5)
        ficha = await nav.js("(() => { const a=[...document.querySelectorAll('a[href^=\"/ui/series/\"]')].find(x=>x.textContent.includes('Guardianes')); return a? a.getAttribute('href'):null })()")
        sid = ficha.rsplit("/", 1)[-1] if ficha else ""
        pantallas = [
            ("panel", "/ui/"), ("biblioteca", "/ui/biblioteca"), ("ficha-de-serie", ficha or "/ui/biblioteca"), ("descubrir", "/ui/descubrir"),
            ("por-revisar", "/ui/pendientes"), ("pendientes-por-carpeta", "/ui/pendientes/carpetas"),
            ("asistente-de-carpeta", "/ui/pendientes/carpetas/asistente?clave=_Unsorted"),
            ("revision-de-la-vinculacion", f"/ui/pendientes/carpetas/asistente/vinculacion?clave=_Unsorted&series_id={sid}"),
            ("deseados", "/ui/wishlist"), ("mi-biblioteca-auditoria", "/ui/auditoria"), ("ajustes", "/ui/ajustes"),
            ("estado", "/estado"), ("aviso-legal-asistente", "/ui/legal"), ("aviso-legal-texto", "/legal"),
        ]
        for nombre, ruta in pantallas:
            res["pantallas"][nombre] = {"ruta": ruta, "anchos": {}}
            for w, h in PANTALLAS_ANDROID:
                await perfil(nav, w, h, version)
                await nav.ir(base + ruta, espera=2.5 if nombre == "estado" else 1.8)
                m = medir.resumir(await nav.js(medir.MEDIR))
                m["agente"] = (await nav.js("navigator.userAgent"))[:90]
                m["pointer_coarse"] = await nav.js("matchMedia('(pointer: coarse)').matches")
                res["pantallas"][nombre]["anchos"][str(w)] = m
    finally:
        await nav.cdp("Emulation.setCPUThrottlingRate", rate=1)
        await nav.cerrar()
    (salida / "simulacion-android.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{'pantalla':32} {'ancho':>5} {'lateral':>8} {'<16px':>6} {'<24px':>6} {'<44px':>6}")
    for n, d in res["pantallas"].items():
        for w, r in d["anchos"].items():
            print(f"{n:32} {w:>5} {'SÍ' if r['desborda_en_horizontal'] else 'no':>8} {len(r['campos_menores_de_16px']):>6} {len(r['objetivos_menores_de_24px']):>6} "
                  f"{len(r['controles_menores_de_44px']):>6}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1].rstrip("/"), Path(sys.argv[2]), sys.argv[3]))
