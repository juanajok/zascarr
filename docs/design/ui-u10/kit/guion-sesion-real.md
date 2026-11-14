# Guion de sesión real — «Por revisar» (U13) · #272

> **Estado del kit: preparado. Sesiones con personas: NOT RUN.** Este documento no declara
> validación, no contiene resultados y no sustituye a las personas. La deuda de #272 sigue abierta
> hasta que haya sesiones reales registradas y la ficha §13 actualizada. Mientras tanto, U10 sigue
> siendo **simulación aceptada**, no validación real.

## Cabecera

**Propósito.** Observar con 3–5 coleccionistas no técnicos si la **app real** de «Por revisar»
(U13/BL-R) permite entender qué hay pendiente, por dónde empezar, qué hace cada acción con efecto y
qué salida existe cuando una carpeta reúne dos series. Se buscan fricciones y correcciones; no se
busca aprobar la historia ni producir una tasa.

**Duración.** 45–60 minutos por sesión: 5 de recibir y consentir, 5 de encuadre, 30–38 de tareas,
5–6 de cierre y 2–3 de comprobar el estado. Si el tiempo aprieta, se recorta T4 y la última pregunta
del cierre; **nunca** se recortan T1, T5 ni T6.

**Se prueba.** La aplicación real, no una maqueta: `GET /ui/pendientes`
(`src/zascarr/web/pendientes.py:140`), la vista de carpetas
(`src/zascarr/web/pendientes.py:397`), la cola de sueltos
(`src/zascarr/web/pendientes.py:459`), el asistente de carpeta
(`src/zascarr/web/asistente_carpetas.py:133`), la vista previa de organizar
(`src/zascarr/web/pendientes.py:632`) y, si se llega, la vinculación del asistente
(`src/zascarr/web/asistente_vinculacion.py:420`). Los datos son **la biblioteca del PO en modo solo
lectura** o **una biblioteca de prueba** creada para la sesión. El modo se fija antes de la primera
persona y se registra; no se cambia a mitad.

**No se prueba.** Los prototipos estáticos A/B del 2026-10-21, la simulación con agentes del
2026-11-11, las métricas de representatividad (tasas, medias poblacionales, significación), la
accesibilidad conforme (lector de pantalla, 360 px, texto grande) ni el rendimiento en la Pi, salvo
que se haga una sesión aparte y se declare como tal. Tampoco se prueba el uso a largo plazo ni la
calidad de las series o metadatos que propone el sistema.

**Frase de encuadre (decirla tal cual, antes de la primera tarea).**

> «Esto no es un examen. No hay respuestas correctas ni incorrectas: estamos probando la
> aplicación, no a ti. Si algo te confunde, eso es justo lo que necesitamos saber. Puedes parar o
> saltarte una tarea cuando quieras, y no hace falta que prepares nada ni que me enseñes tu
> colección.»

## 1. Qué se prueba y qué no

### 1.1 Una sola versión: la app real

En esta deuda se prueba **una sola versión**: la app implementada de U13. No hay variante A ni B que
comparar, no se pregunta preferencia A/B y no se alterna el orden A→B / B→A. El requisito de alternar
variantes del comentario de #272 y del README del kit corresponde a los **prototipos**; aquí se
sustituye por algo que sí controla el aprendizaje: **alternar la carpeta de ejemplo** (F-A / F-B)
cuando existan dos equivalentes, y registrar cuál se usó. Si solo hay una, se usa en todas las
sesiones y se declara como límite.

Esto también significa que la línea «preferencia A/B» del documento de consentimiento no se usa en
esta sesión: T7 pregunta por la facilidad, por lo que cambiaría y por la confianza, no por una
variante. Si el PO usa la plantilla de consentimiento tal cual, se adapta antes de firmarla. En la
hoja de registro, la variante es `unica` (pantalla implementada), `orden_variante` queda vacío o
`—` y `preferencia` se marca `no aplica`; no se inventa una comparación.

### 1.2 Datos: biblioteca de prueba o del PO

Hay dos modos y se elige **uno** antes de la primera sesión:

| Modo | Qué se usa | Qué permite | Qué exige |
|---|---|---|---|
| **Biblioteca de prueba** (recomendado) | Una copia o una biblioteca sintética con 2–3 carpetas y 5–10 archivos, en la carpeta de la biblioteca (`library_path`) aparte | Probar T5 hasta la confirmación, grabación de pantalla y restauración limpia | Crear los datos **antes** de la sesión; no tocarlos durante; copia de seguridad |
| **Biblioteca del PO, solo lectura** | La biblioteca real del PO, con permiso explícito | Ver nombres y volúmenes reales sin inventar un escenario | No ejecutar «Confirmar y organizar», «Ignorar», «Vincular» ni crear series; no grabar nombres reales; usar códigos C1/C2 en las notas |

En ambos modos se aplica la regla del [consentimiento del kit](consentimiento-y-conservacion.md):
no se copian rutas, nombres de carpetas ni nombres de archivos de la biblioteca que se muestra (sea
la del PO o la de la persona); si aparecen en pantalla, no se transcriben. En la biblioteca de prueba
se pueden usar nombres sintéticos; en la del PO se usan códigos en las notas y el mapa de códigos se
guarda en el almacenamiento privado del PO, no en el repositorio.

### 1.3 Hipótesis heredadas (son hipótesis, no resultados)

La simulación del 2026-11-11 dejó fricciones candidatas. Este guion las convierte en cosas que
mirar, sin darlas por buenas:

| Hipótesis | Dónde se mira | Qué se quiere observar |
|---|---|---|
| **F1** — la acción que mueve y renombra no se entiende o no se ve el destino | T5 | ¿La nota de efecto y la vista previa bastan para saber qué pasará antes de confirmar? |
| **F2** — la entrada no propone un camino y separa las cifras | T2 | ¿Encuentra cuántos hay y por dónde empezar sin ayuda? |
| **F3** — una carpeta con dos series no ofrece una salida visible | T6 | ¿Detecta la ambigüedad y encuentra una vía que no aplique una sola serie a todo? |
| **F4** — vocabulario y nota pequeña | T1, T3, T4, T5 | ¿Entiende «pendientes», «sueltos», «vistas de trabajo», «organizar»? ¿Lee la nota antes de pulsar? |

Ninguna fila es un hallazgo: son preguntas. Lo observado se registra aparte y se interpreta después,
sin convertir una impresión del moderador en una conclusión.

### 1.4 Lo que este guion no puede concluir

