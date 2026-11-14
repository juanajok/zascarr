# Revisión UX — carpeta sin serie → buscar en fuentes → asignar

> Revisión de código, plantillas y pruebas, 2026-11-14. **No es una prueba con
> usuarios ni en navegador real.** Las conclusiones de jerarquía y copy se
> basan en el HTML que se sirve y en las reglas publicadas del sistema de diseño.

Documento de benchmark asociado:
[`benchmark-carpeta-fuentes-2026-11-14.md`](benchmark-carpeta-fuentes-2026-11-14.md).

## 1. Recorrido actual, sin adornos

```
Pendientes por carpeta
  [Elegir la serie de esta carpeta]
        ↓
A. Elegir la serie de una carpeta
   ├─ ¿Ya la tienes en tu biblioteca?  ← primer formulario
   ├─ Buscar en las fuentes           ← segundo formulario
   └─ Crear la serie a mano           ← tercer camino
        ↓ (fuente)
R. Resultados de la búsqueda
   candidata + estado de fuentes + serie local parecida + señales de la carpeta
   [tradición ▾] [Elegir esta serie]
        ↓
P. Vista previa del alta
   «Se guardará como…» [Crear serie vacía / Usar esta serie]
        ↓
C. Resultado del alta
   «Serie creada» → [Revisar los archivos de esta carpeta]
        ↓
V. Revisar selección y números → X. Vincular
```

Lo importante ya está bien resuelto: **elegir no escribe**, **crear la serie y
vincular son dos consentimientos separados**, las fuentes se consultan solo a
petición, el alta conserva la carpeta y volver no relanza búsquedas.

## 2. Evidencia de la revisión

- Plantilla principal: `src/zascarr/web/templates/asistente_carpeta.html`.
- Resultados: `_asistente_resultados.html`, `_asistente_macros.html`.
- Vista previa y alta: `_asistente_eleccion.html`, `_alta_vista_previa.html`,
  `_alta_resultado.html`, `asistente_alta.html`.
- Rutas: `src/zascarr/web/asistente_carpetas.py`, `web/discovery.py`.
- Sistema de diseño: `docs/design/sistema-de-diseno-zascarr.md` (un botón
  principal por pantalla; presupuesto de texto; chips; tarjetas; foco).
- Pruebas que fijan el comportamiento actual: `tests/test_asistente_carpetas_pg.py`,
  `tests/test_u19_recorrido_pg.py`, `tests/test_u19_continuidad_pg.py`.

## 3. Hallazgos

### F1 — El camino principal no está primero · Alta

La pantalla A abre con **«¿Ya la tienes en tu biblioteca?»** y su formulario.
La búsqueda en fuentes —la acción que necesita quien no tiene la serie— aparece
después, y la creación a mano después. El primer botón accionable es «Buscar en
mi biblioteca», no «Buscar en las fuentes».

Consecuencias:

- quien no tiene la serie puede probar la búsqueda local, no encontrar nada y
  tener que descubrir que hay otra búsqueda más abajo;
- el foco inicial y el orden de lectura empujan a la vía equivocada;
- no hay un `.primary` que diga cuál es la tarea principal.

### F2 — La búsqueda externa no muestra espera · Alta

El formulario de fuentes usa `hx-post` y sustituye `#asistente-resultados`, pero
no tiene `hx-indicator`, `hx-disabled-elt`, `aria-busy` ni un texto de
«Buscando…». Las fuentes tienen límites de cortesía (Tebeosfera 2,5 s; otras
esperas pueden ser mayores). El botón sigue disponible y el área de resultados
queda vacía mientras tanto.

Riesgo: doble envío, varias consultas a la fuente, y la sensación de que el
botón no ha funcionado.

### F3 — La tradición es un desplegable obligatorio escondido · Alta

En cada resultado hay un `<select name="tradition" required>` sin etiqueta
visible (solo `aria-label`) y un botón «Elegir esta serie». La tradición es
necesaria para crear la serie, pero:

- no se explica en el punto de decisión por qué hay que elegirla;
- la pista de tradición aparece como texto pequeño después del botón;
- si no se elige, el servidor devuelve un aviso y se vuelve a pintar el paso;
- el usuario puede pulsar «Elegir esta serie» creyendo que ya ha terminado.

La regla de no preseleccionar es correcta; el problema es **dónde y cómo se
pide**, no que se pida.

### F4 — La tarjeta de resultado está sobrecargada · Alta

Cada candidata acumula portada, título, año, fuente, enlace externo,
descripción, series locales parecidas, señales de la carpeta, desplegable de
conflicto, tradición y botón. La decisión —«¿es esta serie?»— compite con
metadatos secundarios. En móvil es un bloque largo antes de la acción.

