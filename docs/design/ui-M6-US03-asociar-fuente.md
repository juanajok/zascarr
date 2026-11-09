# UX — Asociar otra fuente (MIT-M6-US03, #129)

> **Estado:** diseño UX de las tres entregas del corte. **No implementa código, no toca `src/` ni
> `tests/`, no crea rutas y no decide las cuestiones de producto D1-D5 de la especificación.**
> **Base:** `origin/main` = `5f27b3ef967130266a892c7244fbded590f1e9f0` (2026-11-09), worktree
> `.squad/wt-129-ui`, rama `docs/129-ui` (rebasada sobre ese SHA antes de publicar).
> **Insumo principal:** `docs/design/especificacion-M6-US03-asociar-fuente.md` (ya en `main`; se
> leyó durante el refinamiento en `docs/129-refinamiento`, `da3f51b`). Al implementar, contrastar el
> SHA y los textos de la especificación vigente.
> **Insumos vecinos:** #109 (contrato), #127 (procedencia), #128 (previsualización), #133 (estados),
> #134 (cortesía), #182 (discriminantes), ADR 0003 (identidad editorial), `CLAUDE.md` §6.
> **Navegador, lector de pantalla y 360 px:** **NOT RUN** para este diseño; se describen las
> condiciones que la implementación tendrá que verificar.

---

## 0. Resumen para quien implemente

La operación vive en la ficha de la serie y tiene tres momentos: **buscar** en una web elegida a
mano, **confirmar** una ficha concreta y **retirar** una asociación. Buscar no escribe; confirmar
solo apunta la relación; retirar no borra la serie ni sus datos. En ningún momento se fusionan
series, se copian metadatos ni se tocan archivos.

**El recorrido en cinco líneas:**

1. En la ficha, bloque **«Otras fuentes»** → **«Buscar en otra fuente»**.
2. Se elige **una** web (sin valor por defecto) y se escribe/busca un título; **«Buscar»**.
3. Se comparan las **fichas encontradas** (candidatas, no equivalencias) y se pulsa **«Elegir esta ficha»**.
4. Se revisa qué se va a guardar y se confirma con **«Asociar esta ficha»**.
5. En la ficha queda la relación; **«Retirar»** abre una vista previa y deja historial.

**Lo que no cambia:** la ficha sigue teniendo un solo botón principal en cada pantalla, sin
diálogos nativos, sin JS nuevo (HTMX), sin portadas de candidatas y sin ids internos. Las
decisiones de modelo (columnas paralelas, `metadata.asociaciones`, token, comprobante) son las de la
especificación; este documento solo decide **qué ve y qué lee la persona**.

**Cómo se cuentan las palabras** en las tablas de presupuesto: solo la copia fija de la tarea. **No**
cuentan los valores variables (títulos, años, números de ficha), los enlaces de navegación
(«Volver a la serie», «Cancelar») ni el contenido de los `<details>` cerrados. Sí cuenta todo lo que
la persona lee antes de la acción que avanza la tarea.

---

## 1. Principios de esta experiencia

1. **Una candidata no es una equivalencia.** La pantalla dice «podría ser tu serie», nunca «es tu
   serie» ni «coincide». La persona elige; el sistema no autoselecciona ni recomienda.
2. **Una sola web, elegida a mano.** Nunca se consultan varias «por si acaso»; sin valor por defecto
   (la misma regla que la tradición en el alta). Una acción = una consulta.
3. **Buscar no guarda.** A no escribe en la base, no abre transacción de escritura y no emite
   comprobantes. La pantalla puede repetirse sin dejar rastro.
4. **Confirmar guarda una relación, no datos.** Se apunta la ficha de esa web en la serie y una
   entrada de procedencia; no se fusiona, no se enriquece, no se tocan números ni archivos.
5. **Lo desconocido se dice.** «No consta» es información; no se rellena por intuición ni se cambia
   por un guion.
6. **El id de la fuente se enseña para comparar, no como identificador interno.** Se llama «ficha»
   + número; nunca «id externo», «token» ni «payload».
7. **Garantía junto a la acción con efecto.** Antes de confirmar y antes de retirar se ve qué se
   toca y qué no, en una frase junto al botón.
8. **Un botón principal por pantalla.** Las acciones que se repiten (una por candidata, una por
   fuente) son neutras. La acción que avanza la tarea es la única amarilla.
9. **El detalle no estorba.** La comparación y el historial son contenido principal, pero la
   explicación secundaria (qué significa asociar, qué pasa si repito, cómo se elige la web) va en
   `<details>` nativos, que se abren con teclado.
10. **Nada destructivo en A.** A no tiene borrar, fusionar, ni siquiera un botón «deshacer»: no hay
    nada que deshacer porque no se ha escrito.

**Un principal por pantalla (resumen):**

| Pantalla | Único `.primary` |
|---|---|
| Ficha (punto de entrada) | El que ya tiene («Añadir números del disco»); «Buscar en otra fuente» es neutro |
| A1 elegir web | «Buscar» |
| A2 candidatas | **Ninguno**: «Elegir esta ficha» se repite por tarjeta y es neutro |
| B1 confirmar | «Asociar esta ficha» |
| B2 resultado | «Volver a la serie» (éxito, repetición, serie inexistente) · «Volver a buscar» (desactualizada, caducada) · «Comprobar el resultado» (desconocido) · «Volver a mi serie» (conflicto) · «Reintentar» (bloqueo) |
| C1 retirar | «Retirar la asociación» |
| C2 resultado | «Volver a la serie» (o «Comprobar el resultado» si es incierto) |

---

## 2. Punto de entrada: bloque «Otras fuentes» en la ficha

### 2.1 Dónde va y por qué

