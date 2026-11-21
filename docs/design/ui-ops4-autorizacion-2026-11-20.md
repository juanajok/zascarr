# UI/UX — botón de actualización deshabilitado en Estado (#443, OPS4)

> **Revisión de solo lectura. La actualización desde la UI sigue DESHABILITADA.**
> Este documento no edita código, no conecta la UI, el auxiliar, `main.py` ni
> ninguna unidad, no instala ni ejecuta `update.sh` y no habilita nada. Es el
> único fichero creado por esta fase.
>
> - **Rama:** `feat/ops4-seguridad-443`, commit `55baba87` (2026-11-20).
> - **Árbol revisado:** el commit anterior **más** los cambios sin commitear del
>   tramo de autorización app→host (solo `deploy/ops/**`,
>   `src/zascarr/services/**` y pruebas/documentación; ningún fichero de UI).
> - **Superficie revisada:** `/estado` → sección `#actualizacion`
>   ([`estado.html`](../../src/zascarr/web/templates/estado.html), líneas 13-17)
>   y sus pruebas de UI deshabilitada.
> - **Fecha:** 2026-11-20.

## 1. Veredicto

**APTO para mantener la función deshabilitada, sin cambios obligatorios.** El
botón sigue **inerte**, **accesible** y **sin formulario ni acción**, y no
promete una actualización concreta: no hay ruta, ni formulario, ni `hx-*`, ni
`onclick`, ni enlace, ni script que lo use. Se mantiene honesto en los cuatro
estados del aviso de versión.

Dos observaciones **no bloqueantes**, para cuando se toque la sección (no se
aplican ahora):

1. El copy dice «**aún** no está disponible»: «aún» sugiere que llegará. No es
   una promesa operativa (no hay fecha, ni «próximamente», ni botón activo),
   pero conviene quitarlo para no crear expectativa. Copy propuesto en §8.
2. La sección ocupa el primer bloque tras el aviso de versión, por delante del
   resumen de salud de la página. Una acción que no existe no debería competir
   con el diagnóstico; alternativa: bajarla o plegarla en `<details>` mientras
   siga deshabilitada (§9).

El trabajo del desarrollador **no introduce ninguna ruta ni expectativa de UI**
(§7): los códigos de resultado y el paso de confirmación de la nueva
composición son contrato de servicio, están aislados y no se importan desde
`web`, `api` ni `main.py`.

## 2. Alcance y método

- Revisión de solo lectura de la plantilla, el CSS que le aplica, las pruebas
  de UI deshabilitada y el enrutado efectivo de la aplicación.
- Se comprobó el **HTML renderizado** de `/estado` (TestClient con `FakeSession`
  y `aviso_version` forzado a cada estado), no solo la plantilla.
- Se ejecutaron solo las pruebas de UI afectadas; **no** se repitió la suite
  completa (el árbol declara 710 pruebas OPS4/paridad verdes y una suite previa
  verde). No se ejecutó Ruff porque esta fase no modifica código.
- **Fuera de alcance:** habilitar o diseñar la futura UI, la unidad, el
  auxiliar, el transporte y la ejecución real. La UX de una futura UI necesita
  su propia especificación
  ([SPEC §2.2 y §14](especificacion-ops4-autorizacion.md)).

## 3. Estado actual de la sección

HTML renderizado (idéntico en los estados `disponible`, `actualizada`,
`comprobando` y `desconocida`):

```html
<section id="actualizacion" aria-labelledby="actualizacion-titulo">
  <h2 id="actualizacion-titulo" class="seccion">Actualizar ZascArr</h2>
  <p id="actualizacion-no-disponible">La actualización desde esta página aún no está disponible. No se instalará nada.</p>
  <button type="button" disabled aria-describedby="actualizacion-no-disponible">Actualizar ZascArr</button>
</section>
```

Contexto: va dentro del `<main id="main">` de `base.html` (con enlace «Saltar al
contenido» y `lang="es"`), entre la sección «Versión de ZascArr» y el resumen
de salud (`#summary-*`). No es un botón principal (no lleva `.primary`), por lo
que no compite con la regla de «un botón principal por pantalla».

## 4. Comprobación: inerte, sin formulario y sin acción