### F5 — Se pierde el contexto de la carpeta · Media

A muestra la carpeta y el número de registros. R solo dice «Se ha buscado X»; no
recuerda de qué carpeta se trata ni cuántos archivos se van a asignar. P vuelve
a mostrar la carpeta; C y V también. El salto A → R es el más largo y el que más
contexto pierde.

### F6 — Volver desde la vista previa obliga a repetir la búsqueda · Media

R es un fragmento sin URL reconstruible. Si se vuelve desde P, se conserva la
consulta escrita, pero no los resultados. La pantalla lo dice, pero el coste es
real: una segunda consulta externa y esperar otra vez. Es coherente con no
guardar resultados, pero debería tener una salida más clara que «vuelve a
buscar».

### F7 — Después de crear, la cabecera y el paso siguen diciendo «Crear» · Alta

`asistente_alta.html` pinta siempre el indicador de pasos en **1. Elegir la
serie**. La respuesta de `/ui/descubrir/crear` sustituye solo `.alta-paso` con
`_alta_resultado.html`; no actualiza el título ni el indicador. Después de que
la serie exista, la página sigue titulada «Crear la serie de la carpeta» y el
paso sigue en 1. El resultado dice «creada», pero el marco de la pantalla no
acompaña.

El siguiente paso («Revisar los archivos de esta carpeta») es un enlace
secundario; debería ser la acción principal de ese estado.

### F8 — El presupuesto de texto de la entrada se incumple · Media

Antes de la primera acción de fuentes hay título, subtítulo, volver, tarjeta de
carpeta, explicación, bloque de biblioteca local completo y formulario local.
El sistema de diseño pide una frase de entrada de ≤20 palabras y ≤50 palabras
visibles antes de la primera acción. Aquí la acción principal no está en ese
primer tramo.

### F9 — La fuente puede no estar disponible y se descubre después de buscar · Media/baja

El estado por fuente (apagada, sin configurar, límite de cortesía, error) se
pinta después de la búsqueda. Si no hay ninguna fuente activa, el usuario se
entera al enviar. Conviene mostrar un resumen compacto antes del formulario:
«Comic Vine activa · AniList sin clave · Tebeosfera apagada», con el enlace a
Ajustes solo si hace falta.

### F10 — Detalles de accesibilidad y lenguaje · Media/baja

- El `<select>` de tradición tiene etiqueta solo para lectores; debería ser
  visible, porque es una decisión de producto.
- El enlace externo usa el glifo `↗` como SVG/texto; el sistema de diseño pide
  icono SVG con nombre accesible.
- «Registros en esta carpeta» usa un término que el glosario reserva para
  contexto técnico; para el coleccionista son **pendientes/archivos**.
- El botón de buscar no se deshabilita ni anuncia el estado de carga.

## 4. Propuestas priorizadas

### P0 — Un solo camino principal

Reordenar A:

```
Pendientes por carpeta › «Comics/Flash (1987)»
14 pendientes · 3 archivos sin serie

[BUSCAR EN LAS FUENTES]  ← acción principal, .primary
[Título de la serie…]    [Buscar]

¿Ya la tienes en tu biblioteca?  ▸ (plegado)
¿No aparece? Crear la serie a mano (enlace secundario)
```

- La búsqueda en fuentes es lo primero y el único `.primary`.
- La búsqueda local y la creación manual pasan a `<details>`/enlace.
- La consulta propuesta se mantiene editable; no se ejecuta sola.
- Se conserva el aviso de que no se crea ni vincula nada.

### P0 — Espera visible y sin doble envío

Sin JavaScript propio, con atributos HTMX:

```html
<form hx-post="…/buscar" hx-target="#asistente-resultados"
      hx-swap="innerHTML" hx-disabled-elt="find button"
      hx-indicator="#buscando">
  <button type="submit">Buscar en las fuentes</button>
</form>
<p id="buscando" role="status" aria-live="polite" hidden>Buscando en las fuentes…</p>
```

- El botón se deshabilita mientras dura la petición.
- El estado se anuncia; el resultado también.
- Si se recupera de un límite de cortesía, se dice cuánto esperar (ya existe).

### P0 — Llevar la tradición al paso de confirmación

En R, la acción primaria sería **«Usar esta serie»** (sin tradición). En P:

```
Tradición
( ) Grapa americana   ← sugerida por la fuente
( ) Manga
( ) Tebeo español
…
[Crear serie vacía]
```

- Sigue sin haber valor preseleccionado; la sugerencia se marca como pista.
- Se explica en una frase: «La tradición decide cómo se cuenta la serie; no
  cambia el título».