En `series_detail.html`, **después** del bloque plegable «De dónde sale cada dato» y antes de
«Revisar cambios de datos». Así la identidad y su procedencia se leen juntas, y no compite con el
botón principal de la ficha («Añadir números del disco»), que sigue siendo el único amarillo.

```
┌─ Ficha de serie ─────────────────────────────────────────────────────────────┐
│ ← Biblioteca                                                                  │
│ [portada] THE WICKED + THE DIVINE (2014)                                      │
│           Editorial · géneros · 42 números…                                  │
│           [Añadir números del disco]  ← único botón principal de la ficha    │
│           [Retirar de mi biblioteca]                                          │
│                                                                               │
│ ▸ De dónde sale cada dato            ← ya existente (#127)                    │
│                                                                               │
│ OTRAS FUENTES                         ← bloque nuevo, título de 2 palabras   │
│   Comic Vine · asociada el 09/11/2026              [Retirar]  ← fila si hay  │
│   GCD · ficha 1234567 · asociada el 09/11/2026     [Retirar]                  │
│   Todavía no hay otra fuente asociada.             ← estado vacío             │
│   [Buscar en otra fuente]             ← acción neutra (ghost), no principal   │
│   ▸ Historial de asociaciones         ← solo si hay retiradas                 │
│   ▸ Qué significa asociar             ← solo lectura, plegado                 │
│                                                                               │
│ ▸ Revisar cambios de datos            ← ya existente (#128)                   │
└───────────────────────────────────────────────────────────────────────────────┘
```

**Texto del bloque (exacto):**

| Elemento | Texto | Notas |
|---|---|---|
| Título | «Otras fuentes» | 2 palabras; rótulo de sección en Anton |
| Acción | «Buscar en otra fuente» | `a.btn.ghost.sm`; no principal |
| Estado vacío | «Todavía no hay otra fuente asociada.» | 6 palabras; se sustituye por la lista cuando hay asociaciones |
| Fila de asociación | «{Web} · ficha {n} · asociada el {fecha}» + «Retirar» | El número de ficha se enseña para poder reconocerla; no se pinta ningún id interno |
| Sin fecha o sin procedencia | «{Web} · procedencia no registrada» | No se inventa «asociada por ti» |
| Detalle plegado | «Historial de asociaciones» | Lista de retiradas con web, ficha y fecha |
| Detalle plegado | «Qué significa asociar» | «Solo apunta que esta serie también está en esa web. No se fusiona nada, no se copian datos y no se tocan tus archivos.» |

- Si la serie **ya tiene** identidad en una fuente (por alta, enriquecimiento o una asociación
  confirmada), esa fuente aparece en la lista; la procedencia se muestra si consta y, si no,
  «procedencia no registrada». Retirar una fuente que vino del alta también pasa por la vista previa
  de C: la operación no adivina el origen ni lo reescribe.
- El bloque existe **siempre** que la ficha se sirva: la persona tiene que poder iniciar la tarea
  aunque no haya ninguna asociación.
- No se crea otro panel de procedencia: la fila «Identificador de la fuente» de «De dónde sale cada
  dato» (D-B1 de la especificación) pasa a decir cuántas fuentes hay y desde cuándo, **sin pintar
  ids**, por ejemplo: «Comic Vine (alta) y GCD (asociada el 09/11/2026)».
- El bloque no añade un `<h2>` de pantalla: es una sección de la ficha con título de 2 palabras;
  cumple la regla de mayúsculas de ≤ 3 palabras.

### 2.2 Presupuesto del bloque

| Texto | Palabras |
|---|---:|
| Título + estado vacío + acción | 2 + 6 + 4 = **12** |
| «Qué significa asociar» (plegado, no cuenta antes de la acción) | 27 |
| Historial (plegado) | 3 |

---

## 3. Entrega A · Pantalla A1: elegir web

### 3.1 Qué es y qué no es

Pantalla de entrada de la búsqueda. **No** escribe, **no** consulta todavía, **no** crea token.
Decide la web y el texto de búsqueda; el botón «Buscar» hace **una** petición a **una** web.

**Ruta propuesta (contrato de UX, no de implementación):** `GET /ui/series/{id}/asociar`.
**Título de pestaña:** «Asociar fuente — ZascArr».
**H1:** «Asociar fuente» (2 palabras, Anton).

### 3.2 Wireframe a 360 px

```
┌─ 360 px ─────────────────────────────────────┐
│ ← Volver a la serie                          │
│ ASOCIAR FUENTE                               │
│ Elige en qué web buscar esta serie.          │
│ No se guarda nada hasta que lo confirmes.    │
│                                              │
│ Buscar por título                            │
│ [ The Wicked + The Divine             ]      │
│ Puedes cambiarlo para buscar con otro nombre.│
│                                              │
│ WEB                                          │
│ ( ) Comic Vine    Falta la clave en Ajustes  │
│ (•) AniList       Encendida                  │
│ ( ) Tebeosfera    Encendida                  │
│ ( ) GCD           Apagada en Ajustes         │
│                                              │
│ [ Buscar ]  ← único botón principal          │
│ Buscar no cambia nada: solo consulta la web  │
│ que elijas.                                  │
└──────────────────────────────────────────────┘
```

- El campo de título viene **prellenado con el título local**; se puede cambiar. No se inventa una
  consulta a partir de sinopsis ni de la editorial.
- La lista de webs no trae ninguna seleccionada: el botón «Buscar» empieza **deshabilitado** y se
  activa al elegir una web disponible. No se puede buscar en una web apagada o sin configurar.
- Una web apagada no es un fallo: se muestra en gris, con su motivo y enlace a Ajustes; no se
  consulta ni cuenta como error de la búsqueda.
