# UI/UX — Parte A de OPS4/#443: puerta apagada, formulario y resultado

> **Revisión de solo lectura. La actualización desde la UI sigue DESHABILITADA y no se
> autoriza ningún despliegue.**
> Este documento no edita código, no modifica plantillas, CSS, rutas ni configuración, no
> enciende `OPS4_ACTUALIZACION_HABILITADA`, no ejecuta `update.sh`, no toca la Pi, Docker real,
> PostgreSQL real, systemd del host ni el instalador, y no despliega nada. Es el único fichero
> escrito por esta fase.
>
> - **SHA revisado:** `5d775319f7f53310e873f86a23729686deeabc6b` («fix(ops): cerrar Parte A de
>   fusión apagada con TDD (#443)»), 2026-11-21.
> - **Rama:** `feat/ops4-seguridad-443`. El código está limpio; el único cambio en el árbol es
>   este documento sin seguimiento.
> - **Superficie revisada:** `GET /estado` (sección `#actualizacion`), `POST /ui/actualizar`,
>   `actualizacion_resultado.html`, macros `ui.*`, `base.html`, el menú, la configuración de la
>   bandera y las pruebas de UI. No se revisa la seguridad del protocolo ni la ejecución real:
>   eso es SecOps/host y queda fuera de alcance.
> - **Fecha de la revisión:** 2026-11-21.

## 0. Aclaración de alcance sobre el SHA

El commit `5d775319` no toca plantillas ni CSS: su diff es de `deploy/ops/`, pruebas y
documentación. La superficie de UI se introdujo en commits anteriores de la misma rama
(`d6249bdb`, `4c07e49e`, `9646aaec`, entre otros) y **se revisa tal como queda en el árbol de
`5d775319`**, no solo el diff de ese commit. Esto importa porque el resultado (`/ui/actualizar`)
se pinta dentro de `base.html` desde `4c07e49e` y el estado durable se añadió a la respuesta en
`9646aaec`.

## 1. Veredicto

**APTO para fusionar con la función apagada** (no hay hallazgos P0). La bandera efectiva por
defecto es `False`, el botón de `/estado` sigue deshabilitado y `POST /ui/actualizar` responde
`404` antes de leer la clave o reautenticar. La fusión no enciende nada.

**NO-GO para habilitar** hasta cerrar los P1 de §6 y las condiciones de §10. En particular, hay
un enlace roto en la página de resultado, el estado final puede quedar tapado por un aviso verde
de éxito, y el caso `incierta` no avisa de no reintentar en la ruta que de verdad lo muestra (el
estado del fichero del host). Ninguno de esos defectos es alcanzable con la bandera en `false`,
por eso no bloquean la fusión apagada, pero sí bloquean la habilitación.

| Nivel | Nº | ¿Bloquea la fusión apagada? |
|---|---|---|
| P0 | 0 | — |
| P1 | 6 | No (no alcanzables con la bandera apagada); **sí bloquean habilitar** |
| P2 | 9 | No; recomendaciones y deuda para la fase de habilitación |

**No se autoriza despliegue.** La fusión apagada no cambia la política de despliegue
([spec de cierre, A8](especificacion-ops4-cierre.md#A8--no-desplegar-en-el-mismo-acto)): nada de
`instalar_actualizacion_ops4.sh`, `--activar`, `systemctl start/enable`, `update.sh` real, Docker
real, Pi ni cambios de `.env` de producción.

## 2. Método y evidencia ejecutada

Revisión de solo lectura con tres fuentes:

1. Lectura del código y las plantillas del SHA (§3–§7).
2. **HTML renderizado** con `TestClient` (sin lifespan, `FakeSession`, `base_url` y `Origin`
   locales) para la sección apagada, el formulario con la bandera encendida y la página de
   resultado con cada estado final.
3. Pruebas de UI/templates y Ruff (§9). **No** se ejecutó la suite completa.

## 3. Puerta apagada: invariantes comprobadas (PASS)

| Invariante | Resultado | Evidencia |
|---|---|---|
| Bandera por defecto `False` | **Cumple** | [`config.py:280-285`](../../src/zascarr/config.py#L280-L285) (`default=False`). Efectiva en el árbol: `False`. |
| Compose no la enciende por defecto | **Cumple** | [`docker-compose.yml:163-167`](../../docker-compose.yml#L163-L167) (`${OPS4_ACTUALIZACION_HABILITADA:-false}`). |
| No hay botón activo por defecto | **Cumple** | [`estado.html:23-26`](../../src/zascarr/web/templates/estado.html#L23-L26): `button type="button" disabled`, sin `form`, `hx-*`, `on*` ni `<a>`. |
| La ruta responde 404 con la puerta cerrada | **Cumple** | [`actualizacion.py:79-81`](../../src/zascarr/web/actualizacion.py#L79-L81). Comprobado con `Origin` local: `POST /ui/actualizar` → **404**; sin `Origin`, el middleware CSRF responde 403 **antes** de la ruta (no es un fallo de la puerta). |
| La sección se anuncia siempre, en los cuatro estados del aviso | **Cumple** | `test_ops4_ui_deshabilitada.py:39-76`; HTML renderizado. |
| No hay ruta ejecutable sin la puerta | **Cumple** | La ruta existe, pero devuelve 404 antes de autenticar; `test_ops4_ui_gate.py:88-93`. |
| Sin JavaScript nuevo ni HTMX en la sección | **Cumple** | Plantilla sin `hx-*`; el único JS de `/estado` es el sondeo de salud/versión preexistente. |
| Sin CSS nuevo en la rama | **Cumple** | `git diff --stat <merge-base>..HEAD -- src/zascarr/static` vacío; los controles nuevos heredan la base de campos de [`web.css:609-618`](../../src/zascarr/static/web.css#L609-L618). |

La sección apagada renderizada es:

```html
<section id="actualizacion" aria-labelledby="actualizacion-titulo">
  <h2 id="actualizacion-titulo" class="seccion">Actualizar ZascArr</h2>
  <p id="actualizacion-no-disponible">La actualización desde esta página aún no está disponible. No se instalará nada.</p>
  <button type="button" disabled aria-describedby="actualizacion-no-disponible">Actualizar ZascArr</button>
</section>
```

**Conclusión:** con el valor por defecto no hay formulario, ni envío, ni ruta ejecutable; la
promesa «no se instalará nada» es verificable. La puerta apagada cumple.

## 4. Formulario (solo con la bandera encendida)

### 4.1 Marcado y comportamiento

```html
<form method="post" action="/ui/actualizar">
  <p>Se comprobará tu contraseña actual y se pedirá al host que prepare la actualización.
     No se instala nada hasta que el host la acepte.</p>
  <label for="actualizacion-contrasena">Contraseña actual</label>
  <input id="actualizacion-contrasena" type="password" name="contrasena"
         required maxlength="512" autocomplete="current-password">
  <label><input type="checkbox" name="entiendo" value="si" required>
    Entiendo que la actualización modificará el código y la base de datos.</label>
  <button type="submit">Actualizar ZascArr</button>
</form>
```

Viene de [`estado.html:15-22`](../../src/zascarr/web/templates/estado.html#L15-L22).

- **POST de página completa, sin HTMX ni JS:** correcto para una operación que reinicia el
  servicio; no hay `hx-*` ni `on*`.
- **Contraseña:** `required`, `maxlength="512"`, `autocomplete="current-password"`; etiqueta
  asociada por `for`/`id`. Correcto.
- **Confirmación:** casilla con `required` y comprobación de servidor (`entiendo != "si"` →
  aviso `warn`, 400). Correcto.
- **Un solo botón, neutro:** `type="submit"` sin `.primary`; el sistema de diseño dice que un
  envío es neutro por defecto y que solo hay un `.primary` por pantalla. Aquí no compite con la
  tarea de `/estado` (diagnóstico), así que es aceptable.
- **El formulario no aparece con la bandera apagada:** correcto.

### 4.2 Desviaciones y riesgos

- **P1-4 (auth):** el formulario se pinta siempre que la bandera esté encendida, aunque
  `auth_mode == "none"`. En ese caso pide una contraseña que no existe y, al enviar, el servicio
  responde «Activa la contraseña de la app antes de actualizar»
  ([`actualizacion.py:43-44`](../../src/zascarr/web/actualizacion.py#L43-L44)), sin enlace a
  Ajustes → Seguridad. El patrón equivalente de restauración **sí** resuelve ese caso antes de
  pintar el formulario y enlaza a la pantalla de seguridad
  ([`_restaurar_confirmar.html:8-10`](../../src/zascarr/web/templates/_restaurar_confirmar.html#L8-L10)).
- **P2-2 (jerga):** «host» (dos veces), «código» y «base de datos» son vocabulario de quien
  mantiene la Pi, no del coleccionista. La persona del producto no sabe qué es el host ni qué
  significa que se modifique la base de datos. Debe reescribirse en llano y decir **quién** hace
  la operación y **qué no se toca** (la biblioteca de archivos).
- **P2-3 (efecto y parada):** falta decir que ZascArr se reiniciará/se parará un momento y que la
  página puede dejar de responder mientras tanto. La pantalla de restauración sí lo advierte
  («ZascArr se parará uno o dos minutos»). La garantía de que no se mueve ni renombra la
  biblioteca debe ir junto a la acción con efecto, no solo en la documentación.
- **P2-4 (sistema de diseño / accesibilidad de campos):** las etiquetas no usan el patrón de
  campo del sistema (etiqueta **encima**, negrita a `.875rem`; ver
  [sistema de diseño, Formularios](sistema-de-diseno-zascarr.md)):
  `.content label` no tiene regla propia, así que quedan a tamaño normal y en la misma línea que
  el campo. No hay `aria-describedby` que asocie el párrafo explicativo a la contraseña o a la
  casilla, ni un `fieldset`/`legend` que agrupe la confirmación. No hay macro de campo en
  `ui.*` (solo `aviso`, `chip`, etc.), así que la corrección natural es una clase de formulario
  existente o una nueva clase con tokens, no un macro inventado para esta pantalla.
- **P2-5 (doble envío):** no hay `hx-disabled-elt` ni otra protección de doble pulsación. El
  servidor tiene códigos de «ocupada»/duplicado y la autorización corta, así que el daño es
  limitado; aun así, una doble pulsación puede producir una segunda página de resultado
  confusa. Se puede resolver sin JS nuevo (p. ej. deshabilitar tras envío con el patrón ya usado
  en la app) o dejarlo declarado.
- **P1-6 (contradicción con el aviso de versión):** con la bandera encendida, la misma página
  sigue diciendo «Hay una versión nueva de ZascArr. **Esta página solo informa; no instala
  nada.**» en [`_aviso_version.html:2`](../../src/zascarr/web/templates/_aviso_version.html#L2)
  y en el texto de `pollVersion` de [`estado.html:315`](../../src/zascarr/web/templates/estado.html#L315),
  mientras justo debajo hay un formulario que modifica código y base de datos. El aviso de
  versión debe ser condicional a la bandera; hoy la frase es cierta solo con la puerta apagada.

## 5. La respuesta dentro de `base.html`

### 5.1 Lo que funciona

[`actualizacion_resultado.html`](../../src/zascarr/web/templates/actualizacion_resultado.html)
extiende `base.html` y pinta el contenido dentro de `<main id="main">`, con el menú, el pie y el
enlace de salto. Cumple el hallazgo de la revisión de la PR #1159: ya no es un `<p>` suelto. Usa
la macro del sistema `{{ ui.aviso(tipo) }}`, no HTML de aviso escrito a mano, y el estado final
se pasa como contexto. El fallback sin `Request` (solo pruebas) sigue siendo un `<p>` y no es
superficie de usuario.

### 5.2 Matriz real de la página de resultado

Así se pinta hoy, con la bandera encendida y una solicitud aceptada, para cada estado leído del
fichero del host ([`actualizacion.py:31-37`](../../src/zascarr/web/actualizacion.py#L31-L37),
[`actualizacion.py:102-110`](../../src/zascarr/web/actualizacion.py#L102-L110)):

| Estado final leído | Aviso principal (tipo/role) | Texto secundario (`.caption`) | Problema |
|---|---|---|---|
| `aceptada` | `ok`, `role="status"`, ✓ «Solicitud aceptada. La actualización se está preparando.» | «El host ha aceptado la solicitud.» | Duplicidad de mensaje; el estado no aporta nada nuevo. |
| `en_curso` | `ok` | «La actualización está en curso.» | Aceptable, aunque el aviso sigue hablando de «preparando». |
| `hecha` | **`ok`** | «La actualización ha terminado.» | El aviso verde de «solicitud aceptada» sigue siendo el mensaje dominante; el resultado real va en letra secundaria. «Ha terminado» no dice si terminó bien; el finalizador solo escribe `hecha` con éxito limpio. |
| `fallida` | **`ok`** | «La actualización ha fallado.» | **Mensaje contradictorio:** ✓ verde «Solicitud aceptada» + «ha fallado» en letra pequeña. |
| `incierta` | **`ok`** | «No se puede confirmar el estado de la actualización.» | **Mensaje contradictorio y sin «no reintentar»:** el único «no vuelvas a intentarlo» está en `_MENSAJES[INCIERTA]`, que es la ruta en que el **servicio** responde incierto; si el servicio respondió `ACEPTADA` y el fichero de estado dice `incierta`, esa frase no aparece. |

**P1-2:** el tipo del aviso se decide solo por el resultado de la solicitud
([`actualizacion.py:102`](../../src/zascarr/web/actualizacion.py#L102)), no por el estado final
leído. Debe decidirse por el estado final (o pintarse dos mensajes separados: la aceptación como
confirmación secundaria y el estado final como aviso principal). `fallida` e `incierta` no
pueden llevar ✓ verde.

**P1-3:** `incierta` (venga del servicio o del fichero) debe decir en la página de resultado
«No vuelvas a intentarlo; revisa el estado del host / consulta con quien instaló ZascArr», y la
vuelta a `/estado` no puede ofrecer el formulario como si se pudiera reintentar sin más. Hoy
`Volver a Estado` lleva a la página con el formulario activo (si la bandera está encendida) y no
hay ningún aviso de «no reintentar» en ese camino. Es exactamente el caso que la revisión pedía
comprobar: los estados `hecha/fallida/incierta` no deben invitar a reintentar cuando no toca.

**P1-1 (enlace roto):** «Volver a Estado» apunta a **`/ui/estado`**, que **no existe**; la ruta
es `/estado` ([`estado.py:48`](../../src/zascarr/web/estado.py#L48)) y el menú también usa
`/estado` ([`menu.py:42`](../../src/zascarr/web/menu.py#L42)). Comprobado: `GET /ui/estado` →
**404**; `GET /estado` → 200. El único enlace de vuelta dentro del contenido del resultado lleva
a la página de error.
La prueba actual solo busca el texto «Volver a Estado», no el `href`
([`test_ops4_ui_actualizacion.py:205-209`](../../tests/test_ops4_ui_actualizacion.py#L205-L209)),
por eso no lo detecta. Nota: `_logs_visor.html:48` tiene el mismo `href` incorrecto, pero es
preexistente y ajeno a este incremento; conviene arreglarlo aparte.

**P1-5 (una sola foto, sin estado final visible después):** la página lee el fichero **una vez**,
justo al responder el POST. Si en ese momento el host aún no ha escrito el terminal (lo normal:
el auxiliar escribe `aceptada` antes del `start` y el finalizador cierra al final), la página se
queda en «Solicitud aceptada / se está preparando» y **no se actualiza sola**. No hay patrón
Post/Redirect/Get: recargar la página reenvía el POST (el navegador pide confirmación) y un GET
directo a `/ui/actualizar` responde 405; `/estado` no muestra el último intento (eso es B7, no
implementado). Si el servicio se reinicia durante la actualización, la respuesta puede perderse
y el usuario no tiene forma de consultar el resultado. Es una condición de habilitación, no un
defecto de la fusión apagada: exige la vista de último intento/polling de B1.6/B7 (y, si se
quiere, un PRG con URL de resultado consultable).

## 6. Hallazgos P0/P1/P2

### P0 — ninguno

No hay vía activa con la configuración por defecto, no hay formulario activo, no hay ruta
ejecutable sin la bandera y la fusión no cambia el despliegue. No hay P0.

### P1 — bloquean habilitar (no la fusión apagada)

| ID | Hallazgo | Evidencia | Impacto | Condición para cerrar |
|---|---|---|---|---|
| **P1-1** | «Volver a Estado» apunta a `/ui/estado` (404); debe ser `/estado` | [`actualizacion_resultado.html:7`](../../src/zascarr/web/templates/actualizacion_resultado.html#L7); ruta real [`estado.py:48`](../../src/zascarr/web/estado.py#L48); `GET /ui/estado` → 404 comprobado | El único enlace de salida del resultado lleva a error tras una operación con efecto | Cambiar el `href` a `/estado` y añadir prueba del destino (no solo del texto) |
| **P1-2** | El aviso principal es verde `ok` aunque el estado final sea `fallida` o `incierta`; el estado final va en `.caption` secundaria | [`actualizacion.py:102`](../../src/zascarr/web/actualizacion.py#L102); matriz de §5.2; render comprobado | Mensaje contradictorio en la pantalla más delicada: el usuario puede creer que la actualización fue bien cuando falló o es incierta | Derivar `tipo`/mensaje del estado final; `fallida`/`incierta` en `warn` con `role="alert"`; `hecha` en `ok`; aceptación como texto secundario |
| **P1-3** | `incierta` leída del fichero no dice «no reintentar»; el formulario de `/estado` sigue activo y no hay aviso persistente | [`actualizacion.py:36`](../../src/zascarr/web/actualizacion.py#L36) y [`51-54`](../../src/zascarr/web/actualizacion.py#L51-L54); matriz §5.2 | El usuario puede reintentar una operación incierta, justo lo que la UI debía evitar | Cubrir `EstadoActualizacion.INCIERTA` (servicio y fichero) con el texto de no reintento y bloquear/avisar en `/estado` hasta reconciliar; probar ambos caminos |
| **P1-4** | Con la bandera encendida y `auth_mode == "none"` se muestra el formulario de contraseña, que no puede funcionar; el error no enlaza a Ajustes → Seguridad | [`estado.html:15-22`](../../src/zascarr/web/templates/estado.html#L15-L22); [`actualizacion.py:43-44`](../../src/zascarr/web/actualizacion.py#L43-L44); comparable correcto en [`_restaurar_confirmar.html:8-10`](../../src/zascarr/web/templates/_restaurar_confirmar.html#L8-L10) | Formulario que promete una acción imposible y no dice cómo arreglarlo | Ocultar el formulario y mostrar «Activa la contraseña en Ajustes → Seguridad» (con enlace) cuando `auth_activo()` sea falso; probar con `auth_mode="none"` |
| **P1-5** | El resultado es una sola foto del estado; no se actualiza ni hay vista de último intento en `/estado` | [`actualizacion.py:103-110`](../../src/zascarr/web/actualizacion.py#L103-L110); ausencia de B7 en `/estado` ([`estado.py:50-56`](../../src/zascarr/web/estado.py#L50-L56)); §5.2 | Tras una actualización real el usuario no puede saber si terminó bien, falló o quedó incierta; con reinicio del servicio puede no ver ni la respuesta | Implementar B1.6/B7 (proyección cerrada del último intento, polling o vista en `/estado`) y probar el caso «respuesta perdida por reinicio» |
| **P1-6** | Con la bandera encendida, el aviso de versión sigue afirmando «Esta página solo informa; no instala nada» aunque la misma página tenga el formulario de actualización | [`_aviso_version.html:2`](../../src/zascarr/web/templates/_aviso_version.html#L2); [`estado.html:315`](../../src/zascarr/web/templates/estado.html#L315); rama `actualizacion_habilitada` en [`estado.html:15`](../../src/zascarr/web/templates/estado.html#L15) | Contradicción visible entre dos bloques de la misma pantalla; rompe la confianza en la garantía «no se instala nada» | Hacer el texto del aviso condicional a la bandera (y a `pollVersion`) o retirar la garantía cuando la puerta esté encendida; probar ambos valores |

### P2 — recomendaciones y deuda (no bloquean fusionar apagado)

| ID | Hallazgo | Evidencia | Recomendación |
|---|---|---|---|
| **P2-1** | El copy apagado conserva «**aún** no está disponible», que sugiere un futuro | [`estado.html:24`](../../src/zascarr/web/templates/estado.html#L24); lo fija [`test_ops4_ui_deshabilitada.py:66`](../../tests/test_ops4_ui_deshabilitada.py#L66) | Quitar «aún» («La actualización desde esta página no está disponible. No se instalará nada.») y actualizar la prueba en el mismo cambio, como ya recomendó la revisión de 2026-11-20 |
| **P2-2** | Jerga para el coleccionista: «host», «código», «base de datos» | [`estado.html:17`](../../src/zascarr/web/templates/estado.html#L17), [`estado.html:20`](../../src/zascarr/web/templates/estado.html#L20), [`actualizacion.py:32-55`](../../src/zascarr/web/actualizacion.py#L32-L55) | Reescribir en llano: quién hace la operación, qué se actualiza, que no se mueve ni renombra la biblioteca y qué hacer si no se puede comprobar |
| **P2-3** | No se advierte de la parada/reinicio ni del tiempo de la operación junto a la acción | [`estado.html:17`](../../src/zascarr/web/templates/estado.html#L17) | Añadir una frase breve de efecto («ZascArr se reiniciará y la página puede dejar de responder un momento») y la garantía sobre la biblioteca junto al botón |
| **P2-4** | Etiquetas y agrupación fuera del patrón de campos del sistema; sin `aria-describedby` en el párrafo explicativo | [`estado.html:18-20`](../../src/zascarr/web/templates/estado.html#L18-L20); sistemas: Formularios en [sistema de diseño](sistema-de-diseno-zascarr.md) | Etiqueta encima y en negrita `.875rem`, ayuda en `.ajustes-hint`/equivalente, `fieldset`/`legend` para la confirmación y `aria-describedby` si el párrafo explica el campo |
| **P2-5** | Sin protección de doble envío en el formulario (no hay `hx-disabled-elt` ni patrón equivalente) | [`estado.html:21`](../../src/zascarr/web/templates/estado.html#L21) | Usar el patrón de la app para deshabilitar el botón mientras se envía, o declararlo aceptado con el límite del servidor |
| **P2-6** | El estado final se pinta como `.caption` (didascalia), sin icono ni `role`; la página se titula «Actualizar ZascArr», no «Resultado» | [`actualizacion_resultado.html:2-6`](../../src/zascarr/web/templates/actualizacion_resultado.html#L2-L6) | Usar `ui.aviso`/`ui.chip` para el estado final (icono + color + `role`), título de resultado y, si hay error de validación, enlace «Volver al formulario» |
| **P2-7** | El menú no marca ninguna entrada activa en `/ui/actualizar` (`entrada_activa` devuelve `None`) | [`menu.py:49-64`](../../src/zascarr/web/menu.py#L49-L64); render comprobado: `aria-current` = 0 en el resultado | Añadir `/ui/actualizar` → `estado` en `_PREFIJOS` (la entrada «Estado» ya cuelga de `/estado` y `/ui/no-disponibles`) |
| **P2-8** | La sección deshabilitada sigue siendo el primer bloque tras Versión, por delante del diagnóstico; deuda de 2026-11-20 sin cerrar | [`estado.html:13-27`](../../src/zascarr/web/templates/estado.html#L13-L27); revisión previa [`ui-ops4-autorizacion-2026-11-20.md`](ui-ops4-autorizacion-2026-11-20.md) | Mientras siga apagada, bajarla o plegarla en `<details>` conservando el botón deshabilitado y su explicación |
| **P2-9** | Huecos de prueba: no se comprueba el `href` de vuelta, ni el formulario encendido, ni los estados finales, ni el no-reintento; la prueba estática de aislamiento solo mira `hx-post="/ui/actualizar"`, no `action=` | [`test_ops4_ui_actualizacion.py:205-209`](../../tests/test_ops4_ui_actualizacion.py#L205-L209); [`test_ops4_aislamiento.py:44-47`](../../tests/test_ops4_aislamiento.py#L44-L47); [`test_ops4_ui_deshabilitada.py`](../../tests/test_ops4_ui_deshabilitada.py) | Añadir pruebas con la bandera encendida (campos, `required`, etiquetas), del destino de «Volver a Estado», de la matriz de estados (incluida `incierta` sin reintento) y ampliar la guardia estática a `action=` |

## 7. Accesibilidad

| Aspecto | Valoración | Detalle |
|---|---|---|
| Región y jerarquía | Correcta | `<section id="actualizacion" aria-labelledby="actualizacion-titulo">` con `h1` «Estado» → `h2`; la sección apagada mantiene el mismo patrón. |
| Nombre del botón | Correcto | «Actualizar ZascArr»; el deshabilitado se anuncia como no disponible y no es enfocable. |
| Descripción del deshabilitado | Correcta con matiz conocido | `aria-describedby="actualizacion-no-disponible"`; como un `button[disabled]` no recibe foco, el motivo se lee en el párrafo visible anterior. Es la misma limitación aceptada en la revisión de 2026-11-20. |
| Formulario: etiquetas | **Mejorable (P2-4)** | Contraseña con `for`/`id` correcto; casilla envuelta en `<label>` correcta; pero sin patrón visual de campo ni `aria-describedby`. |
| Formulario: obligatoriedad | Correcta | `required` en contraseña y casilla; comprobación de servidor de la casilla; sin `aria-required` redundante. |
| Foco y teclado | Correcto en lo existente | Controles nativos, sin `tabindex` extra; el botón deshabilitado está fuera del orden natural. La página de resultado no mueve el foco al aviso, pero es una carga completa de página y el título es el `h1`; no es un incumplimiento, es una mejora posible (P2). |
| Anuncio del resultado | Correcto con reserva | `ui.aviso("ok")` → `role="status"` y `ui.aviso("warn")` → `role="alert"`, conforme al sistema. La reserva es P1-2: el rol/tipo no refleja el estado final. El estado final como `.caption` no tiene `role` (P2-6). |
| Contraste y tamaño | Sin cambios | No hay CSS nuevo; los campos heredan la base de tinta y el botón la base de botones. `disabled` usa `opacity: .5` (exención de WCAG para controles inactivos), ya medido en la revisión anterior. No se comunica nada solo por color: hay texto. |
| Objetivos táctiles | Correctos | Botón ≥ 40 px (44 px en táctil); casilla 24 px por la regla global; el campo hereda 40 px. |
| Menú / contexto | **Mejorable (P2-7)** | En `/ui/actualizar` no hay `aria-current`; el usuario no ve en el menú que sigue en el área de Estado. |
| Movimiento / `forced-colors` | Sin cambios | Sin animación nueva; la deuda de `forced-colors` del botón deshabilitado es la misma de la revisión anterior. |

## 8. Macros y sistema de diseño

- **La página de resultado usa macros:** `ui.aviso(tipo)` con `tipo ∈ {ok, warn}` es válido en
  `TIPOS_AVISO` ([`componentes.py:49-55`](../../src/zascarr/web/componentes.py#L49-L55)); no hay
  avisos escritos a mano. `ui.aviso` pone icono, borde y `role`; cumple.
- **El formulario usa HTML nativo**, no macros: no existe macro de campo en `ui.*` (las macros
  son `chip`, `aviso`, `grupo`, `estado_vacio`, `progreso`, `region_viva`, `menu`, `portada`).
  Los controles heredan la base de campos de `web.css:609-618`; los botones, la base de
  `web.css:445-470`; la casilla, 24 px. **No es un incumplimiento por sí mismo**, pero las
  etiquetas no siguen la regla de "Formularios" del sistema (P2-4) y el aviso de estado final no
  usa un componente de estado (P2-6).
- **Sin CSS ni JS nuevos** en la rama; el aspecto no introduce tokens fuera de sistema. La
  sección usa `.seccion`, `.caption` y `.btn`, clases existentes.
- **No se copia deuda abierta nueva:** no se añaden clases sin regla, ni `style=` en línea, ni
  `on*`, ni colores literales. La deuda que se hereda (ubicación de la sección apagada, botón
  deshabilitado con `opacity`) es la de la revisión de 2026-11-20, no nueva.

## 9. Evidencia ejecutada

```bash
cd /mnt/Datos/Documentos/Repos/zascarr/.worktrees/ops4-443
export PYTHONPATH=.:src
PY=/mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python
RUFF=/mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/ruff

# 1. Pruebas de UI de OPS4 y del lector de estado
$PY -m pytest tests/test_ops4_ui_actualizacion.py tests/test_ops4_ui_deshabilitada.py \
  tests/test_ops4_ui_gate.py tests/test_ops4_estado_actualizacion.py -q
# 48 passed, 0 failed

# 2. Sistema de diseño, CSS y accesibilidad de plantillas
$PY -m pytest tests/test_web_css_contraste.py tests/test_web_css_sistema_diseno.py \
  tests/test_web_css_tokens.py tests/test_web_componentes.py tests/test_web_css_previa.py \
  tests/test_web_accesibilidad_pendientes.py -q
# 310 passed, 0 failed

# 3. Esqueleto web
$PY -m pytest tests/test_web.py -q
# 11 passed, 0 failed

# 3b. Páginas de Estado, aviso de versión y disponibilidad
$PY -m pytest tests/test_estado_puntos.py tests/test_aviso_version.py \
  tests/test_disponibilidad.py -q
# 86 passed, 0 failed

# 4. Aislamiento e instalador (puerta apagada)
$PY -m pytest tests/test_ops4_aislamiento.py tests/test_instalar_ops4.py -q
# 35 passed, 0 failed

# 5. Ruff del código revisado y de src/
$RUFF check src/zascarr/web/actualizacion.py src/zascarr/web/estado.py src/zascarr/config.py
# All checks passed!
$RUFF check --select S src/zascarr/web/actualizacion.py src/zascarr/web/estado.py \
  src/zascarr/config.py
# All checks passed!
$RUFF check src/
# All checks passed!

# 6. Árbol limpio (solo este documento sin seguimiento) y SHA
git status --short
# ?? docs/design/uiux-ops4-parte-a-2026-11-21.md
git diff --stat
# (vacío)
git rev-parse HEAD
# 5d775319f7f53310e873f86a23729686deeabc6b
```

Comprobaciones de HTML renderizado (TestClient sin lifespan, `base_url`/`Origin` locales):

| Comprobación | Resultado |
|---|---|
| `GET /estado` con la bandera por defecto | 200; sección con `button type="button" disabled`, sin `<form>` |
| `POST /ui/actualizar` con `Origin` local y bandera `false` | **404** `{"detail":"No disponible"}` antes de leer clave/reautenticar |
| `POST /ui/actualizar` sin `Origin` | 403 del middleware CSRF, antes de la ruta; no es un fallo de la puerta |
| `GET /ui/estado` | **404** (el enlace de «Volver a Estado» está roto: P1-1) |
| `GET /estado` | 200 |
| Resultado con estado final `fallida`/`incierta` | Aviso `ok` verde + `.caption` con el estado final (P1-2/P1-3) |
| Resultado con `estado_texto` = `null` | Aviso `ok` sin estado final; no se inventa nada |
| Menú en la página de resultado | 0 `aria-current` (P2-7) |

## 10. Condiciones antes de habilitar

Además de B1–B10, CE-1…CE-12 e I-1…I-9 de la
[especificación de cierre](especificacion-ops4-cierre.md#4-parte-b--contratos-para-habilitar) y de
la revisión SecOps del SHA final, la habilitación no debe ocurrir hasta:

1. **Cerrar P1-1:** «Volver a Estado» → `/estado`, con prueba del destino.
2. **Cerrar P1-2:** el aviso principal y su `tipo`/`role` se derivan del **estado final**, no del
   resultado de la solicitud; `fallida` e `incierta` en `warn`, nunca ✓ verde de éxito.
3. **Cerrar P1-3:** `incierta` (servicio y fichero) con texto expreso de no reintentar y sin
   ofrecer el formulario como si fuera seguro reintentar; política explícita para `fallida`.
4. **Cerrar P1-4:** no pintar el formulario sin contraseña activa; enlace a Ajustes → Seguridad.
5. **Cerrar P1-5:** último intento consultable tras el POST (B1.6/B7), incluido el caso de
   reinicio del servicio y respuesta perdida; no prometer un resultado que la UI no puede leer.
6. **Cerrar P1-6:** el aviso de versión no puede decir «no instala nada» con la puerta encendida.
7. **Cerrar los P2 de copy y accesibilidad** que afectan a la acción con efecto: P2-1 a P2-6;
   P2-7/P2-8 son de contexto y prominencia, y P2-9 es la red de pruebas que debe impedir que
   estos hallazgos vuelvan.
8. **Validación real:** probar el formulario HTTP completo en el entorno aislado/VM, con
   `update.sh` real y la unidad endurecida, no solo el socket local; dejar los NOT RUN de §11
   declarados. Nada de esto se ha ejecutado en esta revisión.
9. **No desplegar en el mismo acto:** la bandera sigue apagada, no se provisiona la clave en
   producción y no se instala ni se arranca la unidad. La fusión apagada no cambia la política
   de despliegue.

## 11. Límites y NOT RUN

- **No se ha ejecutado:** suite completa; Python 3.11 de producción; navegador real (1280/375
  px); lector de pantalla; Docker real; PostgreSQL real; Pi; systemd del host; `update.sh` real;
  instalador OPS4 sobre un host real; socket/unidad reales; ningún despliegue.
- **Sí se ha ejecutado:** las pruebas de UI/templates enumeradas en §9 (incluido el E2E local
  ruta→servicio→socket Unix temporal→admisión→consumo durable de
  `test_ops4_ui_actualizacion.py`), Ruff y las comprobaciones de HTML renderizado de §9. El E2E
  local no sustituye a la validación en el host.
- **No se ha editado código ni configuración.** Este documento no aprueba la habilitación, no
  autoriza la fusión por sí mismo (eso es del coordinador/PO), no sustituye a SecOps y no
  autoriza ningún despliegue.