- Se elimina el error de «elige la tradición» en la pantalla de resultados.

Si el PO prefiere no moverla, como mínimo: etiqueta visible, ayuda junto al
select y botón deshabilitado hasta elegir.

### P0 — Actualizar el marco tras crear

- La respuesta de crear debe actualizar el `<h1>` y el indicador de pasos a
  **2. Revisar los archivos**, no solo el fragmento del alta.
- «Revisar los archivos de esta carpeta» pasa a `.primary`.
- Se mantiene «Deshacer» como acción secundaria y el aviso de que no se ha
  vinculado nada.

### P1 — Resultado compacto y contexto persistente

- Cabecera de R: «Buscando para **Comics/Flash (1987)** · 14 pendientes».
- Tarjeta: portada, título, año, fuente y un chip de **coincidencia con la
  carpeta**; descripción y señales en `<details>`.
- Una sola acción por candidata: «Usar esta serie».
- Las series locales parecidas, si existen, como bloque separado y breve.

### P1 — Volver sin repetir la consulta

- En P, «Volver a los resultados» debe explicar que los resultados no se
  conservan y ofrecer la consulta ya escrita, sin lanzarla.
- Si se puede conservar la lista firmada sin consultar la fuente, hacerlo; si
  no, al menos el texto debe ser «La búsqueda no se guarda; pulsa Buscar para
  repetirla» en vez de un párrafo largo.

### P1 — Estado de fuentes antes de buscar

Resumen compacto con `ui.chip` por fuente; si no hay ninguna activa, mostrar la
salida a Ajustes **antes** de que el usuario escriba. El detalle por fuente se
mantiene después de buscar.

### P2 — Accesibilidad, móvil y design system

- Etiqueta visible para tradición; asociar ayuda con `aria-describedby`.
- Icono SVG para el enlace externo, con nombre accesible que diga que abre en
  otra pestaña.
- Mantener 44 px y el foco visible en selects y botones.
- Sustituir «Registros en esta carpeta» por «Pendientes en esta carpeta» o
  «Archivos pendientes» según el glosario.
- Reducir el texto de A para cumplir ≤50 palabras antes de la acción principal.

## 5. Adhesión al sistema de diseño

| Regla | Estado actual | Propuesta |
|---|---|---|
| Un botón principal por pantalla | A tiene tres formularios y ningún `.primary`; C tiene un enlace secundario para el siguiente paso | Fuentes como `.primary`; «Revisar archivos» como `.primary` tras crear |
| Presupuesto de texto | Demasiados párrafos antes de la acción de fuentes | Mover local/manual a `<details>`; una frase de entrada |
| Tarjetas que enlazan | Resultados usan `discovery-card`, pero la decisión queda bajo metadatos | Resumen primero; detalles plegados |
| Chips de estado | Ya se usan para fuentes y carpeta | Mantener; añadir chip de coincidencia con la carpeta |
| Foco y regiones vivas | Hay `aria-live` en resultados, pero no hay estado de espera ni foco al resultado | `aria-busy`, `hx-indicator`, foco al primer resultado |
| Iconos SVG | El enlace externo usa `↗` | Icono SVG con texto accesible |
| Sin JS propio | Correcto: todo HTMX | Mantener; no usar estado en cliente |

## 6. Criterios de aceptación propuestos

- [ ] La primera acción visible de A es buscar en fuentes y es `.primary`.
- [ ] La búsqueda muestra estado de espera y no admite doble envío.
- [ ] La tradición se elige en P (o en R con etiqueta visible y ayuda), sin
      preselección.
- [ ] R muestra la carpeta de origen y el número de pendientes.
- [ ] Tras crear, la pantalla dice que la serie existe, el paso es 2 y la
      acción principal es revisar los archivos.
- [ ] No hay pérdida de contexto ni callejones al volver.
- [ ] Tests de rutas, textos, foco y contraste; sin nueva dependencia.

## 7. Qué no se propone

- No crear la serie y vincular en la misma petición: rompe la separación de
  consentimientos que ya funciona.
- No preseleccionar una candidata aunque sea la única.
- No eliminar la búsqueda local: pasa a segundo plano, no desaparece.
- No consultar fuentes al abrir la carpeta ni al volver.
- No añadir JavaScript para conservar estado; la URL y el servidor deben seguir
  siendo la memoria.

## 8. Límites de esta revisión

No se ha probado con navegador real, lector de pantalla ni 5 coleccionistas. Las
hipótesis de tiempo, abandono y comprensión deben validarse con el kit de
validación UX. La revisión de código sí confirma los problemas de orden,
etiquetas, estado de carga y actualización del marco tras crear.