- Si **ninguna** web está disponible: no hay botón «Buscar»; se muestra el aviso de estado vacío
  (ver §3.4) y un enlace a Ajustes. La pantalla no es un callejón sin salida.

### 3.3 Copia exacta

| Elemento | Texto |
|---|---|
| H1 | «Asociar fuente» |
| Entrada | «Elige en qué web buscar esta serie. No se guarda nada hasta que lo confirmes.» |
| Etiqueta del campo | «Buscar por título» |
| Ayuda del campo | «Puedes cambiarlo para buscar con otro nombre.» |
| Leyenda del grupo | «Web» |
| Estados de web | «Encendida» · «Apagada en Ajustes» · «Falta la clave en Ajustes» |
| Botón principal | «Buscar» |
| Nota bajo el botón | «Buscar no cambia nada: solo consulta la web que elijas.» |
| Enlace a Ajustes | «Ir a Ajustes» |

### 3.4 Estados de A1

| Estado | Cuándo | Texto | Acción |
|---|---|---|---|
| Normal | Alguna web disponible | La pantalla de arriba | «Buscar» |
| Web apagada | La fuente está desactivada | «Apagada en Ajustes» junto a la web, sin radio activo | Enlace «Ir a Ajustes» |
| Configuración incompleta | Comic Vine sin clave | «Falta la clave en Ajustes» | Enlace «Ir a Ajustes» |
| Todo apagado | Ninguna web disponible | «Ninguna web está encendida. Enciéndela en Ajustes si quieres buscar.» | Enlace «Ir a Ajustes»; sin botón de búsqueda |
| Serie inexistente | La serie ya no está | «Esta serie ya no está en tu biblioteca.» | «Volver a la biblioteca» |

**Nunca** se dice «error» al hablar de una web apagada o sin configurar: no se ha intentado nada.

### 3.5 Presupuesto de A1

| Medida | Palabras |
|---|---:|
| Frase de entrada | **15** (≤ 20) |
| Copia fija antes de elegir web (título, entrada, etiqueta, ayuda, leyenda) | **28** (≤ 50) |
| Copia fija antes de elegir web con los cuatro estados peores | **46** (≤ 50) |

Los nombres de las webs y los valores del campo son datos, no copy fija; no se cuentan.

---

## 4. Entrega A · Pantalla A2: comparar candidatas

### 4.1 Qué muestra

Respuesta de una búsqueda ya hecha. Puede ser un fragmento HTMX dentro de A1 o una página completa
si no hay JavaScript: el contenido es el mismo. **No escribe nada.**

- Cabecera de resultados: «Fichas encontradas en {Web}» (H2 con `.titulo-frase`; cambia por web).
- Frase de una línea: **«Estas fichas podrían ser tu serie, pero no se sabe seguro. Compáralas antes
  de elegir.»** (15 palabras; «podrían», no «son»).
- Referencia local fija: «Tu serie: {título} ({año})»; si no hay año, «Tu serie: {título}».
- Una tarjeta por candidata, máximo 10; sin paginación (una consulta por acción).
- Botón «Buscar otra web» (neutro) y enlace «Volver a la serie»; **ningún botón principal**: las
  acciones que se repiten (una por candidata) son neutras. La acción con efecto llega en B.

### 4.2 Wireframe de una tarjeta (desktop y 360)

Desktop: las tarjetas van en rejilla de una o dos columnas según el ancho; **a 360 px, una columna**.
Cada tarjeta es la comparación «lado a lado» entre la serie local y **esa** ficha:

```
┌─ Ficha 1234567 de GCD ───────────────────────────────────────┐
│ The Wicked + The Divine (2014)     [Ver la ficha en GCD ↗]  │
│                                                              │
│ ┌────────────┬──────────────────┬─────────────────────────┐ │
│ │ Dato       │ Tu serie         │ Esta ficha               │ │
│ ├────────────┼──────────────────┼─────────────────────────┤ │
│ │ Título     │ The Wicked…      │ The Wicked + The Divine  │ │
│ │ Año        │ 2014             │ 2014                     │ │
│ │ Editorial  │ Panini Cómics    │ No consta                │ │
│ │ País       │ No consta        │ Estados Unidos           │ │
│ │ Idioma     │ No consta        │ Inglés                   │ │
│ └────────────┴──────────────────┴─────────────────────────┘ │
│ [ Elegir esta ficha ]        ← botón neutro, uno por ficha  │
└──────────────────────────────────────────────────────────────┘
```

- La tabla es real (`<table>` con `<caption>` y `scope="col"`/`scope="row"`), no una rejilla de
  `<div>`: los lectores de pantalla anuncian cada dato con su fila y su columna.
- **«No consta»** es texto visible, nunca un guion ni una celda vacía. Se usa tanto para lo que la
  web no devuelve como para lo que la serie local no tiene (no se inventa país o idioma locales).
- El título de la candidata es un `<h3>` dentro de la tarjeta; el enlace externo lleva
  `target="_blank" rel="noopener noreferrer"` y un nombre accesible que dice que se abre en otra
  pestaña.
- No se muestran portadas: exigirían proxy y otra fuente de tráfico; no hacen falta para comparar
  identidad.
- El número de ficha (`1234567`) se muestra como dato de la web; nunca como «id externo».

### 4.3 Casos obligatorios de A2

**Candidata única.** No se preselecciona ni se asocia sola. Se añade el aviso:
«Solo hay una ficha. Compruébala antes de asociarla.» (8 palabras).

**Homónimas / ambiguas.** Dos o más fichas con los mismos datos no se ordenan por «mejor» ni se
marcan como recomendadas. Sobre la lista:

> «Las dos fichas tienen los mismos datos. Ábrelas en GCD antes de elegir; si no las distingues,
> no asocies ninguna.»

(20 palabras; «las dos» se adapta a «las N»). Cada tarjeta conserva su enlace externo y su botón
«Elegir esta ficha»: la elección sigue siendo posible, pero es explícita y sin recomendación.

**Conflicto de identificador.** Si la ficha ya pertenece a otra serie local, la tarjeta muestra:

- chip de aviso «No se puede asociar»;
- «Esa ficha ya está asociada a «{título de la otra serie}».»;
- enlace «Ver esa serie»;
- **sin** botón «Elegir esta ficha» y sin token.

No se oculta la candidata ni se ofrece reasignarla en un clic.

**Cero candidatas.** H2 «Sin fichas en {Web}» + «{Web} no tiene ninguna ficha con ese título.
Prueba con otro título o con otra web.» Acciones neutras: «Cambiar la búsqueda» (vuelve a A1 con el
título) y «Probar otra web». No hay un botón principal porque no hay nada que confirmar.

**Solo sagas (Tebeosfera).** «Tebeosfera solo devolvió fichas de saga, no de colecciones. No se
puede asociar una saga a una serie.» + «Probar con otro título». Es un resultado distinto de «no
hay nada»: la web respondió.

**Web apagada / configuración incompleta.** No deberían llegar aquí (A1 ya las bloquea). Si ocurren
porque la configuración cambió mientras la búsqueda estaba en curso, se muestra el mismo texto de
#133, sin lista y sin «reintentar en bucle»: «{Web} está apagada en Ajustes. No se ha consultado.»
o «{Web} no está configurada: falta su clave en Ajustes. No se ha consultado.»

**Límite de cortesía.** «{Web} ha pedido esperar un poco. No se ha consultado nada.» + «Vuelve a
intentarlo en {N} s» solo si el contrato da el dato; si no, «Vuelve a intentarlo en un momento.» No
se confunde con «no existe».

**Fallo transitorio.** «No se ha podido consultar {Web}. No es que no exista: es un fallo pasajero.»
+ «Volver a intentarlo».

**Propuesta desactualizada.** Si al previsualizar o confirmar la serie cambió desde la búsqueda:
«Tu serie ha cambiado desde que buscaste. Vuelve a buscar para comparar de nuevo.» + «Volver a
buscar». No se ofrece confirmar con datos viejos.

### 4.4 Estados de A2 (resumen)

| Estado | Título | Acción propuesta | ¿Hay candidatas? |
|---|---|---|---|
| Con resultados | «Fichas encontradas en {Web}» | «Elegir esta ficha» (neutra, por tarjeta) | Sí |
| Candidata única | «Fichas encontradas en {Web}» + aviso | «Elegir esta ficha» | Una |
| Homónimas | «Fichas encontradas en {Web}» + aviso | «Elegir esta ficha» (la persona decide) | Varias |
| Conflicto | «Fichas encontradas en {Web}» | «Ver esa serie»; no elegir | Una bloqueada |
| Sin resultados | «Sin fichas en {Web}» | «Cambiar la búsqueda» | No |
| Solo sagas | «Sin fichas en {Web}» | «Probar con otro título» | No |
| Apagada / incompleta | «No se ha consultado» | «Ir a Ajustes» | No |
| Cortesía | «Espera un momento» | «Volver a intentarlo» | No |
| Fallo | «No se ha podido consultar» | «Volver a intentarlo» | No |

### 4.5 Presupuesto de A2

| Medida | Palabras |
|---|---:|
| Frase de entrada de resultados | **15** (≤ 20) |
| Aviso de candidata única | 8 |
| Aviso de homónimas | 20 |
| Copy fija antes del primer «Elegir esta ficha» (H2 + entrada + cabecera de ficha + etiquetas de tabla) | **28** (≤ 50) |
| Valores de la tabla y títulos | datos variables; no se cuentan |

En el caso de homónimas, la suma fija antes del primer botón es 48 palabras (H2 + entrada +
cabecera de ficha + aviso + etiquetas de tabla): sigue por debajo de 50. El aviso de ambigüedad es
la única excepción que se acerca al límite; **no se recorta** porque es lo que evita una elección al
azar.

---

## 5. Entrega B · Pantalla B1: confirmar

### 5.1 Qué se muestra antes de confirmar

Pantalla de vista previa de **una** ficha, con el token firmado de A. Muestra, sin escribir:

- **Entidad local:** «Tu serie» + título y año. Si existe, editorial actual.
- **Web:** nombre de la fuente.
- **Ficha:** número de ficha de esa web + enlace externo «Ver la ficha en {Web} ↗».
- **Tipo:** «Serie» (entidad que se asocia). No se asocian números, ediciones ni obras.
- **Qué hay ahora:** las fuentes que ya tiene, plegado en un `<details>` «Qué hay ahora en esta
  serie» (después de los botones).
- **Qué no cambia:** la garantía, junto al botón.
- La comparación de A2 se puede releer en un `<details>` «Volver a comparar», también después de los
  botones.
- Si la ficha ya no es válida (huella distinta), no se pinta esta pantalla: se va a B2
  «Ficha desactualizada».

**H1:** «Asociar esta ficha» (3 palabras).

### 5.2 Wireframe a 360 px