| Criterio | Resultado | Evidencia |
|---|---|---|
| Se puede pulsar o enviar | **No** | `<button type="button" disabled>`: control nativo inerte, fuera del orden de tabulación y sin comportamiento de envío. |
| Formulario o `action` | **No** | No hay `<form>`, `action`, `formaction` ni `method` en la sección; la prueba los excluye (`test_ops4_ui_deshabilitada.py:73-75`). |
| HTMX o manejadores JS | **No** | Sin `hx-*` ni atributos `on*`; sin `id` en el botón, así que ningún `getElementById` puede engancharle. El único JS de la página hace `fetch` GET de solo lectura a `/api/health` y `/ui/version/estado` (`estado.html:289-331`). |
| Enlace disfrazado | **No** | No hay `<a>` dentro de la sección; el control es un `button` deshabilitado, no un enlace. |
| Ruta ejecutable | **No** | El enrutado efectivo (320 rutas) solo expone `GET /ui/version/estado` (JSON informativo) y `GET /estado`; no hay POST ni ruta con `actualizar`. `test_ops4_ui_gate.py:79-85` comprueba `POST /ui/version/estado`, `/ui/version/actualizar`, `/ui/actualizar` y `/actualizar` contra el enrutador, incluidas rutas parametrizadas. |
| Se anuncia siempre | **Sí** | La sección se pinta en los cuatro estados del aviso de versión (`test_ops4_ui_deshabilitada.py:39-76`); no se oculta cuando hay versión nueva ni cuando no se puede comprobar. |
| Resultado de las pruebas | **Verde** | `tests/test_ops4_ui_deshabilitada.py tests/test_ops4_ui_gate.py` → **9 passed**. |

No hay ningún camino por el que pulsar el botón produzca una petición: ni
formulario, ni HTMX, ni JS, ni ruta. La inercia no depende de que el navegador
ignore un clic, sino de que el control está deshabilitado de forma nativa.

## 5. Accesibilidad

| Aspecto | Valoración | Detalle |
|---|---|---|
| Región y título | Correcto | `<section>` con `aria-labelledby` que apunta al `<h2 id="actualizacion-titulo">`; jerarquía `h1` («Estado») → `h2` correcta. |
| Nombre accesible | Correcto | El nombre del botón es su texto: «Actualizar ZascArr», coherente con el título de la sección. |
| Descripción | Correcta | `aria-describedby="actualizacion-no-disponible"` enlaza la explicación, que además va **antes** del botón en el orden del DOM: quien lee con lector de pantalla encuentra el motivo antes del control. |
| Estado deshabilitado | Correcto | Atributo nativo `disabled`: se anuncia como no disponible y no se puede activar por teclado ni por clic. No hay `aria-disabled` falso ni `tabindex` que lo haga parecer operable. |
| Foco y teclado | Aceptable con matiz | Un `button[disabled]` no recibe foco; por tanto `aria-describedby` no se lee «al enfocar». No hay pérdida de información porque la explicación es texto visible e inmediatamente anterior y el botón repite el título. No hay trampa de foco ni control fantasma. |
| Contraste | Aceptable (componente inactivo) | La regla `button[disabled] { opacity: .5 }` deja la etiqueta en ~3,33:1 en tema claro y ~4,71:1 en oscuro sobre `--paper` (medido sobre los tokens). WCAG 1.4.3 **exime** el texto de componentes de interfaz inactivos; la información esencial («no está disponible», «no se instalará nada») está en el párrafo, a contraste pleno. No se comunica nada solo por color: hay texto y estado nativo. |
| Tamaño | Correcto | `.88rem` (≥14 px) y 40 px de alto; en móvil/táctil sube a 44 px por la regla `@media (max-width: 860px), (pointer: coarse)`. |
| Movimiento | Correcto | Las reglas de `:hover`/`:active` excluyen `[disabled]` (`:where(:not([disabled]))`): no se levanta ni simula pulsación. |
| `forced-colors` | Menor, sin incumplimiento | No hay regla específica para este botón; `opacity: .5` puede atenuarlo más en alto contraste. Es un componente inactivo y la etiqueta duplica el título; si algún día se toca el CSS, una regla de `forced-colors` que mantenga borde/etiqueta sería una mejora, no un requisito. |
| Anuncio dinámico | No aplica | El bloque es estático; no necesita `aria-live`. El aviso de versión ya tiene su propia `aria-live` (`#version-aviso`). |

### Matiz sobre el foco

Si en el futuro se quisiera que el motivo se anunciara al llegar con Tab, el
patrón sería `aria-disabled="true"` + control enfocable + JS que bloquee la
acción. **No se recomienda ahora**: añadiría JavaScript y una acción aparente
que hoy no existe, justo lo que esta fase quiere evitar. La solución actual
(texto visible + `disabled` nativo) es la más simple y honesta.

## 6. ¿Promete una actualización?

**No promete una actualización concreta**, pero el copy tiene un matiz
mejorable:

- La frase «La actualización desde esta página **aún** no está disponible»
  informa correctamente de que hoy no se puede. «Aún» implica «todavía no» y
  sugiere un futuro; no hay fecha ni «próximamente», así que no es una promesa
  operativa, pero es la única palabra que crea expectativa.
- «No se instalará nada» es una garantía clara y verificable, coherente con el
  aviso de versión: «Esta página solo informa; no instala nada»
  ([`_aviso_version.html:2`](../../src/zascarr/web/templates/_aviso_version.html)).
- El título y la etiqueta del botón describen una acción que **hoy no existe**.
  Es aceptable porque el control está deshabilitado y explicado justo antes; no
  se muestra como disponible, no tiene estado de carga y no hay promesa de
  resultado.

**Conclusión:** no hay promesa de que el botón vaya a actualizar. Recomendación
de copy en §8 para eliminar el matiz de «aún».

## 7. ¿El trabajo del desarrollador introduce rutas o expectativas de UI?

**No.** El diff sin commitear no toca superficies de UI:

- `git diff --name-only 55baba87 -- src/zascarr/web src/zascarr/api src/zascarr/main.py src/zascarr/static`
  devuelve vacío. Los ficheros modificados son
  `deploy/ops/registro_repeticiones_ops4.py`,
  `deploy/ops/verificador_autorizacion_ops4.py`,
  `src/zascarr/services/autorizacion_actualizacion.py` y tres pruebas; los
  altas nuevas son documentación (`benchmark-ops4-autorizacion.md`,
  `especificacion-ops4-autorizacion.md`) y una prueba
  (`test_ops4_autorizacion_compuesta.py`). Ninguna plantilla, CSS, JS, router ni
  `main.py`.
- **Sin ruta:** el recorrido del enrutador efectivo no encuentra endpoint de
  actualización; el único relacionado es el `GET /ui/version/estado` ya
  existente, de solo lectura. `test_ops4_ui_gate.py` sigue cubriendo las rutas
  candidatas.
- **Sin importación desde runtime:** `preparar_autorizacion` y
  `ResultadoAutorizacion` no aparecen en `web/**`, `api/**` ni `main.py`;
  `test_ops4_aislamiento.py` amplía la barrera con
  `test_la_composicion_de_autorizacion_no_se_importa_desde_runtime`.
- **Sin textos de superficie:** el servicio añade códigos cerrados
  (`no_habilitada`, `confirmacion_requerida`, `bloqueada` con `hasta_epoch`,
  etc.) y acepta un booleano `entiendo` de confirmación. Son contrato de
  servicio para una futura UI, **no** copy ni fragmentos HTML: la SPEC deja la
  UX explícitamente fuera de alcance (§2.2) y solo **recomienda** un patrón de
  respuesta para la fase de UI (§9.1). Es una expectativa de contrato, no una
  ruta ni una promesa visible.
- Las pruebas de UI deshabilitada y de puerta **no se modificaron** y siguen
  pasando; la prueba de aislamiento que exige que la UI no mencione acciones de
  actualización se mantiene.

**Riesgo residual a vigilar cuando se integre:** la confirmación (`entiendo`),
el aviso de bloqueo con hora y los códigos de resultado exigirán una UI propia
(texto llano, sin «token» ni códigos, `aria-live` para el resultado, 403 de
sesión/origen y sin 422 con la contraseña). Nada de eso existe hoy; si se
reutiliza el copy deshabilitado de este documento al habilitar, sería un error:
el copy de §8 **solo vale mientras la función siga deshabilitada**.

## 8. Copy propuesto (solo si la función sigue deshabilitada)

Mantener el título, el `button` deshabilitado y `aria-describedby`; cambiar solo
el párrafo para quitar la expectativa temporal y alinearlo con el aviso de
versión.

**Opción A (recomendada, cambio mínimo):**

```html
<p id="actualizacion-no-disponible">La actualización desde esta página no está disponible. No se instalará nada.</p>
```

**Opción B (si se quiere unificar con el aviso de versión):**

```html
<p id="actualizacion-no-disponible">La actualización desde esta página no está disponible. Esta página solo informa; no instala nada.</p>
```

Ambas conservan las dos ideas que hoy funcionan: «no está disponible» y «no se
instala nada». No añaden fechas, «próximamente» ni promesas de resultado. Se
mantiene la etiqueta «Actualizar ZascArr»: el estado deshabilitado ya se anuncia
y no hace falta duplicarlo en el nombre accesible.

