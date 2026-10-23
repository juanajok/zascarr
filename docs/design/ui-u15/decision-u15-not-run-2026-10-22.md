# Ficha §13 — Decisión sobre los NOT RUN de U15 (#202) — firmada el 2026-10-22

- **Feature:** #196 Auditoría de UI del 2026-10-15.
- **Historia:** #202 BL-U15, «Que la tradición sugerida en Descubrir no me lleve a error».
- **Alcance de la decisión:** aceptación de los NOT RUN de Comic Vine y AniList y cierre de #202.
- **Código de producto de referencia:** `origin/main` `bf6769967ccbed8f6f229eb586b28edb32576c23`
  (merge de #281).
- **Responsable de la decisión:** juanajok.
- **Fecha de la propuesta:** 2026-10-22.
- **Fecha de firma:** 2026-10-22.
- **Estado:** **firmada** por el responsable el 2026-10-22; decisión adoptada.

## 1. Decisión adoptada

Se **aceptan como límite declarado** los dos NOT RUN de U15 —Comic Vine sin clave y AniList con la API
no disponible— y se **acuerda cerrar #202** con la evidencia del producto, **sin convertir esos NOT RUN en
PASS** y sin afirmar nada sobre el comportamiento real de esas dos fuentes.

La historia pasa a **«Fusionado — pendiente de despliegue»**, no a «Hecha». El cierre no autoriza
desplegar en la Pi ni sustituye la validación con personas de U21.

## 2. Qué se acepta

### 2.1. Lo que sí está cubierto por código y pruebas

- **Medición real de 20 títulos** en las dos fuentes públicas disponibles: GCD y Tebeosfera. Registra
  consulta, resultado, ID, fecha y sugerencia; GCD devolvió resultados en 16/20 y Tebeosfera en 20/20. El detalle
  está en `resultados-reales.json` y `resultados-reales.md`.
- **Contrato de presentación de #276:** `tradition_guess` opcional, procedencia con cuatro valores
  (`explicita`, `transformada`, `por_defecto`, `desconocida`), token retrocompatible, ausencia sin
  `other` y copy diferenciada. Fusionado en `bf67699` (PR #281).
- **Los cinco escenarios de CA6** tienen prueba automática: dato explícito, sugerencia no fiable,
  origen desconocido, ausencia de sugerencia y elección explícita. La elección se completa contra
  PostgreSQL real; el mapeo de pruebas está en `u15b-ausencia-procedencia.md` §5.
- **Verificación en Chrome real del contrato nuevo** (`bf67699`, 2026-10-22): 20/20 selectores
  obligatorios y vacíos, 0 preselecciones, 10 pistas `por_defecto`, 9 `transformada`, 1 tarjeta GCD sin
  pista en `Mortadelo`; 7 tarjetas GCD sin pista en `Lucky Luke`. La elección Manga sobre una pista
  Tebeo español se conserva en la vista previa y no escribe ninguna serie.
  Evidencia: `verificacion-navegador-2026-10-22.md`.
- **Cadena de evidencia anterior:** la verificación de Chrome del 2026-10-21 (`a2721722`) cubrió la
  copy original y la elección explícita; se conserva como evidencia histórica y no se presenta como si
  cubriera #276.

### 2.2. Lo que se acepta específicamente de las dos fuentes no ejecutadas

| Fuente | Cobertura aceptada | Lo que no se acredita |
|---|---|---|
| Comic Vine | El código asigna `american` con procedencia `por_defecto` a cualquier resultado; la presentación y la no preselección están cubiertas por pruebas automáticas. | Que la búsqueda real de *Mortadelo* devuelva 9 resultados, su orden, sus títulos o que la sugerencia sea correcta. No hay `COMICVINE_API_KEY` en el entorno. |
| AniList | El código asigna `manga` con procedencia `explicita`; la presentación y el token están cubiertos por pruebas automáticas. | Que la API responda, que devuelva resultados para los 20 títulos o que su comportamiento actual coincida con el anterior. El 2026-10-21 devolvió 403 y no se ha vuelto a consultar. |

La aceptación es de **cobertura del producto**, no de comportamiento de la fuente. No se declara que
Comic Vine o AniList sean fiables, ni que sus sugerencias acierten, ni que las 20 búsquedas estén
completas en las cuatro fuentes.

## 3. Qué NO se acepta como acreditado

- Que las 20 búsquedas se hayan ejecutado en las cuatro fuentes: solo GCD y Tebeosfera respondieron.
- Que la sugerencia de Comic Vine para *Mortadelo* sea «Grapa americana» en una ejecución real: se
  verificó en la auditoría original y en el código, no en la medición de 20 títulos.
- Que AniList esté disponible o que su 403 sea permanente.
- Que la muestra de 20 títulos sea representativa, estadísticamente significativa o una tasa de acierto.
- Que la verificación en Chrome sea una validación con personas, con lector de pantalla o con teclado.
- Que #202 esté desplegada, «Hecha» o verificada en la Pi.

## 4. Consecuencias

1. **#202 pasa a «Fusionado — pendiente de despliegue»** con la firma de esta ficha (2026-10-22). No pasa a
   «Hecha».
2. **#276 ya está fusionada** en `bf67699`; su tarjeta está en «Fusionado — pendiente de despliegue».
3. **#196 sigue abierta.** El cierre de #202 no cierra el Sprint 0: quedan #208 (condiciones humanas y
   alineación del test de Carpetas), la decisión de cierre de #196 y el despliegue, que sigue sin
   autorización.
4. **Deuda de evidencia:** si más adelante hay `COMICVINE_API_KEY` o AniList vuelve a responder, se
   puede repetir `buscar_20.py` y anexar los resultados. Esa repetición **no es condición** de este
   cierre; queda registrada como deuda en #196, no como un PASS pendiente.
5. **No se toca la Pi.** Nada de esta ficha autoriza desplegar.

## 5. Limitaciones registradas

- La medición real es de **dos fuentes**, no de cuatro; los denominadores de Comic Vine y AniList son
  cero y no se rellenan por inferencia.
- La referencia de tradición de `titulos.json` es provisional y no está contrastada contra un catálogo
  externo.
- Solo se evalúa el **primer resultado** de cada fuente en la medición de 20 títulos; la app muestra
  varias candidatas y la persona elige.
- La verificación de Chrome es headless, con una sesión y dos consultas; no mide personas, lectores de
  pantalla, teclado ni otros navegadores.
- La procedencia `explicita` y el origen `desconocido` no se fuerzan en vivo en esta sesión: quedan
  cubiertos por pruebas automáticas.
- El entorno no es la Pi ni una instalación de producción; la biblioteca y la base son desechables.

## 6. Evidencia

1. **Medición de 20 títulos:** `docs/design/ui-u15/resultados-reales.json` y
   `resultados-reales.md` (commit de producto `8589b47`, 2026-10-21).
2. **Chrome original:** `docs/design/ui-u15/verificacion-navegador-2026-10-21.md` (`a2721722`,
   2026-10-21); 20/20 selectores vacíos y elección Manga sin escribir.
3. **Contrato #276:** `docs/design/ui-u15/u15b-ausencia-procedencia.md`; PR #281 fusionada en
   `bf67699`; pruebas de los cinco escenarios y token retrocompatible.
4. **Chrome nuevo:** `docs/design/ui-u15/verificacion-navegador-2026-10-22.md` y
   `verificacion-navegador-2026-10-22.json` (`bf67699`, 2026-10-22); copy con procedencia, tarjeta GCD
   `None`, elección explícita y 360 px.
5. **Esta ficha:** decisión firmada sobre los NOT RUN el 2026-10-22.

## 7. Firma

**Decisión adoptada:** aceptar los NOT RUN de Comic Vine y AniList como límite declarado y cerrar
#202 con la evidencia del producto, sin declarar PASS de esas dos fuentes ni desplegar.

**Responsable:** juanajok — fecha de la propuesta: 2026-10-22.

**Firma:** juanajok — **Fecha de firma:** 2026-10-22.

Firma registrada tras la fusión de la PR #282 (`06de148`) y antes de la transición de #202 a
«Fusionado — pendiente de despliegue».