```
┌─ 360 px ─────────────────────────────────────┐
│ ← Volver a la serie                          │
│ ASOCIAR ESTA FICHA                           │
│ Revisa lo que se guardará. Hasta que         │
│ confirmes, no cambia nada.                   │
│                                              │
│ Tu serie     The Wicked + The Divine (2014)  │
│ Web          GCD                             │
│ Ficha        1234567  [Ver la ficha en GCD ↗]│
│ Tipo         Serie                           │
│                                              │
│ No se fusiona nada, no se copian datos de esa│
│ web y no se tocan tus archivos. Solo se      │
│ guarda la relación; repetir no duplica.      │
│                                              │
│ [ Asociar esta ficha ]   ← único principal   │
│ [ Cancelar ]             ← vuelve a la ficha │
│                                              │
│ ▸ Volver a comparar                          │
│ ▸ Qué hay ahora en esta serie                │
└──────────────────────────────────────────────┘
```

### 5.3 Copia exacta

| Elemento | Texto |
|---|---|
| H1 | «Asociar esta ficha» |
| Entrada | «Revisa lo que se guardará. Hasta que confirmes, no cambia nada.» |
| Etiquetas | «Tu serie» · «Web» · «Ficha» · «Tipo» |
| Valor de tipo | «Serie» |
| Garantía | «No se fusiona nada, no se copian datos de esa web y no se tocan tus archivos. Solo se guarda la relación; repetir no duplica.» |
| Detalles (después de los botones) | «Volver a comparar» · «Qué hay ahora en esta serie» |
| Botón principal | «Asociar esta ficha» |
| Secundario | «Cancelar» |

- **Un solo botón principal.** «Cancelar» es un enlace neutro; «Volver a comparar» es un
  `<details>` cerrado, no un botón.
- No hay `hx-confirm` ni `<dialog>`: la confirmación es esta pantalla y el POST explícito.
- La garantía está inmediatamente encima del botón, no en la cabecera. Dice «no se copian datos de
  esa web» en lugar de «no se enriquece»: es lo mismo para la persona y evita jerga.
- «Repetir no duplica» está en la misma frase para que la idempotencia sea visible antes de pulsar.

### 5.4 Presupuesto de B1

| Medida | Palabras |
|---|---:|
| Frase de entrada | **11** (≤ 20) |
| Copy fija antes del botón principal (H1 + entrada + etiquetas + valor «Serie» + garantía + enlace externo) | **50** (≤ 50) |
| Valores (título, web, ficha) | datos variables; no se cuentan |

Si al implementar se añade una palabra fija más antes del botón, **se mueve a `<details>`**; no se
sube el umbral.

---

## 6. Entrega B · Pantalla B2: resultado de confirmar

El POST devuelve una pantalla de resultado (o un fragmento HTMX). Nunca se anuncia éxito sin haber
leído el resultado. Los seis estados y sus textos:

| Estado | H1 | Texto principal | Acción |
|---|---|---|---|
| Asociada | «Ficha asociada» | «{Web} queda asociada a esta serie. Si repites esta confirmación, no se duplica.» | «Volver a la serie» (principal) |
| Ya estaba (mismo id) | «Ya estaba asociada» | «No se ha cambiado nada: esa ficha ya constaba en esta serie.» | «Volver a la serie» |
| Repetición del mismo envío | «Ya estaba asociada» | «Es la misma asociación que acabas de guardar. No se ha duplicado nada.» | «Volver a la serie» |
| Conflicto de ficha | «Ficha ocupada» | «La ficha {n} de {Web} ya está asociada a «{otra serie}». No se ha cambiado nada.» | «Volver a mi serie» (principal) + «Ver la otra serie» |
| Ya tiene otra ficha de esa web | «Ya tiene ficha» | «Esta serie ya tiene otra ficha de {Web}. Retírala primero si quieres cambiarla.» | «Retirar la ficha actual» (enlace a C) + «Volver a la serie» |
| Ficha desactualizada | «Ficha desactualizada» | «Tu serie ha cambiado desde que buscaste. No se ha asociado nada; vuelve a buscarla.» | «Volver a buscar» (principal) |
| Propuesta caducada | «Propuesta caducada» | «Han pasado más de 15 minutos. No se ha cambiado nada; vuelve a buscar la ficha.» | «Volver a buscar» |
| Resultado desconocido | «Resultado sin confirmar» | «La respuesta se perdió. No sabemos si se ha guardado ni si sigue sin guardarse. Compruébalo antes de repetir.» | «Comprobar el resultado» (principal) |
| Otra operación | «Vuelve a intentarlo» | «Otra operación coincidió con esta. No se ha cambiado nada.» | «Reintentar» (principal) |
| Serie inexistente | «Serie no encontrada» | «Esta serie ya no está en tu biblioteca.» | «Volver a la biblioteca» |

**Reglas de estos textos:**

- El éxito dice «asociada a esta ficha», no «es la misma serie»: no se afirma equivalencia.
- La repetición no es un error ni un éxito nuevo: «no se ha duplicado nada».
- El conflicto **no** ofrece «quitar de la otra serie» ni «reasignar»; solo explica y enlaza.
- El resultado desconocido **nunca** dice «no se ha guardado» ni «se ha guardado»: dice que no se
  sabe y ofrece comprobarlo. Es el texto más delicado de todo el recorrido.
- B2 muestra el bloque «Otras fuentes» actualizado y un `<details>` «Qué ha cambiado» con:
  «Se ha guardado la ficha {n} de {Web} en esta serie y una entrada en su historial. No se han
  tocado números, archivos ni metadatos.»
- Después del éxito, el foco va al H1 del resultado; después de un error, al aviso
  (`role="alert"`), no al botón.

**Presupuesto de B2:** los resultados son pantallas de estado; la frase de entrada es el propio
texto del resultado (≤ 20 palabras en todos los casos). No hay formulario nuevo que supere el
umbral.

---

## 7. Entrega C · Pantalla C1: retirar una asociación

### 7.1 Entrada y qué muestra

