# Walkthroughs sintéticos del flujo «Por revisar» — resultados

> **No son usuarios reales.** Son 5 recorridos independientes hechos el
> 2026-11-13 por perfiles simulados, leyendo código, plantillas y tests del
> worktree `parser-matcher`. No hay reclutamiento, consentimiento, navegador,
> tiempos reales ni citas de personas. Las «citas» son reconstrucciones del
> perfil, no transcripciones.
>
> Las 5 sesiones reales del kit
> [`validacion-ux-por-revisar-2026-11-13.md`](validacion-ux-por-revisar-2026-11-13.md)
> siguen **NOT RUN**.

## 1. Perfiles y método

| Perfil | Foco |
|---|---|
| P1. No técnico, 55+ | Vocabulario, miedo a mover, descubrimiento |
| P2. Móvil de una mano | Barra sticky, objetivos táctiles, jerarquía |
| P3. Teclado/lector | Foco, nombres accesibles, anuncios |
| P4. Volumen alto | Paginación, progreso, borradores, packs |
| P5. Cauteloso | Vincular vs Organizar, confirmaciones, recibo |

Cada perfil recorrió las mismas 5 tareas: vincular sin mover, revisar por
carpeta, resolver un conflicto, decidir un pack y reanudar al día siguiente.

## 2. Resultado por tarea

Leyenda: Completa / Parcial / Bloqueada.

| Tarea | P1 | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|
| 1. Vincular sin mover | Duda | Parcial con riesgo alto | Parcial | Parcial / riesgo | Completa solo si el Issue existe |
| 2. Revisar carpeta y dejar el resto | Completa con fricción | Completa con fricción | Bloqueada con teclado | No ejecutable con 30 (límite 100) | Completa |
| 3. Resolver conflicto | Completa con fricción | Parcial | Parcial | Completa con fricción | Fallida en tarjeta individual |
| 4. Decidir un pack | Duda | No por la vía principal | No completable | No segura | Fallida |
| 5. Volver y reanudar | Duda | Parcial | Bloqueada (fragmento roto) | En riesgo | Parcial |

## 3. Hallazgos transversales

### H1 — La jerarquía visual premia lo que mueve · Alta

En la tarjeta individual, «Ver antes de organizar» es el botón verde y el
primero; «Vincular en su sitio» es un `ghost small`. Los cinco perfiles leen
que el botón dominante es el que mueve, justo lo contrario de la intención de
#720. Además hay **dos campos «nº»** casi idénticos.

Evidencia: [`_tarjeta_pendiente.html`](../../src/zascarr/web/templates/_tarjeta_pendiente.html),
[`web.css`](../../src/zascarr/static/web.css).

### H2 — «Vincular en su sitio» tiene precondiciones invisibles · Alta

El botón se pinta siempre, pero el servicio exige estar dentro de la
biblioteca, no estar en `_Unsorted`, que el Issue exista y que no esté ocupado.
El caso normal de un pendiente del importer es `_Unsorted`, así que la vía
segura falla y el aviso remite a «Organizar»; el usuario descubre la
precondición después de intentarlo.

### H3 — El pack no se veía en la tarjeta y podía vincularse · Crítica, corregida

La tarjeta no mostraba `is_pack` y `vincular_en_sitio` no lo comprobaba: un
pack como «Flash 144-158» podía enlazarse entero con la grapa 1, sin mover
nada y sin aviso. El asistente sí lo bloqueaba, pero la tarjeta no.

**Corregido:** `vincular_en_sitio` rechaza packs con el mismo texto que el
asistente. Test nuevo en `tests/test_vinculacion_en_sitio_pg.py`.

### H4 — «Reanudar revisión» inyectaba la página completa · Alta, corregida

`/reabrir` devolvía `pagina_completa=True` también con `HX-Request`, y el botón
lo insertaba dentro de `#revision`: menú y cabecera duplicados, foco perdido.

**Corregido:** el fragmento solo se devuelve cuando la petición es HTMX. Test
añadido en `TestBorradorGuardado`.

### H5 — Éxito silencioso, sin recibo ni deshacer · Alta

Al vincular u organizar correctamente, la tarjeta desaparece y la respuesta son
dos spans ocultos; no hay «Vinculado X», ni foco, ni deshacer en el mismo
sitio. La desvinculación existe, pero en la ficha de la serie.

### H6 — Guardar y reanudar no se encuentran donde se vuelve · Alta

El borrador solo se descubre al reabrir la misma carpeta **y** la misma serie;
la lista de carpetas no muestra «Revisión guardada» ni «Reanudar (12/30)». Al
guardar y salir no hay acuse. P4 detecta además riesgo de sobrescritura y de
borrado al guardar una página vacía.

### H7 — El conflicto se resuelve «quitando», no comparando · Alta

«Quitar este del lote» funciona, pero no hay comparación lado a lado ni datos
que ayuden a elegir. Para P1/P2/P5, «quitar» suena a perder el archivo. Si el
gemelo está en otra página, no se detecta hasta confirmar.

### H8 — Foco y teclado en el asistente · Alta

Cada marca sustituye `#revision` entera; las casillas no tienen `id`, así que
htmx no puede devolver el foco. En una página de 100 archivos, el teclado vuelve
al principio en cada cambio. Los botones repetidos tampoco llevan el nombre del
archivo en su nombre accesible.

### H9 — Barra sticky y anclajes en móvil · Media/alta

`.vinc-barra` es sticky a `top:0` con `z-index:4`, pero la cabecera conserva
`z-index:30`; puede taparla. «Revisar y vincular» apunta a `#vinc-lote`, que no
tiene `scroll-margin`; el destino queda bajo la barra.

### H10 — Entrada principal y recomendación · Media

«Revisar por carpeta» es primaria, pero el primer tab stop es «Ver las vistas
de trabajo» y la frase «Empieza por carpeta…» va después de los botones y sin
estilos propios.

## 4. Correcciones aplicadas en esta ronda

| Hallazgo | Estado |
|---|---|
| H3 packs sin guarda en Vincular | **Corregido**, test PG |
| H4 reabrir página completa en fragmento | **Corregido**, test PG |
| Tests de ambos | En verde |

## 5. Qué no se ha corregido todavía

Por impacto y orden:

1. **H1/H2:** unificar la tarjeta en un solo número y una acción principal
   segura; no ofrecer «Vincular» condenado a fallar en `_Unsorted`.
2. **H5/H6:** recibo persistente + deshacer + «Revisión guardada» en la lista
   de carpetas.
3. **H7/H8:** comparar conflictos y devolver foco estable; IDs en casillas y
   botones.
4. **H9/H10:** corregir `z-index`/`scroll-margin` y orden de entrada.

## 6. Qué sigue siendo necesario

Estas conclusiones son **hipótesis de diseño**, no evidencia de usuarios. Para
cerrar la validación hay que ejecutar las 5 sesiones reales del kit y comparar.
Mientras tanto, H3 y H4 ya eran fallos objetivos de código y están corregidos.