> **Nota de implementación futura (no ahora):** la prueba
> `test_ops4_ui_deshabilitada.py:66` fija literalmente `"aún no está
> disponible"`. Aplicar la opción A o B exigirá actualizar esa aserción y su
> docstring en el mismo cambio, de forma deliberada. Esta revisión no edita ni
> la prueba ni la plantilla.

## 9. Recomendaciones no bloqueantes

1. **Ubicación y prominencia.** La sección va entre «Versión» y el resumen de
   salud. En una pantalla de diagnóstico, una acción que no existe ocupa el
   primer bloque. Si el PO quiere reducir ruido mientras siga deshabilitada,
   moverla debajo del resumen, junto a «Versión», o plegarla en
   `<details><summary>Actualizar ZascArr</summary>…</details>` conservando el
   texto y el botón deshabilitado. No es un incumplimiento y no se aplica en
   esta fase.
2. **Duplicidad con el aviso de versión.** Hoy hay dos bloques que hablan de
   actualizar: «Versión de ZascArr» (informativo) y «Actualizar ZascArr»
   (deshabilitado). Es correcto que el segundo sea explícito, pero el copy
   debería ser coherente entre ambos (opción B).
3. **Endurecer las pruebas de UI** (cuando se toque esa zona, no ahora):
   - añadir a `test_ops4_ui_gate` las rutas candidatas
     `/ui/actualizar`, `/ui/actualizacion` y `/ui/actualizar/{id}`;
   - comprobar el **nombre accesible** del botón y que el `aria-describedby`
     apunta a un texto con «no está disponible»;
   - rechazar `aria-haspopup`, `aria-expanded`, `aria-controls`, `tabindex`,
     `role="button"` y cualquier `aria-disabled="false"` en la sección;
   - comprobar que la página entera no tiene `form` ni `hx-post` hacia rutas de
     actualización (la prueba actual mira la sección y una ruta concreta).
4. **Contraste/`forced-colors` (deuda menor).** `opacity: .5` es la convención
   del sistema de diseño para `disabled` y aquí no hay pérdida de información.
   Si algún día se prioriza, mantener el borde y la etiqueta visibles en
   `forced-colors` sería la mejora natural; no se cambia ahora para no
   desviarse del sistema de diseño publicado.
5. **Textos preexistentes, fuera de alcance.** Los mensajes de
   `CHECK_ACTION` para errores de BD/actualización invitan a ejecutar
   `sudo bash scripts/update.sh --rama main` (`estado.html:181-183`). No los
   introduce este incremento y no forman parte de la sección revisada, pero
   chocan con la persona «no técnica» y con la idea de que la página no instala
   nada; al especificar la futura UI habrá que armonizarlos o remitirlos a
   quien instaló ZascArr.
6. **Prueba de que sigue deshabilitado.** Mantener y ampliar, no eliminar, las
   pruebas estáticas de aislamiento y de UI deshabilitada: son la red que evita
   que un cambio de integración conecte la UI sin pasar por la puerta de
   habilitación de la SPEC §12.3.

## 10. Evidencia ejecutada

```bash
cd /mnt/Datos/Documentos/Repos/zascarr/.worktrees/ops4-443
PYTHONPATH=.:src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest \
  tests/test_ops4_ui_deshabilitada.py tests/test_ops4_ui_gate.py -q
# 9 passed

git diff --name-only 55baba87 -- src/zascarr/web src/zascarr/api src/zascarr/main.py src/zascarr/static
# (vacío)

# Recorrido del enrutador efectivo (320 rutas): solo GET /ui/version/estado y GET /estado
# contienen «version»/«estado»; ninguna ruta contiene «actualizar» ni «update».
```

No se ejecutó la suite completa ni Ruff: esta fase no modifica código. Las
pruebas nuevas del desarrollador (`test_ops4_autorizacion_compuesta.py`, etc.)
quedan fuera de esta revisión de UI; su aislamiento sí se comprobó de forma
estática (§7).

## 11. Límites de este documento

- **No aprueba habilitar** la actualización, ni fusionar, ni desplegar. La
  función sigue deshabilitada: sin UI conectada, sin ruta, sin auxiliar, sin
  unidad, sin `update.sh`.
- El copy de §8 **solo es válido mientras la función siga deshabilitada**. Una
  UI futura necesita su propia especificación de UX (textos, confirmación,
  estados de bloqueo, resultado incierto y accesibilidad), aprobada por el PO y
  con la revisión de seguridad del SHA final que exige CLAUDE.md §5.8.
- Este documento no sustituye la revisión de la SPEC ni del benchmark; es la
  pasada de UI/UX de la fase de solo lectura del 2026-11-20.
