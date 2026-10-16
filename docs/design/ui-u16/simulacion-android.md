# Simulación suplementaria: perfil de Android modesto (emulado) — U16 (#203)

> **No forma parte del contrato de aceptación** de [`verificacion-u16.md`](verificacion-u16.md): se ejecutó para informar. **No es un teléfono
> ni una prueba de compatibilidad con Android real.** Resultado bruto: [`simulacion-android.json`](simulacion-android.json); herramienta:
> [`simular_android_u16.py`](simular_android_u16.py).

| Dato | Valor |
|---|---|
| Aplicación | Debian 12 (bookworm) en contenedor, x86-64, `main` `dc9841aec9f709dba1b7c0e9eb5d96f462cb9079`, PostgreSQL real con datos sintéticos |
| Navegador | Chrome 154.0.8037.92 del equipo del desarrollador (Ubuntu 26.04), **emulando** un Chrome para Android: agente de usuario (`Android 10; SM-A105F`; solo el texto, no el aparato), táctil con 5 puntos, `pointer: coarse`, densidad 2×, **CPU 4× más lenta**, red de ~1,6 Mbit/s con 150 ms |
| Pantallas | 360×640, 390×780 y 414×736 px (los tres anchos de la tarjeta, con alturas habituales de Android modesto) |
| Alcance | las mismas 14 pantallas × 3 anchos = 42 medidas, con la misma medición que `medir_u16.py` |

## Resultado

| Comprobación | Resultado |
|---|---|
| Sin desplazamiento horizontal | **PASS** — 0 de 42 |
| Campos con tamaño calculado ≥ 16 px | **PASS** — 0 por debajo, de 138 campos medidos |
| Controles ≥ 44 px y ninguno < 24 px | **PASS** — 0 por debajo en ambos casos |

Coincide con la medición sin perfil de Android (`medicion-despues.json`): era lo esperable, porque la hoja de estilos no distingue el agente de
usuario, sino el ancho y `pointer: coarse` (ambos emulados).

## Lo que esta simulación NO demuestra

- **Nada de un Android real:** motor de entrada táctil, teclado virtual, fuentes del sistema, rendimiento real y densidad real no se reproducen.
- **Nada de Safari/iOS** (WebKit no está instalado): el zoom al enfocar un campo no se ha observado; se sustituye por el tamaño calculado ≥ 16 px.
- **Una prueba de «toque»** (comprobar que nada tapa un control) se intentó y se **descartó**: devolvía `null` por llevar el control a pantalla
  antes de acabar el desplazamiento con la CPU ralentizada. No se publica porque no es fiable.
- Estados posteriores a una interacción y tema oscuro: no medidos.