No puede decir que «los coleccionistas» prefieren algo, ni dar porcentajes, ni declarar PASS de
accesibilidad. Con 3–5 personas se describe lo observado, se proponen correcciones y se actualiza la
ficha §13; la decisión de cierre es del PO. Si lo observado contradice la decisión G1 del
2026-10-21, se abre una decisión nueva; no se reescribe la historia ni se convierte la simulación en
validación.

## 2. Antes de la sesión

### 2.1 Elige y fija las dos carpetas

Antes de la primera persona, elige en los datos:

- **F-A (T3):** una carpeta con **una serie clara** y 2 o más archivos. Sirve para «seguir una
  carpeta concreta». Ejemplo de nombre si existe: «Flash (1987)». No se usa si no existe.
- **F-B (T6):** una carpeta con **dos series distintas** o con archivos que apuntan a dos series
  distintas. Si no existe, créala en la biblioteca de prueba **antes** de la sesión; no la crees
  durante.

Escribe el **nombre exacto** de cada una en la hoja de sesión y dilo en el enunciado de T3. Si son
sintéticas, dilo también en el informe («carpeta sintética F-A»), para que nadie las confunda con la
biblioteca real del PO. Si solo hay una carpeta válida, úsala en todas las sesiones y anótalo como
límite; no inventes una segunda.

La biblioteca debe tener, como mínimo:

- una tarjeta con sugerencia guardada («¿Es esta serie?») para T5;
- una carpeta con serie sugerida o sin serie para T3;
- una carpeta con dos series o candidatas distintas para T6;
- 1–2 archivos sueltos para T4.

Si falta la tarjeta con sugerencia, T5 no se puede hacer: es un **fallo de preparación**, no un
fallo de la persona. Anótalo y no improvises una sugerencia.

### 2.2 Congela versión, cuenta y entorno

- **Versión:** anota el SHA o la imagen exacta de la app y no la actualices entre participantes
  (lo da quien despliega, junto con el tag de la imagen; no lo pegues en las notas si el repo es
  privado, usa el identificador corto).
- **Entorno:** navegador y versión, sistema, dispositivo, tamaño de ventana (viewport), zoom y tema
  (claro/oscuro). Si la persona usa su propio dispositivo, anótalo; no cambies el tamaño de ventana
  entre personas.
- **Cuenta:** una cuenta con acceso a «Por revisar» y a las carpetas; si hay login, una cuenta de
  prueba o la del PO con permiso. La contraseña no se escribe en las notas. Al terminar, cierra la
  sesión.
- **Instancia:** nadie más usando la app durante la sesión; importador y rescan parados o sin
  cambios previsibles; sin actualizaciones ni reinicios. Si entra una importación a mitad, las
  cifras cambian y la sesión deja de ser comparable: anótalo como incidencia.

### 2.3 Abre la pantalla correcta

Abre directamente `<URL de la instancia>/ui/pendientes` en una pestaña limpia. No empieces en Inicio
salvo que quieras probar la entrada desde allí (fuera de este guion). Cierra otras pestañas,
notificaciones, chats y cualquier grabador automático. Comprueba antes de que llegue la persona:

- que la lista carga y muestra «Mostrando … de … pendientes»
  (`src/zascarr/web/templates/_pendientes_rango.html:4`);
- que el enlace «Revisar por carpeta» está
  (`src/zascarr/web/templates/pendientes.html:14-15`) y que su recuento llega o, si no llega, que el
  enlace sigue funcionando (`src/zascarr/web/pendientes.py:171-190`);
- que «Ver los archivos sueltos» (`src/zascarr/web/templates/pendientes.html:16`) y «Ver las vistas
  de trabajo» (`:18`) abren;
- que la carpeta F-A y la F-B se encuentran por nombre en la vista de carpetas.

### 2.4 Copia de seguridad y restauración

El moderador **no toca la base de datos ni la biblioteca real**. El responsable técnico prepara y
restaura; el moderador solo verifica que existe el punto de retorno.

1. **Antes:** copia de seguridad de la base de datos de la instancia de prueba y copia de la
   biblioteca de prueba (la carpeta `library_path`). Si se usa la biblioteca del PO, copia acordada
   con el PO y su confirmación por escrito. Prueba la restauración **antes** de la primera sesión, no
   el día de la primera persona.
2. **Durante:** si se ejecuta una acción con efecto (confirmar y organizar, ignorar, crear serie,
   vincular), anota el archivo exacto, la acción, la hora y el resultado. En la biblioteca del PO,
   por defecto **no se ejecuta ninguna**.
3. **Después:** si hubo escritura, para la app, restaura la copia de seguridad de la base de datos y
   la de la biblioteca, arranca y comprueba que el total y las carpetas coinciden con el estado de
   partida. Si no hubo escritura, comprueba que nada cambió. Si la restauración no es posible, no
   sigas con la siguiente persona: el estado ya no es el mismo.
4. **Datos temporales:** borra copias, capturas y grabaciones según el
   [consentimiento](consentimiento-y-conservacion.md). La biblioteca de prueba se puede conservar
   entre sesiones solo si se restaura al estado inicial y se anota.

**Protección de datos y de la biblioteca.** En el modo PO no se ejecuta ninguna acción con efecto.
Si la persona llega a «Confirmar y organizar», «Ignorar», «Vincular N archivos» o a crear una serie,
se le dice **antes** de que pulse: «No hace falta que confirmes para la prueba; puedes parar aquí».
No es una pista de la tarea: es protección de sus datos. Se registra «no ejecutó» y el motivo, no un
fallo. En modo PO no se graba la pantalla; solo notas con códigos C1/C2. En modo prueba, se ejecuta
solo lo que esté en el plan y con restauración preparada.

### 2.5 Lo que no se explica antes de la tarea

No expliques, ni de pasada:

- para qué sirve la pantalla, ni qué es «Por revisar»;
- la diferencia entre «pendientes», «sueltos» y «vistas de trabajo»;
- dónde está el total ni que el recuento de carpetas carga aparte;
- que «Ver antes de organizar» abre una vista previa;
- que «Confirmar y organizar» mueve y renombra, o que «Ignorar» no se puede deshacer;
- que el asistente no crea ni vincula en el primer paso;
- que «Mezcla» significa archivos sin serie y con serie sugerida, no dos series.

Solo se explica la **mecánica de la sesión**: que piense en voz alta, que no hay respuestas
correctas, que puede parar y que se toman notas. Si pregunta «¿qué es esto?», la respuesta es
«¿tú qué crees que es?»; si insiste, «no hay una respuesta correcta, dime lo que te parece».

