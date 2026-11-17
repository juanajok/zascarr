# Capturas actuales de la interfaz (V14, 2026-11-14)

> **Qué es.** La foto de la UI al cerrar la migración de la Épica V (V0–V14). Sustituye a las
> capturas por hito (`ui-v1` … `ui-v13`) como referencia de cómo se ve la app hoy.
> **No es una verificación de accesibilidad ni sustituye a la revisión en navegador real con lector
> de pantalla**: eso tiene su propia lista en `docs/design/ui-migracion.md`.

| | |
|---|---|
| **Fecha** | 2026-11-14 |
| **Código** | Pi de producción en `dbe39451` (merge de #775, V14 F4) |
| **Navegador** | Chrome headless 156, sin extensiones |
| **Temas** | Papel (claro) y Nocturno (oscuro, emulando `prefers-color-scheme: dark`) |
| **Tamaños** | Escritorio 1280×800 · Móvil 390×844 |
| **Datos** | Biblioteca real del PO (224 series, 667 pendientes); ninguna ruta ni nombre se inventó |

## Índice

| Archivo | Pantalla |
|---|---|
| `inicio--escritorio-1280x800-claro.png` | Inicio (panel de pasos y métricas) |
| `biblioteca--escritorio-1280x800-claro.png` | Biblioteca con la barra única (búsqueda, filtros, orden, vista) |
| `biblioteca--escritorio-1280x800-oscuro.png` | Biblioteca, tema nocturno |
| `biblioteca--movil-390x844-claro.png` | Biblioteca en móvil |
| `por-revisar--escritorio-1280x800-claro.png` | Por revisar (tarjetas con marcador de portada) |
| `por-revisar--movil-390x844-claro.png` | Por revisar en móvil |
| `colecciones--escritorio-1280x800-claro.png` | Colecciones |
| `descubrir--escritorio-1280x800-claro.png` | Descubrir |
| `deseados--escritorio-1280x800-claro.png` | Deseados (avisos legales con `ui.aviso`) |
| `estado--escritorio-1280x800-claro.png` | Estado (semáforos y comprobaciones) |
| `estado--escritorio-1280x800-oscuro.png` | Estado, tema nocturno |
| `ajustes--escritorio-1280x800-claro.png` | Ajustes |

## Cómo se repiten

1. Abrir sesión en la Pi y guardar la cookie de sesión (método de `scripts/`/sesión de ZascArr).
2. Con Chrome headless y CDP: `Page.navigate` a cada ruta, `Emulation.setDeviceMetricsOverride`
   con el tamaño y `Emulation.setEmulatedMedia` con `prefers-color-scheme`; capturar con
   `Page.captureScreenshot`. En oscuro, **recargar** tras fijar el media (si no, la primera foto
   sale clara).
3. Guardar con el patrón `<pantalla>--<escritorio|movil>-<ancho>x<alto>-<claro|oscuro>.png`.

## Presupuesto de peso (V14)

Medido con la misma receta que el plan de V14 (`docs/design/plan-retirada-css-v14.md` §2.2): bytes
en claro de `web.css` y HTML de la página con sesión; gzip con `gzip -c`.

| Recurso | Antes de V14 (2026-11-13) | Al cerrar V14 | Lectura |
|---|---:|---:|---|
| `web.css` | 130.813 B (934 reglas) | **128.037 B** (941 reglas) | V14 quitó ~7 KB de CSS sin uso; el neto baja aunque entraron pantallas nuevas de otras historias (D3, móvil, borradores…). |
| `/ui/biblioteca` | 43.078 B | 43.893 B | +0,8 KB por contenido nuevo, no por CSS. |
| `/ui/pendientes` | 83.928 B | 91.231 B | +7,3 KB por las pantallas nuevas de revisión (V14 no toca HTML). |
| `/ui/auditoria` | 138.322 B | 139.137 B | +0,8 KB por el informe, no por CSS. |

**Conclusión honesta:** el peso de la hoja baja; el de las páginas sube por historias nuevas, no por
la migración. No se ha recortado contenido para maquillar la cifra.