Desde la fila de la fuente en «Otras fuentes» → «Retirar». Abre una **vista previa** (GET) que no
escribe; la confirmación es un POST explícito. **H1:** «Retirar la asociación» (3 palabras).

Muestra:

- la web y la ficha que se quitan («GCD · ficha 1234567»);
- cuándo se añadió, si consta; si no, «procedencia no registrada»;
- qué **no** se toca: la serie, sus números, sus archivos y las demás fuentes;
- que queda en el historial;
- botón principal «Retirar la asociación» y «Cancelar» neutro.

Se puede retirar **cualquier** fuente con identidad registrada, conste o no su procedencia
(D4 de la especificación). No se borra la serie ni ninguna de sus filas de números/archivos.

### 7.2 Wireframe a 360 px

```
┌─ 360 px ─────────────────────────────────────┐
│ ← Volver a la serie                          │
│ RETIRAR LA ASOCIACIÓN                        │
│ Vas a quitar la ficha de GCD de esta serie.  │
│ No se borra nada.                            │
│                                              │
│ Web          GCD                             │
│ Ficha        1234567                         │
│ Añadida      el 09/11/2026                   │
│                                              │
│ La serie, sus números y tus archivos siguen  │
│ igual. Queda en el historial.                │
│                                              │
│ [ Retirar la asociación ]  ← único principal │
│ [ Cancelar ]                                 │
└──────────────────────────────────────────────┘
```

### 7.3 Copia exacta

| Elemento | Texto |
|---|---|
| H1 | «Retirar la asociación» |
| Entrada | «Vas a quitar la ficha de {Web} de esta serie. No se borra nada.» |
| Etiquetas | «Web» · «Ficha» · «Añadida» |
| Garantía | «La serie, sus números y tus archivos siguen igual. Queda en el historial.» |
| Botón principal | «Retirar la asociación» |
| Secundario | «Cancelar» |
| Procedencia desconocida | «No consta cómo se añadió esta ficha.» |

### 7.4 Presupuesto de C1

| Medida | Palabras |
|---|---:|
| Frase de entrada | **14** (≤ 20) |
| Copy fija antes del botón principal (H1 + entrada + etiquetas + garantía) | **33** (≤ 50) |

---

## 8. Entrega C · Pantalla C2: resultado de retirar

| Estado | H1 | Texto principal | Acción |
|---|---|---|---|
| Retirada | «Asociación retirada» | «{Web} ya no está asociada a esta serie. La serie, sus números y tus archivos siguen igual.» | «Volver a la serie» (principal) |
| Ya estaba retirada | «Ya estaba retirada» | «No se ha cambiado nada: esa ficha ya no estaba asociada.» | «Volver a la serie» |
| Otro la retiró / ya no existe | «Ya no estaba» | «Otra acción la había retirado antes. No se ha cambiado nada.» | «Volver a la serie» |
| Resultado desconocido | «Resultado sin confirmar» | «La respuesta se perdió. No sabemos si se ha retirado. Compruébalo antes de repetir.» | «Comprobar el resultado» (principal) |
| Ficha desactualizada | «Ficha desactualizada» | «La asociación cambió desde que abriste la vista previa. No se ha retirado nada; vuelve a revisarla.» | «Volver a la serie» |

- Tras retirar, el historial visible en la ficha gana una entrada: «GCD · ficha 1234567 · retirada
  el {fecha}». Sirve para saber qué se quitó y cuándo, sin guardar quién.
- La serie, sus números, sus archivos, sus demás fuentes y su procedencia (incluida `metadata_source`)
  no se tocan. El texto lo dice de forma explícita.
- Después de retirar se puede volver a asociar la misma ficha: es una operación nueva, con su propia
  entrada de historial; no se «revive» la anterior.

---

## 9. Estados, foco y anuncio (resumen para implementación)

**Vocabulario de #133, ya en llano.** Los estados internos no se pintan; se cuenta lo que pasó y
qué hacer:

| Código interno (#133) | Lo que ve la persona | ¿Es un fallo? |
|---|---|---|
| `ok` | «Fichas encontradas en {Web}» + lista | No |
| `sin_resultados` | «{Web} no tiene ninguna ficha con ese título.» | No |
| `fuente_apagada` | «Apagada en Ajustes» / «No se ha consultado.» | **No** |
| `configuracion_incompleta` | «Falta la clave en Ajustes.» | **No** (falta configuración) |
| `limite_de_cortesia` | «{Web} ha pedido esperar un poco. No se ha consultado nada.» | No es ausencia |
| `fallo_transitorio` | «No se ha podido consultar {Web}. No es que no exista.» | Sí, pasajero |
| `conflicto_identificador` | «Esa ficha ya está asociada a «{otra serie}».» | No (conflicto) |
| `propuesta_desactualizada` | «Tu serie ha cambiado desde que buscaste.» | No (hay que repetir) |
| `resultado_incierto` | «No sabemos si se ha guardado. Compruébalo.» | Sí, sin mentir |


| Momento | Región que cambia | Foco al terminar | Anuncio |
|---|---|---|---|
| A1 → A2 (búsqueda) | `#asociar-resultados` (HTMX `outerHTML`) | H2 de resultados (`tabindex="-1"`) | `role="status"` con «{N} fichas encontradas en {Web}» o el estado vacío/error |
| A2 → B1 (elegir) | Navegación completa a la vista previa | H1 de B1 | — (nueva página) |
| B1 → B2 (confirmar) | `#asociar-panel` (HTMX) o página completa | H1 de B2 (éxito) o el aviso (`role="alert"`) si es error | `role="status"` solo en éxito; el error ya lleva `role="alert"` |
| C1 → C2 (retirar) | `#asociar-panel` (HTMX) o página completa | H1 de C2 | idem |
| Resultado desconocido | B2/C2 | Botón «Comprobar el resultado» (es la acción siguiente) | `role="alert"` con el texto de incertidumbre |

- Los fragmentos HTMX no deben reemplazar el `<h1>` ni el `<main>`; solo el panel de la operación.
- Nunca se anuncia «éxito» antes de leer el resultado; el estado desconocido se anuncia como
  incertidumbre.
- Los avisos de estado de fuente (apagada, falta clave, cortesía, fallo) van en
  `role="status"`/`role="alert"` según su gravedad, pero **no** como `role="alert"` si no hay nada
  roto (una web apagada no es un error).

---

## 10. Accesibilidad

### 10.1 Estructura y semántica

- Una sola `<h1>` por pantalla, de **≤ 3 palabras** (rótulo Anton): «Asociar fuente»,
  «Asociar esta ficha», «Retirar la asociación», «Ficha asociada», etc.
- Los H2 que son frases llevan `.titulo-frase` (Archivo, sin mayúsculas): «Fichas encontradas en
  {Web}», «Sin fichas en {Web}».
- Las webs se eligen con un grupo de `radio` dentro de `<fieldset>`/`<legend>`; no son enlaces
  sueltos ni tarjetas clicables. El estado de cada web va asociado al radio con `aria-describedby`.
- La comparación es una `<table>` por ficha candidata, con `<caption>` (nombre de la ficha y web),
  `scope="col"` y `scope="row"`; no se usan celdas vacías: «No consta» es texto.
- El historial y las explicaciones secundarias son `<details>`/`<summary>` nativos (foco y
  Enter/Espacio estándar). No hay `onclick`, ni `aria-expanded` manual, ni `<dialog>`.

### 10.2 Teclado

- Orden de tabulación: volver → campo de título → radios de web → «Buscar» → resultados →
  enlaces externos → «Elegir esta ficha» (una por tarjeta) → «Buscar otra web» → «Volver».
- Los radios se recorren con flechas; la selección no depende del ratón.
- En B1 y C1, al cargar se enfoca el **H1** (`tabindex="-1"`), no el botón con efecto: el lector
  anuncia primero el contexto y la persona decide cuándo tabular hasta «Asociar esta ficha» o
  «Retirar la asociación». El botón no se autopulsa ni recibe Enter por accidente.
- Tras un POST con resultado, el foco va al H1 del resultado; si el resultado es desconocido, al
  aviso que lo dice y al botón «Comprobar el resultado».
- El botón que dispara un POST lleva `hx-disabled-elt="find button"` para evitar dobles envíos; si
  no hay htmx, el formulario normal sigue funcionando.
- No hay atajos de teclado propios ni trampas de foco.

### 10.3 Lectores de pantalla

- El enlace externo se anuncia como «Ver la ficha {n} en {Web} (se abre en otra pestaña)»; no se
  depende del icono ↗ (que va `aria-hidden`).
- Los chips de estado llevan texto; el color no es el único indicador. «No consta» se lee como
  texto, no como celda vacía.
- El número de ficha se lee como «ficha 1234567», no como «id» ni como un número suelto.
- Los resultados de búsqueda se anuncian una vez en una región `aria-live="polite"`; las tablas no
  se anuncian enteras (sería un muro de texto).
- El resultado de una confirmación se anuncia como estado; el desconocido dice explícitamente que
  no se sabe si se guardó.

### 10.4 360 px

- Fuente mínima 14 px (`.875rem`); ids y años con `font-variant-numeric: tabular-nums` si se
  comparan.
- Una sola columna; las tarjetas de candidata ocupan el ancho disponible. La tabla de comparación
  tiene 3 columnas (etiqueta, «Tu serie», «Esta ficha») y los valores largos envuelven
  (`overflow-wrap: anywhere`); nunca hay scroll lateral de página.
- Los botones de acción se apilan a ancho completo a ≤ 480 px; «Buscar», «Asociar esta ficha» y
  «Retirar la asociación» tienen 44 px de alto mínimo.
- Los enlaces externos y los números largos se parten con `overflow-wrap: anywhere`; no se usan
  `white-space: nowrap` en textos de datos.
- Cabecera y navegación de la app ya son responsive; esta pantalla no añade barras propias ni
  `position: fixed`.
- No se usan tablas de 5+ columnas con todas las candidatas en una fila: a 360 se convertirían en
  scroll lateral o en letra diminuta.

### 10.5 Contraste y tipografía

- Se reutilizan los tokens de `web.css` (`--ink`, `--ink-soft`, `--paper`, chips y avisos); no se
  crean colores nuevos. Todo texto ≥ 4,5:1 (lo fija la prueba existente de contraste).
- Anton solo en H1/rótulos de ≤ 3 palabras; cualquier frase larga va en Archivo (`.titulo-frase`).
- El enlace externo no es el único camino para comparar: la tabla muestra los datos acreditados.

---

## 11. Decisiones de copy delicadas (y por qué)

1. **«Fichas encontradas» / «podría ser tu serie», no «resultados» ni «coincidencias».** Una
   coincidencia de título no acredita identidad; «resultado» sugiere que el sistema ya eligió.
2. **«Elegir esta ficha» (no «Asociar» en A).** Asociar es la acción con efecto de B; en A solo se
   elige cuál se va a revisar. Evita que la persona crea que ya está asociada.
3. **«Asociar esta ficha» en B, nunca «Vincular».** La app usa «vincular» para archivos y números;
   reutilizarlo aquí confundiría dos operaciones distintas.
4. **«No se fusiona nada, no se copian datos de esa web y no se tocan tus archivos. Solo se guarda
   la relación; repetir no duplica.»** Es la garantía de #109 en llano: cubre fusión, enriquecimiento
   y archivos, y añade la idempotencia visible sin decir «idempotente».
5. **«No se ha asociado nada» vs «No sabemos si se ha guardado».** El resultado desconocido es el
   único sitio donde no se puede afirmar ni el sí ni el no; decir «ha fallado» sería mentir y decir
   «guardado» también. Se ofrece «Comprobar el resultado» antes de repetir.
6. **Conflicto: «Esa ficha ya está asociada a «X». No se ha cambiado nada.»** No se ofrece
   reasignar ni «liberar»; el criterio 8 prohíbe la reasignación silenciosa y la UI no la insinúa.
7. **Homónimas: «si no las distingues, no asocies ninguna».** Es la única recomendación negativa del
   recorrido; evita que la persona elija al azar solo porque hay un botón.
8. **«No consta» en vez de «—» o de una celda vacía.** El dato ausente es información; el guion se
   lee como «no aplica» y la celda vacía como error de carga.
9. **«Ficha 1234567» en vez de «id externo».** Es el dato que la persona puede comprobar en la web
   original; el nombre «id» es vocabulario de contrato.
10. **«Te pedimos esperar» / «ha pedido esperar un poco», no «límite de cortesía» ni «rate limit».**
    El estado de #133 se cuenta por lo que pasó y qué hacer, no por su código.
11. **«Web» en el cuerpo y «fuente» en el título y en Ajustes.** El coleccionista reconoce «la web
    de donde salen los datos»; «fuente» ya está en «Fuentes de datos» de Ajustes y en la jerga del
    proyecto, pero no se usa para pedir una acción.
12. **«Propuesta caducada» solo cuando de verdad ha caducado.** No se usa para un fallo de red ni
    para una ficha desactualizada: cada causa tiene su texto y su acción.
13. **Nada de ids internos, tokens, huellas, operaciones ni códigos HTTP en pantalla.** Ni siquiera
    en los `<details>`; el detalle enseña fechas, fuentes y fichas, no contratos.

---

## 12. Qué falta y qué no cubre este documento

- **No implementa** rutas, servicios, plantillas ni pruebas; no decide D1-D5 (entidad serie,
  cardinalidad, `metadata.asociaciones`, retirada o comprobante). Esas decisiones son de la
  especificación y del PO.
- **No valida fuentes reales:** qué devuelve cada web (título, año, editorial, país, idioma, `kind`
  de Tebeosfera) sigue **NOT RUN**; los textos de «No consta» están preparados para esa falta.
- **No mide** navegador, lector de pantalla, teclado real ni 360 px: describe las condiciones que la
  implementación debe verificar. El 360 px de esta ficha es una **condición de aceptación**, no una
  medición hecha.
- **No cubre** la ficha de números/publicaciones (#125/#183); la asociación es a nivel de **serie**.
- **No incluye portadas de candidatas** ni descarga de imágenes; es una decisión de #129 para no
  añadir tráfico ni proxy.
- **No hay camino manual** en esta entrega para homónimas irresolubles: se dice que no se asocie y
  se enlaza a la web original. Un camino manual sería otra historia.
- **No se toca `/api/operaciones`** ni el recuento de asociaciones: el inventario filtra por tipo y
  esta operación no se cuenta, salvo decisión aparte del PO.

### Criterios de aceptación UX → dónde se comprueban al implementar

| # | Criterio | Comprobación |
|---|---|---|
| 1 | Una sola web explícita, sin valor por defecto | Radio sin `checked`; A1 no consulta hasta «Buscar» |
| 2 | Candidata no equivalencia, sin autoselección | Textos «podría ser»; ninguna tarjeta marcada; «Elegir» explícito |
| 3 | Datos acreditados + «No consta» | Tablas con `scope`; celdas nunca vacías |
| 4 | Estados distinguidos | Tabla §9 y §4.4; mensajes distintos para apagada, sin clave, cortesía, fallo, vacío |
| 5 | Buscar no escribe | Cero POST en A; solo GET; sin token visible ni comprobante |
| 6 | La confirmación identifica serie, web, ficha y tipo | B1 pinta los cuatro; el id se enseña como «Ficha n» |
| 7 | Repetir no duplica | Garantía en B1; estados «Ya estaba asociada» y «no se ha duplicado nada» en B2 |
| 8 | Conflicto explicado, sin reasignar | Tarjeta bloqueada en A2; B2 «Ficha ocupada» con enlace a la otra serie |
| 9 | Propuesta desactualizada pide revisar | B2 «Ficha desactualizada» + «Volver a buscar» |
| 10 | Garantía de no fusión/enriquecimiento/archivos | Frase junto al botón de B1 y C1; «Qué ha cambiado» en B2 |
| 11 | Resultado desconocido sin éxito falso | B2/C2 «Resultado sin confirmar» + «Comprobar el resultado» |
| 12 | Una sola acción principal, sin diálogos nativos | Una `.primary` por pantalla; `<details>` nativos; sin `<dialog>`/`hx-confirm` |
| 13 | 360 px sin desbordes; foco y teclado | Verificación de implementación: `scrollWidth == clientWidth`, tab/Enter/Espacio, foco tras HTMX |
| 14 | Español llano y presupuesto | Tablas §3.5, §4.5, §5.4, §7.4; sin tokens, ids internos ni códigos |

**PASS de este documento:** las decisiones de recorrido, textos, estados y accesibilidad están
tomadas y son coherentes con la especificación.
**NOT RUN:** implementación, navegador real, lector de pantalla, teclado físico, 360 px medido,
fuentes reales y Pi. Este documento no los declara.