### 2.6 Etiquetas vigentes (y una que ya no existe)

El guion usa las etiquetas del código actual. La simulación y el comentario de #272 hablan de «Sí,
organizar»: **esa etiqueta ya no existe**. No la uses delante de la persona y no la busques en la
pantalla.

| Lo que se ve hoy | Dónde | Qué hace |
|---|---|---|
| «Revisar por carpeta» | `src/zascarr/web/templates/pendientes.html:14-15` | Enlace primario a la vista de carpetas; el recuento se carga aparte |
| «Ver los archivos sueltos» | `src/zascarr/web/templates/pendientes.html:16` | Cola de sueltos, solo lectura |
| «Ver las vistas de trabajo» | `src/zascarr/web/templates/pendientes.html:18` | `/ui/vistas` (`src/zascarr/web/vistas_trabajo.py:23`), consultas vivas sin escritura |
| «Elegir la serie de esta carpeta» | `src/zascarr/web/templates/carpetas.html:169` | Abre el asistente; no crea ni vincula nada en ese paso |
| «Preparar los archivos de esta carpeta para esta serie» | `src/zascarr/web/templates/carpetas.html:166` | Variante cuando la lista está filtrada por una serie |
| «Ver antes de organizar» | `src/zascarr/web/templates/_tarjeta_pendiente.html:43` | Abre la vista previa; **no mueve** |
| «Esto es lo que pasará si confirmas» | `src/zascarr/web/templates/_previa_asignacion.html:5` | Vista previa con serie, número, carpeta de destino y nombre final |
| «Confirmar y organizar» | `src/zascarr/web/templates/_previa_asignacion.html:18` | La única acción que mueve y renombra |
| «Vincular en su sitio» | `src/zascarr/web/templates/_tarjeta_pendiente.html:30` | Solo si el archivo se puede vincular (fuera de `_Unsorted`, no es un pack) y la publicación ya existe; no mueve ni renombra |
| «Ignorar» | `src/zascarr/web/templates/_tarjeta_pendiente.html:60-65` | Pide confirmación nativa; no tiene deshacer en esta pantalla |
| «Vincular N archivos» | `src/zascarr/web/templates/_vinculacion_revision.html:244` | Confirmación del asistente; vincula en su sitio, no mueve |

**Deshacer.** En «Por revisar» no hay deshacer para «Ignorar» ni para «Confirmar y organizar». El
asistente de alta sí ofrece «Deshacer» cuando crea una serie
(`src/zascarr/web/templates/_alta_resultado.html:35-39`), pero ese no es el flujo de este guion. No
prometas un deshacer que la pantalla no tiene.

## 3. Cómo se conduce

### 3.1 Think-aloud

Di: «Ve diciendo en voz alta lo que piensas, lo que buscas y lo que te sorprende, aunque te parezca
obvio. No hay respuestas correctas». Si se calla, no llenes el silencio: espera y pregunta «¿qué
estás pensando?». No interpretes sus gestos como respuesta; pide palabras.

### 3.2 Escalera de ayuda

Se empieza sin ayuda y solo se sube un peldaño cuando la persona lleva un tiempo sin progresar. Cada
peldaño se anota con la frase exacta.

| Nivel | Qué dices | Cuenta como |
|---|---|---|
| `N0` | Nada; esperas y mantienes una cara neutra | Sin ayuda |
| `N1` | «¿Qué estás pensando?» / «¿Qué esperabas encontrar?» | Método, no ayuda por defecto; **con ayuda** si desbloquea o cambia su camino |
| `N2` | «¿Hay algo en la pantalla que te ayude a decidir?» | Sin ayuda si no orienta a un control concreto; **con ayuda** si lo hace |
| `N3` | «Mira la zona de arriba / el enlace de la izquierda» | **Con ayuda** (pista de zona) |
| `N4` | «Pulsa “X”» | **Con ayuda** (instrucción directa) |
| `N5` | Lo haces tú | **No es éxito de la persona**: `NA` y «moderador ejecutó» |

Reglas:

- No uses las palabras objetivo antes que la persona: «vista previa», «confirmación», «mueve»,
  «renombra», «no aplicada», «mezcla». Si la persona las usa, puedes repetirlas.
- No señales con el dedo ni con el ratón hasta `N3`; si lo haces, es ayuda.
- No completes frases, no asientas con entusiasmo, no corrijas.
- Después de cualquier ayuda, pregunta «¿qué crees que ha pasado?» para ver si lo entendió; sigue
  contando como «con ayuda».

### 3.3 Bloqueo y límites de tiempo

- **45 s sin progreso:** pregunta neutral `N1` o recuerda el think-aloud.
- **90 s sin progreso:** pista de zona (`N3`) y marca «con ayuda».
- **2 min sin progreso:** ofrece pasar a la siguiente tarea. Si acepta, «abandono» con motivo; si
  quiere seguir, déjale hasta el máximo de la tarea (T2: 3 min; T3: 6; T4: 3; T5: 8; T6: 8).
- **Miedo a mover o romper:** no empujes. «Puedes parar; no hay obligación de pulsarlo». Si no lo
  pulsa, se registra «no ejecutó» y se le pregunta qué le frena; no es un fallo automático.
- **Fallo técnico** (error, pantalla en blanco, botón que no responde): para la tarea, anota hora,
  URL y qué pasó, haz una captura solo si está consentida y no muestra datos personales, y no
  depures delante de la persona. Si bloquea la tarea, se salta y se marca «incidencia técnica», no
  «fallo de la persona».
- **Malestar o retirada:** para en el momento, agradece y no insistas. Se registra «retirada».

### 3.4 Neutralidad

No se dice: «pulsa aquí», «está abajo», «eso es para…», «lo que tienes que hacer es…», «¿no ves
que…?», «eso está mal», «es un bug», «debería decir…», «¿verdad que…?», «¿te gusta?». Tampoco se
defiende el diseño ni se explica la intención. Si pregunta si lo hace bien: «No hay una forma
correcta; haz lo que harías en tu casa». Si pregunta si puede volver atrás: responde solo lo que la
pantalla diga; si no lo sabes, «no lo sé; no lo pruebes si no quieres».

### 3.5 Registro del orden y del estado de partida

Antes de T1, anota en la hoja de sesión (los campos están en la
[ficha de sesión](checklist-moderador.md#6-ficha-de-sesión-campos-no-resultados) del checklist):

- seudónimo, fecha y hora, moderador;
- SHA/imagen, URL, navegador y versión, dispositivo, tamaño de ventana, zoom y tema;
- modo de datos (prueba o PO), carpeta F-A y F-B con su nombre exacto, y si son sintéticas;
- total visible al empezar, número de carpetas si ya cargó, y si hay una importación o rescan en
  marcha;
- si se grabó audio o pantalla (y qué se autorizó).

Durante:

- **orden efectivo:** escribe la secuencia real (T1, T2, …). Si saltas, repites o vuelves atrás,
  anótalo con el motivo. No reordenes para «ayudar»;
- **estado tras cada tarea:** ¿cambió la lista, el total o la carpeta? ¿Se movió, ignoró o creó algo?
  Si vuelves a la pantalla de partida, anota la ruta; si no, anota dónde quedaste;
- **ayuda:** nivel (`N0`–`N5`), frase exacta y momento;
- **cita literal:** la primera frase y las que expliquen una confusión, sin corregir la gramática;
- **tiempo:** segundos desde el final del enunciado hasta la respuesta o la acción; para T5, hasta
  la vista previa si no se confirma. Si hay una interrupción técnica, para el cronómetro y anótala.

Si hay dos carpetas equivalentes, alterna F-A / F-B entre participantes y registra cuál se usó. No
cambies el orden T1–T7 entre personas: es la unidad de comparación cualitativa. Si una persona
conoce la app o ya hizo otra sesión, anótalo; su caso no es independiente.

## 4. Tareas

Criterios generales, para no repetirlos en cada tarea:

- **Éxito sin ayuda:** alcanza el objetivo observable con el enunciado y nada más; si necesita que
  le repitas la pregunta porque no la oyó, sigue siendo sin ayuda.
- **Éxito con ayuda:** lo alcanza después de una intervención que orienta (`N2` si de verdad
  orienta, o `N3`/`N4`; también `N1` si desbloquea); se registra la ayuda exacta.
- **Fallo:** no alcanza el objetivo, o lo alcanza con una idea equivocada de lo que pasa.
- **Abandono:** pide pasar, se retira o se agota el tiempo máximo sin alcanzarlo; se registra el
  motivo.
- **No ejecutó:** para acciones que el guion no pide ejecutar (por ejemplo, confirmar y organizar en
  la biblioteca del PO). No es éxito ni fallo; se registra aparte.

### T1 — Cinco segundos: «¿qué puedes hacer aquí?»

**Ruta.** `GET /ui/pendientes` (`src/zascarr/web/pendientes.py:140`); la pantalla que se enseña es la
de `src/zascarr/web/templates/pendientes.html:4-19`.

**Objetivo observable.** Que diga, sin ayuda y sin volver a mirar, para qué sirve la pantalla y qué
haría primero.

**Enunciado exacto.**

> «Te voy a enseñar una pantalla cinco segundos. Mírala sin tocar nada. Luego la tapo y te
> pregunto: ¿qué puedes hacer aquí?»

**Cómo se hace.**

1. Abre la pantalla con la persona delante.
2. Cuenta cinco segundos en silencio y tápala o cambia a una pestaña en blanco.
3. Pregunta «¿Qué puedes hacer aquí?».
4. Deja que termine la primera frase sin corregirla ni dejarle volver a mirar. Si pide verla otra
   vez, «primero dime lo que recuerdas; luego la vemos».
5. Después de la primera respuesta, puedes volver a mostrarla y preguntar «¿cambia algo ahora?».
   Regístralo aparte: T1 mide la primera impresión. Si la persona usa lector de pantalla o necesita
   más tiempo para leer, no apliques el corte de cinco segundos: registra «no aplica» y haz una
   lectura en voz alta; no es el mismo test.

**Qué se observa.** Si nombra el para qué («revisar lo que el sistema no supo clasificar», «archivos
pendientes»), si nombra una acción o un camino («empezar por carpetas», «mirar los sueltos», «abrir
una tarjeta»), y si las tres entradas («Revisar por carpeta», «Ver los archivos sueltos», «Ver las
vistas de trabajo») le parecen un camino o tres puertas sin orden. La entrada tiene una
recomendación visible: «Empieza por carpeta: resuelves varios archivos con una sola decisión»
(`src/zascarr/web/templates/pendientes.html:6`); observa si la lee o la ignora.

**Criterios.**

| Resultado | Qué se registra |
|---|---|
| **Sin ayuda** | Dice para qué sirve y nombra una acción o un camino concreto, con sus palabras |
| **Con ayuda** | Tras una pregunta neutral («¿qué harías primero?») o una pista de zona, llega a esa lectura |
| **Fallo** | Solo lee el título o dice «no sé / no entiendo»; o describe una acción que no existe y no rectifica |
| **Abandono** | Pide saltar, se queda callado tras la pregunta y no quiere seguir, o se retira |

**Qué NO se debe sugerir.** No leas el subtítulo ni la recomendación; no digas «es para clasificar
archivos»; no señales «Revisar por carpeta»; no expliques la diferencia entre las tres entradas; no
digas «mira abajo» ni «hay un total».

**Registra.** Resultado, primera frase literal, si volvió a mirar y qué cambió, y si la primera
impresión se recuperó después.

**Fuente.** `src/zascarr/web/templates/pendientes.html:4-19`; `src/zascarr/web/pendientes.py:140`.

### T2 — Cuántos hay y por dónde empezar

**Ruta.** `GET /ui/pendientes` (`src/zascarr/web/pendientes.py:140`) y, si la persona entra,
`GET /ui/pendientes/carpetas` (`src/zascarr/web/pendientes.py:397`).

**Objetivo observable.** Que encuentre un total y elija un primer paso visible, sin que el moderador
le diga la cifra ni dónde está.

**Enunciado exacto.**

> «Estos son los pendientes. ¿Cuántos hay y por dónde empezarías?»

**Qué se observa.**

- ¿Encuentra el total en «Mostrando X–Y de N pendientes»
  (`src/zascarr/web/templates/_pendientes_rango.html:4`)? ¿O en el recuento de carpetas
  (`src/zascarr/web/templates/_pendientes_carpetas_enlace.html:3`)? ¿O en la vista de carpetas
  (`src/zascarr/web/templates/carpetas.html:140` y el desglose de `:92`)?
- ¿Espera a que cargue el recuento o se impacienta? El enlace funciona aunque el recuento no llegue
  (`src/zascarr/web/pendientes.py:171-190`); un fallo del recuento no es un fallo de la persona.
- ¿Elige el camino que la pantalla propone («Revisar por carpeta»,
  `src/zascarr/web/templates/pendientes.html:14-15`) o inventa otro? ¿Duda entre carpetas y
  sueltos?
- ¿Distingue «cuántos pendientes hay» de «cuántas carpetas hay»? No son lo mismo: el enlace cuenta
  carpetas (`_pendientes_carpetas_enlace.html:3`) y el total cuenta archivos
  (`_pendientes_rango.html:4`).

**Criterios.**

| Resultado | Qué se registra |
|---|---|
| **Sin ayuda** | Da un total correcto (el de la pantalla) y elige un primer paso visible; si usa el enlace de carpetas, espera el recuento sin ayuda |
| **Con ayuda** | Necesita una pista de zona («mira el texto bajo la lista», «espera el número del enlace») y, tras ella, da el total y elige |
| **Fallo** | No encuentra ningún total, da una cifra inventada o elige una acción que no existe; no se corrige tras la pista |
| **Abandono** | No quiere buscar o pide pasar |

**Qué NO se debe sugerir.** No digas la cifra; no digas «el total está abajo» ni «espera a que
cargue»; no digas «empieza por carpetas»; no corrijas una cifra equivocada con la correcta. Si la
app muestra un total distinto del que esperabas (porque los datos son otros), no lo llames error:
anota el que muestra.

**Registra.** Total que da la persona, total que muestra la app, camino elegido, si esperó al
recuento, y si confundió carpetas con archivos.

**Fuente.** `src/zascarr/web/templates/_pendientes_rango.html:4`;
`src/zascarr/web/templates/_pendientes_carpetas_enlace.html:3`;
`src/zascarr/web/templates/pendientes.html:6,14-15`; `src/zascarr/web/pendientes.py:171-190`.

### T3 — Seguir una carpeta concreta

**Ruta.** `GET /ui/pendientes` → `GET /ui/pendientes/carpetas`
(`src/zascarr/web/pendientes.py:397`) → `GET /ui/pendientes/carpetas/asistente?clave=…`
(`src/zascarr/web/asistente_carpetas.py:61,133`).

**Carpeta.** Se fija antes de la sesión (F-A) y se dice su nombre exacto en el enunciado. Si es
sintética, se dice también en la hoja y en el informe. No se usa un nombre inventado si no existe.

**Objetivo observable.** Que encuentre la carpeta, entienda en qué estado está y cuál es el
siguiente paso, sin creer que la sugerencia ya está aplicada.

**Enunciado exacto.**

> «Quieres ocuparte de la carpeta “{CARPETA_T3}”. ¿Qué haces y qué crees que pasará?»

Si pregunta qué significa «ocuparte», responde: «lo que tú harías para revisarla». No expliques la
pantalla.

**Qué se observa.**

- ¿Encuentra la carpeta en la lista o usa el filtro por nombre
  (`src/zascarr/web/templates/carpetas.html:62-64`)? ¿Se pierde con la paginación
  (`carpetas.html:140,245-252`) o con el estado vacío?
- ¿Lee el estado de la carpeta? El chip usa `g.etiqueta`
  (`src/zascarr/web/templates/carpetas.html:156`): «Sin serie» o «Serie sugerida, falta confirmar
  número y edición» (`src/zascarr/services/revision_carpetas.py:50-52`). ¿Entiende que «falta
  confirmar» significa que **no** está aplicada?
- ¿Abre la acción «Elegir la serie de esta carpeta»
  (`src/zascarr/web/templates/carpetas.html:169`) o se queda mirando? ¿Espera que esa acción ya
  mueva los archivos?
- En el asistente, ¿lee que «En este paso no se crea ninguna serie ni se vincula ningún archivo»
  (`src/zascarr/web/templates/asistente_carpeta.html:6`)? ¿Sabe que el siguiente paso es elegir o
  buscar la serie, no que los archivos ya estén organizados?
- Si la lista está filtrada por una serie, la acción es «Preparar los archivos de esta carpeta para
  esta serie» (`carpetas.html:166`); observa si entiende la diferencia.

**Criterios.**

| Resultado | Qué se registra |
|---|---|
| **Sin ayuda** | Encuentra la carpeta, lee su estado sin creer que está aplicado y abre el asistente; dice que el siguiente paso es elegir/buscar la serie y que todavía no se ha movido nada |
| **Con ayuda** | Necesita que le indiques «Revisar por carpeta» o el filtro; después encuentra la carpeta y entiende el siguiente paso |
| **Fallo** | No encuentra la carpeta; cree que la sugerencia ya está aplicada y que los archivos ya están organizados; espera que «Elegir la serie…» mueva los archivos |
| **Abandono** | Deja la tarea o pide pasar |

**Qué NO se debe sugerir.** No digas «usa el filtro»; no digas «pulsa Revisar por carpeta»; no
digas «la sugerencia no está aplicada»; no expliques que el asistente no crea nada; no leas el
subtítulo del asistente. No le pidas que complete una búsqueda en fuentes: para T3 basta con que
sepa cuál sería el siguiente paso.

**Registra.** Cómo encontró la carpeta (lista, filtro, paginación), estado que leyó, acción que
eligió, si abrió el asistente y qué dijo que pasaría. Si no se abrió el asistente, anota por qué.

**Fuente.** `src/zascarr/web/templates/carpetas.html:62-64,156,166,169`;
`src/zascarr/services/revision_carpetas.py:50-52`;
`src/zascarr/web/templates/asistente_carpeta.html:6`;
`src/zascarr/web/asistente_carpetas.py:133`.

### T4 — Archivos sueltos

**Ruta.** `GET /ui/pendientes` → `GET /ui/pendientes/sueltos`
(`src/zascarr/web/pendientes.py:459`); la pantalla es
`src/zascarr/web/templates/sueltos.html:18-22`.

**Objetivo observable.** Que encuentre los sueltos, los distinga de los pendientes y entienda que
esa cola es solo lectura.

**Enunciado exacto.**

> «¿Dónde están los archivos que no pertenecen a ninguna carpeta? ¿Qué puedes hacer con ellos desde
> ahí?»

**Qué se observa.**

- ¿Encuentra «Ver los archivos sueltos» (`src/zascarr/web/templates/pendientes.html:16`) o intenta
  llegar por otro camino?
- ¿Lee el subtítulo «Solo lectura: desde aquí no se asigna, crea, mueve ni ignora nada. Para ignorar
  un pendiente, ábrelo en “Por revisar”» (`src/zascarr/web/templates/sueltos.html:19-20`)? ¿Sabe
  que para actuar tiene que volver?
- ¿Distingue «sueltos» de «pendientes»? ¿Entiende que los sueltos son un subconjunto de los
  pendientes y que esa cola no resuelve nada?
- ¿Lee el recuento «Sueltos X–Y de N · N de M por revisar»
  (`src/zascarr/web/templates/sueltos.html:21-22`)? ¿Se sorprende de que no haya acciones?

**Criterios.**

| Resultado | Qué se registra |
|---|---|
| **Sin ayuda** | Encuentra la cola, explica que son archivos sin carpeta de serie, lee que es solo lectura y sabe que para actuar debe volver a «Por revisar» |
| **Con ayuda** | Necesita una pista para encontrar el enlace o para entender «solo lectura»; después lo explica |
| **Fallo** | Cree que puede asignar, ignorar o mover desde ahí; confunde sueltos con carpetas; no rectifica tras la pista |
| **Abandono** | No lo encuentra y no quiere seguir |

**Qué NO se debe sugerir.** No digas «el enlace está debajo de Revisar por carpeta»; no digas «no se
puede hacer nada»; no digas «para ignorar, vuelve a Por revisar»; no expliques qué es un suelto
antes de que lo intente.

**Registra.** Cómo llegó, qué leyó, si distinguió sueltos de pendientes y qué dijo que se puede
hacer.

**Fuente.** `src/zascarr/web/templates/pendientes.html:16`;
`src/zascarr/web/templates/sueltos.html:19-22`; `src/zascarr/web/pendientes.py:459`.

### T5 — Qué hace organizar y qué pasará

**Ruta.** `GET /ui/pendientes` → tarjeta con sugerencia
(`src/zascarr/web/templates/_tarjeta_pendiente.html:14-45`) → vista previa
`GET /ui/pendientes/{file_id}/asignar/previa` (`src/zascarr/web/pendientes.py:632-644`) → confirmación
`POST /ui/pendientes/{file_id}/asignar` (`src/zascarr/web/pendientes.py:647-680`).

**Objetivo observable.** Que distinga la acción que solo abre la vista previa de la que mueve y
renombra, que lea el destino antes de confirmar y que sepa qué pasará al confirmar.

**Enunciado exacto.**

> «Sin pulsar nada todavía: mira las acciones de esta tarjeta. ¿Qué crees que hace cada una? Si
> quisieras dejar este archivo con su serie y su número, ¿qué harías y qué esperarías que pasara?»

Después de que actúe o llegue a la vista previa:

> «¿Qué crees que hace “Ver antes de organizar”? ¿Y qué pasará si sigues?»

Si ya está en la vista previa:

> «¿Qué hace exactamente “Confirmar y organizar”? ¿Qué cambiará en el archivo?»

Si la tarjeta muestra «Vincular en su sitio» (solo aparece si el archivo se puede vincular: fuera de
`_Unsorted` y no es un pack, `src/zascarr/web/pendientes.py:91-97`), añade: «¿Qué diferencia hay
entre esa acción y la otra?». Solo funciona si la publicación ya existe en la serie
(`_tarjeta_pendiente.html:29`). Si no aparece, no la menciones.

**Cómo se hace.**

- Empieza por una tarjeta con sugerencia («¿Es esta serie?»). Si el número está vacío, la persona
  tiene que escribirlo para que el formulario avance; observa si lo entiende.
- Deja que pulse «Ver antes de organizar» (`_tarjeta_pendiente.html:43`). La vista previa aparece
  **en la misma tarjeta**, debajo del botón (`hx-target="#previa-…"`,
  `_tarjeta_pendiente.html:36,45`), no en otra página. Si no la ve, observa si hace scroll.
- En la vista previa, observa si lee la nota «Organizar mueve y renombra el archivo. Antes verás la
  carpeta y el nombre final» (`_tarjeta_pendiente.html:41`), el título «Esto es lo que pasará si
  confirmas» (`_previa_asignacion.html:5`), los cuatro datos (serie, número, carpeta de destino,
  nombre final; `:7-10`) y la letra pequeña de que se copia, se verifica y se retira el original
  (`:12`).
- **Por defecto no se pulsa «Confirmar y organizar»** si se usan datos del PO. En la biblioteca de
  prueba se puede pulsar para observar el resultado; si se hace, anota antes y después y restaura.
- «Ignorar» (`_tarjeta_pendiente.html:60-65`) no forma parte de T5 salvo que la persona lo mencione;
  no lo pulses para probar. Si pregunta, no afirmes que se puede deshacer: no hay deshacer en esta
  pantalla.

**Qué se observa.** Si lee la nota antes del botón o solo después; si elige «Ver antes de
organizar» o «Vincular en su sitio»; si entiende que la vista previa **no ha movido nada**; si
nombra la carpeta de destino y el nombre final; si sabe que «Confirmar y organizar» es la acción con
efecto; si le sorprende que se retire el original; si el tamaño de la nota o el `title` hover le
impiden leerla (en táctil no hay hover).

**Criterios.**

| Resultado | Qué se registra |
|---|---|
| **Sin ayuda** | Distingue las acciones, lee la nota antes de pulsar, elige la vista previa, nombra serie/número/carpeta/nombre final y dice que «Confirmar y organizar» mueve y renombra; si «Vincular en su sitio» aparece, dice que no mueve |
| **Con ayuda** | Necesita que le señales la nota o el botón; después entiende y llega a la vista previa y sabe qué pasará |
| **Fallo** | Cree que organizar crea una serie, copia sin mover o solo vincula; elige «Vincular» esperando un movimiento; llega a la vista previa pero no sabe qué pasará al confirmar; o confirma sin poder decir el destino |
| **Abandono** | No quiere seguir con la tarea; se registra el motivo y, si no se ejecutó la confirmación, «no ejecutó»; no se cuenta como fallo automático |

**No ejecutado.** Si no se pulsa «Confirmar y organizar» (lo normal con datos del PO), se registra
«no ejecutado: confirmación» y no se cuenta como éxito ni como fallo. Si se pulsa en la biblioteca de
prueba, registra el resultado y el estado posterior.

**Qué NO se debe sugerir.** No digas «vista previa», «confirmación», «mueve», «renombra» ni «no
mueve»; no digas «pulsa Ver antes de organizar»; no leas la nota; no digas que «Vincular» es seguro;
no expliques la diferencia entre copiar y mover; no le digas que hay un paso de confirmación antes de
que lo vea; no prometas que se puede deshacer.

**Registra.** Acción elegida, si leyó la nota antes o después, si llegó a la vista previa, qué datos
nombró, qué dijo que pasaría al confirmar, si ejecutó y qué cambió. Cita literal de la frase que
muestre su modelo mental.

**Fuente.** `src/zascarr/web/templates/_tarjeta_pendiente.html:14-45,60-65`;
`src/zascarr/web/templates/_previa_asignacion.html:5,7-12,18`;
`src/zascarr/web/pendientes.py:632-644,647-680`.

### T6 — Carpeta con dos series o ambigüedad

**Ruta.** `GET /ui/pendientes/carpetas` (`src/zascarr/web/pendientes.py:397`) → tarjeta de la carpeta
(`src/zascarr/web/templates/carpetas.html:153-242`) → asistente
(`src/zascarr/web/asistente_carpetas.py:133`) y, si se sigue, revisión archivo a archivo
(`src/zascarr/web/asistente_vinculacion.py:420`, `_vinculacion_revision.html:244`). También puede
ir por `GET /ui/pendientes` y abrir cada tarjeta (`_tarjeta_pendiente.html:50`).

**Carpeta.** F-B, fijada antes de la sesión. Debe tener de verdad dos series o archivos que apunten a
dos series distintas; si no, el enunciado sería falso. Si no existe, se crea en la biblioteca de
prueba antes de la sesión.

**Objetivo observable.** Que detecte que la carpeta no es de una sola serie y encuentre una salida
que no aplique una única serie a todos los archivos, o que diga explícitamente que no usaría la
acción de carpeta.

**Enunciado exacto.**

> «Esta carpeta tiene archivos de dos series distintas. ¿Qué harías para no equivocarte?»

Si la ambigüedad no es «dos series» sino «candidatas distintas» o «títulos distintos», usa la
formulación verdadera: «Esta carpeta tiene archivos que no son todos de la misma serie. ¿Qué harías
para no equivocarte?».

**Qué se observa.**

- ¿Ve la ambigüedad en la tarjeta? El chip «en conflicto»
  (`src/zascarr/web/templates/carpetas.html:158`) y la señal «Los archivos del grupo sugieren N
  series distintas» (`src/zascarr/services/revision_carpetas.py:691`) o «La carpeta reúne N títulos
  distintos» (`:713`) están dentro de «Ver datos y observaciones»
  (`carpetas.html:186`). ¿Abre ese desplegable o se queda en la superficie?
- ¿Qué acción elige? La tarjeta ofrece una sola acción **principal**: «Elegir la serie de esta
  carpeta» (`carpetas.html:169`). ¿Entiende que elegir una serie no separa los archivos de la otra?
  ¿Espera que todos vayan a la misma?
- ¿Encuentra una vía por archivo? Puede volver a «Por revisar» y abrir cada tarjeta
  (`src/zascarr/web/templates/pendientes.html:39-43`), usar «Elegir otra serie»
  (`_tarjeta_pendiente.html:50`), o entrar en el asistente, elegir una serie y revisar/marcar solo
  los archivos que correspondan (`_vinculacion_revision.html:244`).
- ¿Inventa una acción que no existe («separar por series», «dividir la carpeta»)? Anótalo; no le
  sigas la corriente.
- Ojo con el filtro «Mezcla (sin serie y con serie sugerida)»
  (`carpetas.html:72`): **no** significa «dos series»; mezcla archivos sin serie y con serie
  sugerida (`src/zascarr/services/revision_carpetas.py:52`). No lo uses como pista ni lo confundas
  al registrar.

**Criterios.**

| Resultado | Qué se registra |
|---|---|
| **Sin ayuda** | Detecta que no todos los archivos son de la misma serie y elige una vía que no aplique una sola serie a todo: abrir las tarjetas en «Por revisar», o entrar al asistente y revisar/marcar solo los que correspondan. También es éxito decir «no usaría la acción de carpeta; iría archivo por archivo» |
| **Con ayuda** | Tras indicarle que mire «Ver datos y observaciones» o que vuelva a «Por revisar», encuentra una vía segura |
| **Fallo** | Pulsa «Elegir la serie de esta carpeta» esperando que todos los archivos vayan a una serie; inventa una acción de separar que no existe; o dice «no se puede» sin haber mirado las opciones |
| **Abandono** | Deja la tarea por miedo a equivocarse; se registra el motivo |

**Qué NO se debe sugerir.** No digas «abre Más opciones» ni «mira en Ver datos y observaciones»; no
digas «usa Por revisar»; no prometas un botón de «revisar uno a uno» desde la tarjeta (no existe); no
digas «usa el filtro Mezcla» (no es eso); no le expliques que el asistente vincula en su sitio.

**Registra.** Si detectó la ambigüedad, dónde la vio, qué acción eligió, si llegó a una vía por
archivo y qué dijo que pasaría con los archivos de la otra serie. Si se quedó bloqueado, registra la
frase y el punto exacto.

**Protección.** En modo PO, si llega a «Vincular N archivos» o a crear una serie, se aplica la
protección de §2.4: no se ejecuta, se dice antes de que pulse y se registra «no ejecutó».

**Fuente.** `src/zascarr/web/templates/carpetas.html:72,158,169,186`;
`src/zascarr/services/revision_carpetas.py:52,691,713`;
`src/zascarr/web/templates/_tarjeta_pendiente.html:50`;
`src/zascarr/web/asistente_vinculacion.py:420`;
`src/zascarr/web/templates/_vinculacion_revision.html:244`.

### T7 — Cierre y SEQ

**Ruta.** No hay una ruta nueva: se cierra en la pantalla donde esté la persona o se vuelve a
`/ui/pendientes` (`src/zascarr/web/templates/pendientes.html:4-6`) para que tenga delante lo que ha
usado. Si se ha llegado a la vista previa, se puede citar «Confirmar y organizar»
(`src/zascarr/web/templates/_previa_asignacion.html:18`) al preguntar por la confianza.

**Objetivo observable.** Recoger una valoración de facilidad (SEQ 1–7), lo primero que cambiaría y
qué le daría o quitaría confianza, sin defender el diseño.

**Enunciado exacto.**

> «En general, ¿qué tan fácil o difícil te ha resultado revisar pendientes con esta pantalla? Dame
> un número del 1 al 7, donde 1 es muy difícil y 7 es muy fácil.»

**Escala escrita (para leerla o mostrarla si hace falta).**

| Valor | Etiqueta |
|---|---|
| 1 | Muy difícil |
| 2 | Difícil |
| 3 | Algo difícil |
| 4 | Ni fácil ni difícil |
| 5 | Algo fácil |
| 6 | Fácil |
| 7 | Muy fácil |

**Qué se observa.** Si responde sin pedir aclaraciones o si necesita que le repitas la escala; si
usa los extremos o se queda en el centro; qué menciona primero como cambio; si su confianza se
refiere a la vista previa, al destino, al nombre final o al miedo a mover; si pregunta por sus datos
o por poder deshacer; si la valoración cambia al pensar en su propia biblioteca.

**Preguntas finales (en este orden).**

1. SEQ 1–7 y «¿por qué ese número?».
2. «¿Qué es lo primero que cambiarías o quitarías de esta pantalla?».
3. «¿Qué te haría confiar más (o menos) en la acción de organizar?» (si llegó a la vista previa, puedes
   nombrar «Confirmar y organizar»; si no, di «la acción de organizar»).
4. «¿Usarías esto con tu biblioteca? ¿Por qué?» (opcional).
5. «¿Hay algo que hayas querido hacer y no hayas podido?» (opcional).
6. «¿Algo más que quieras decir?» (abierta).

No preguntes «¿te gustó?», «¿verdad que es claro?» ni «¿qué te parece el diseño?». No defiendas la
decisión ni expliques por qué está así. Si pregunta si lo ha hecho bien: «No hay una forma correcta;
tu impresión es la que nos sirve».

**Criterios.**

| Resultado | Qué se registra |
|---|---|
| **Completado** | Da un número SEQ y al menos una respuesta a «qué cambiarías»; no hace falta que sea positiva |
| **Con ayuda** | Se le repite la escala o se le aclara que no hay respuesta correcta; se anota |
| **Fallo (no completado)** | No da SEQ ni responde a ninguna pregunta; no se fuerza |
| **Abandono** | Se retira antes del cierre; se registra lo que haya dicho |

T7 se registra como cierre (`tipo=cierre` en el registro); un SEQ bajo **no** es un fallo de la
persona ni de la pantalla. La tabla anterior describe cómo cerrar la sesión, no cómo puntuar a nadie.

**Qué NO se debe sugerir.** No sugieras un número; no digas «yo pondría un 5»; no justifiques la
pantalla; no le pidas que sea amable; no conviertas una queja en «bueno, pero…».

**Registra.** SEQ, motivo, primera cosa que cambiaría, confianza, uso y cualquier cita literal.

**Fuente.** `src/zascarr/web/templates/pendientes.html:4-6`;
`src/zascarr/web/templates/_previa_asignacion.html:18`.

## 5. Cierre de la sesión

Después de T7:

1. Agradece: «Muchas gracias. Lo que has dicho no se evalúa como acierto o error; nos ayuda a decidir
   qué corregir».
2. Explica qué se hará con las notas y cuándo se borran, según el
   [consentimiento](consentimiento-y-conservacion.md). Recuérdale que puede pedir el borrado.
3. Comprueba el estado: ¿se movió, ignoró o creó algo? Si sí, avisa al responsable para que
   restaure. No cierres la sesión sin saber en qué estado queda la biblioteca.
4. Guarda la hoja de sesión en el almacenamiento privado; no la subas al repositorio con nombres,
   rutas o capturas personales.
5. No interpretes todavía. Lo observado se separa de lo interpretado y se pasa a la hoja de registro
   del kit; las conclusiones se escriben después, con las demás sesiones.

## 6. Después de todas las sesiones

La hoja y las definiciones operativas están en [registro y análisis](registro-y-analisis.md); este
guion solo describe la sesión.

- Consolida por persona y tarea, sin convertir 3–5 casos en porcentajes.
- Separa **observado** (cita, acción, tiempo) de **interpretado** (hipótesis del moderador).
- Actualiza la ficha §13 con el material exacto, las fechas, el número de personas y las diferencias
  con la simulación.
- Si lo observado contradice la decisión G1 del 2026-10-21, abre una decisión nueva; no reescribas la
  historia ni conviertas la simulación en PASS humano.
- Solo entonces se puede decidir el cierre de #272. Este guion, por sí solo, no lo cierra.

## 7. Límites y honestidad

- **No es una muestra.** 3–5 personas reclutadas a mano no representan a «los coleccionistas»; no
  permiten tasas, medias poblacionales ni significación. Como mucho, «3 de 5 hicieron X», con la
  reserva del tamaño y del reclutamiento.
- **No es una comparación A/B.** Hay una sola app; no se pregunta preferencia de variante. Si se
  compara con los prototipos del 2026-10-21 o con la simulación del 2026-11-11, es otro material y
  no se mezcla.
- **No es accesibilidad conforme.** Lector de pantalla, texto grande, 360 px y teclado no forman
  parte del núcleo; si se prueban, es una sesión aparte y se declara.
- **No es rendimiento.** Los tiempos de tarea no son benchmarks de la Pi.
- **No es validación.** La validación exige sesiones reales registradas y ficha §13 actualizada; la
  decisión es del PO.

## 8. Referencias

- [README del kit](README.md) — índice, estado y criterio de cierre.
- [Reclutamiento](reclutamiento.md) — perfiles, exclusiones, invitación y sesgos de la muestra.
- [Consentimiento y conservación](consentimiento-y-conservacion.md) — qué se recoge, qué no, plazos y
  plantilla.
- [Registro y análisis](registro-y-analisis.md) — hoja por sesión y tarea, definiciones y límites.
- [Guion de la simulación](../guion-sesion.md) — base T1–T7 que este guion adapta.
- [Simulación #272 del 2026-11-11](../simulacion-272-2026-11-11.md) — hipótesis F1–F4, **no**
  resultados.
- [Decisión G1 del 2026-10-21](../decision-g1-2026-10-21.md) — ficha §13 y deuda de validación.
- [Resultados de la simulación U10](../resultados-simulacion.md) — contexto, no validación.
- [U13a — entrada por carpetas](../../ui-u13/u13a-entrada-por-carpetas.md) y
  [U13b — cola de sueltos](../../ui-u13/u13b-cola-de-sueltos.md) — contratos que la sesión observa.
- [Checklist del moderador](checklist-moderador.md) — comprobaciones del día.

Las rutas de código se citan relativas a la raíz del repositorio (`src/…`). Si una línea no coincide
porque el código cambió, prevalece el código actual: actualiza la cita antes de usar el guion.
