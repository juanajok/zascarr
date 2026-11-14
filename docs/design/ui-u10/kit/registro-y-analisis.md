# Registro y análisis para la validación de «Por revisar» (#272)

> **Estado: instrumento preparado. Sesiones con personas: NOT RUN.**
>
> Este documento **no contiene resultados** y **no acredita #272 ni U10**. Es la hoja con la que se
> registran y analizan las sesiones reales. Mientras no haya personas, fechas, consentimientos y una
> ficha §13 actualizada, la validación sigue pendiente.
>
> Se usa con el [guion de la sesión real](guion-sesion-real.md), la
> [checklist del moderador](checklist-moderador.md), el
> [consentimiento y conservación](consentimiento-y-conservacion.md) y el
> [reclutamiento](reclutamiento.md). El [piloto del instrumento](piloto-tecnico-2026-11-14.md)
> contiene filas **sintéticas** que prueban que esta hoja se puede rellenar; no son datos de nadie.

## 0. Reglas de oro

1. **Sin personas no hay validación.** Un documento, una simulación o una prueba automática no
   sustituyen a una sesión real.
2. **Una sola versión.** Esta ronda prueba la **app real** de «Por revisar», no los prototipos A/B.
   No hay preferencia A/B ni orden de variantes; lo que se alterna, si hay dos equivalentes, es la
   carpeta de ejemplo (F-A / F-B). Ver [guion §1.1](guion-sesion-real.md#11-una-sola-versión-la-app-real).
3. **Lo que no se preguntó queda NOT RUN.** No se rellena por inferencia ni se deduce del guion.
4. **Observación no es recomendación.** Primero se describe lo que pasó; después se propone. Nunca
   al revés.
5. **Con 3–5 personas se cuenta personas, no tareas.** «3 de 5» es un recuento, no una tasa
   poblacional.
6. **Nada de datos personales en el repositorio.** Ni nombres, ni correos, ni rutas, ni nombres de
   archivos o carpetas de la biblioteca. Ver [§8](#8-conservación-y-anonimización).
7. **El efecto se verifica aparte del resultado.** Que la persona haga lo correcto no garantiza que
   la app haya hecho lo correcto.

## 1. Antes de la primera sesión

No se empieza hasta que todo esto esté hecho y anotado:

- [ ] **Material y entorno congelados**: SHA o imagen, navegador, sistema, ancho, zoom, tema y modo
      de datos. Se anotan en la hoja S y en la ficha privada de la checklist.
- [ ] **Criterios de éxito copiados literalmente** del guion a la tabla de [§5.7](#57-criterios-de-éxito-por-tarea).
      Si algo no está claro, se resuelve **antes** de la primera persona, no durante.
- [ ] **Moderador formado** con los casos de [§5.8](#58-calibración-de-moderadores) y el
      [piloto §4](piloto-tecnico-2026-11-14.md#4-casos-de-calibración). Si hay una segunda persona,
      se calibra también y debe coincidir en los 12; **si solo hay una, se declara el límite** y otra
      persona revisa las citas y la clasificación.
- [ ] **Consentimiento y conservación** leídos. Cada persona tiene su `P1…P5`, su `S01…S05` y su
      referencia `C-01…`. La línea de «preferencia A/B» del consentimiento **no se usa** en esta
      ronda (guion §1.1); se adapta antes de firmar.
- [ ] **Hoja de cálculo preparada** con dos pestañas (sesiones y tareas) y los CSV de §4 importados.
- [ ] **Ficha privada de sesión** preparada con la checklist: URL, nombres exactos de las carpetas,
      borrado y mapa seudónimo → identidad. Esa ficha **no** se sube al repositorio.
- [ ] **Ensayo del montaje** (entorno, grabación, audio, borrado, restauración) hecho con la
      [checklist](checklist-moderador.md). Este registro no lo cubre.

Si falta una casilla, la sesión no empieza.

## 2. Hoja S — una fila por sesión

Una fila por persona y sesión. Una sesión **cancelada** también lleva fila (con `estado=cancelada` y
sin filas de tarea). Una sesión **retirada** conserva las filas de las tareas ya hechas y se marca
`estado=retirada`.

| `sesion` | `seudonimo` | `fecha` | `dispositivo` | `ancho_px` | `modo_datos` | `version_ui` | `duracion_min` | `estado` |
|---|---|---|---|---|---|---|---|---|
| `S01` | `P1` | `AAAA-MM-DD` | `portatil` | `1440` | `prueba` | `...` | `60` | `realizada` |

Diccionario de la hoja S:

| Columna | Qué se escribe | Valores admitidos |
|---|---|---|
| `origen` | Si la fila es real o de prueba | `real`, `sintetico` |
| `hora_inicio` | Hora local con zona, si importa | `HH:MM` o vacío |
| `modalidad_sesion` | Cómo se hizo | `presencial`, `videollamada` |
| `dispositivo` | Tipo de dispositivo | `portatil`, `tablet`, `movil`, `escritorio` |
| `ancho_px` | Ancho del viewport en píxeles CSS | entero |
| `navegador` | Navegador y versión del entorno congelado | texto corto o `n/d` |
| `version_ui` | SHA corto o imagen exacta de la app | texto corto o `n/d` |
| `duracion_min` | Minutos de la sesión completa | entero o `n/d` |
| `tema` | Tema con el que se probó | `claro`, `oscuro` |
| `modo_datos` | De dónde salen los datos | `prueba`, `po_solo_lectura` |
| `carpeta_t3` | Código de la carpeta de T3 | `F-A`, `F-A2`, `—` |
| `carpeta_t6` | Código de la carpeta de T6 | `F-B`, `F-B2`, `—` |
| `carpetas_sinteticas` | Qué carpetas de ejemplo son sintéticas | `ninguna`, `t3`, `t6`, `ambas` |
| `total_inicial` | Total de pendientes visible al empezar | entero o `n/d` |
| `carpetas_inicial` | Número de carpetas visible al empezar | entero o `n/d` |
| `import_rescan` | Si había importación o rescan en marcha | `si`, `no`, `no consta` |
| `consentimiento` | Modalidad del consentimiento | `firma`, `verbal`, `n/a` |
| `ref_consentimiento` | Referencia del original privado | `C-01`… o `—` |
| `grabacion` | Qué se autorizó y se grabó | `ninguna`, `audio`, `pantalla`, `audio+pantalla` |
| `moderador` | Código de quien modera | `M1`, `M2`… |
| `observador` | Código de quien observa o revisa | `M1`, `M2`… o `—` |
| `banda_edad` | Banda, solo si la persona quiere decirla | `18-29`, `30-44`, `45-59`, `60+`, `no dice`; `n/a` solo en filas sintéticas |
| `banda_biblioteca` | Tamaño en banda, nunca el número exacto | `<100`, `100-999`, `1000+`, `no dice`; `n/a` solo en filas sintéticas |
| `conocia_diseno` | Si había visto el diseño o la app antes | `si`, `no`, `no dice`; `n/a` solo en filas sintéticas |
| `orden_efectivo` | Orden real de las tareas | `T1>T2>T3>T4>T5>T6>T7` o el que fue |
| `tareas_incidencias` | Tareas saltadas, repetidas o interrumpidas | texto corto o `ninguna` |
| `restauracion` | Si se restauró el estado de partida | `hecha`, `no_aplica`, `pendiente` |
| `incidencias` | Fallos del entorno, interrupciones, cambios de cifras | texto corto |
| `notas` | Notas de sesión, sin datos personales | texto corto |

**Estados**: `prevista`, `realizada`, `cancelada`, `retirada`, `piloto`. `piloto` está reservado para
`S00/P0` del ensayo; nunca se asigna a una persona.

**Reglas de la hoja S**:

- `S01` y `P1` se asignan al **agendar**, no al ejecutar. Si se cancela, el código no se reutiliza.
- El **nombre exacto** de las carpetas F-A/F-B se anota en la ficha privada de la checklist, no aquí.
  En el repositorio solo van los códigos `F-A`/`F-B` y si son sintéticas.
- La **URL**, el sistema, el zoom y la entrada (ratón/táctil/teclado) viven en la ficha privada; aquí
  solo se suben si explican una diferencia (por ejemplo, una sesión de teclado declarada como otra
  cosa). Si el zoom no era 100 %, se anota en `incidencias`.
- No se anota edad exacta, tamaño exacto de biblioteca de la persona ni su nombre real. Si no quiere
  decir la banda, se escribe `no dice`; no se estima.
- `duracion_min` es el reloj de la sesión completa; no tiene por qué coincidir con la suma de los
  tiempos de tarea.
- `restauracion` es obligatoria si hubo cualquier escritura: sin ella no se sabe si la siguiente
  persona parte del mismo estado.

## 3. Hoja T — una fila por tarea

Una fila por cada tarea presentada. El orden es fijo T1–T7; si se salta, repite o vuelve atrás, se
anota. No hay bloques por variante: hay una sola app.

| `sesion` | `seudonimo` | `orden` | `tarea` | `tipo` | `resultado` | `ejecucion` | `efecto` | `tiempo_s` | `errores` | `intervenciones` | `ayuda_tipo` | `seq` |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `S01` | `P1` | `1` | `T1` | `tarea` | `ES` | `no_aplica` | `no_aplica` | `5` | `0` | `0` | `N0` | `5` |

Diccionario de la hoja T:

| Columna | Qué se escribe | Valores admitidos |
|---|---|---|
| `origen` | Fila real o de prueba | `real`, `sintetico` |
| `carpeta` | Carpeta usada en T3/T6 | `F-A`, `F-B`, `F-A2`, `F-B2`, `—` |
| `pausa_s` | Segundos de interrupciones técnicas descontados | entero o `0` |
| `tiempo_tipo` | Qué clase de tiempo es | `tarea`, `exposicion`, `entrevista`, `no_medido` |
| `errores` | Episodios de error (ver §5.3) | entero (`0` si ninguno) |
| `intervenciones` | Ayudas que cuentan (`N1`/`N2` que ayudan, `N3`, `N4`) | entero (`0` si ninguna) |
| `seq` | Facilidad percibida (ver §5.5) | `1`–`7`, `4.5` o vacío |
| `error_tipos` | Tipos separados por `+`; vacío si no hay | `comprension`, `ejecucion`, `accion_peligrosa_evitada`, `accion_peligrosa_aplicada`, `contenido`, `ninguno` |
| `movimientos_accidentales` | Efectos de mover o renombrar aplicados sin querer | entero (`0` si ninguno) |
| `nudges` | N1/N2 que **no** orientaron ni cambiaron el camino | entero |
| `estado_final` | Dónde quedó la pantalla al acabar la tarea | `pendientes`, `carpetas`, `sueltos`, `asistente`, `previa`, `otra` |
| `cambio_estado` | Qué cambió en los datos, si cambió algo | `ninguno`, `movido`, `ignorado`, `creado`, `vinculado`, `otro` |
| `nota` | Qué pasó, sin interpretar y sin datos personales | texto corto |
| `cita` | Cita literal ya anonimizada, o vacía | texto entre comillas |

**Reglas de la hoja T**:

- `orden` es la posición real (1–7), no la prevista. Si se salta una tarea, queda su fila con el
  resultado que corresponda (`AB`, `NA` o `NE`) y el motivo en `nota`.
- `tipo=cierre` para T7: es una entrevista, no una tarea de éxito/fallo. Su `resultado` se registra
  con los criterios propios de T7 (`ES` = cierre completado, `EC` = con ayuda, `FA` = no completado,
  `AB` = retirada), su `seq` es el SEQ global y su `nota`, lo que cambiaría y la confianza. La matriz
  de tareas lo excluye y se informa aparte.
- `NA` es un valor, no un hueco. Un hueco significa «no se midió»; `NA`, «no era evaluable» y el
  motivo está en `nota`.
- `NE` es «no ejecutó»: la persona no realiza la acción observable y no hay respuesta evaluable.
  No es éxito ni fallo; se informa aparte. No se usa para una tarea de lectura.
- `movimientos_accidentales` cuenta **efectos de mover o renombrar aplicados**, no clics
  cancelados. Un clic peligroso cancelado se anota en `errores` con `accion_peligrosa_evitada`; un
  «Ignorar» aplicado sin querer, con `accion_peligrosa_aplicada`.
- `tiempo_s` se mide con cronómetro y se redondea a segundos enteros. No se estima «a ojo».

### 3.1 Mapa de tareas T1–T7

Los códigos son fijos. El **enunciado y el criterio literal** están en el
[guion §4](guion-sesion-real.md#4-tareas); esta tabla resume para clasificar y no sustituye al guion.
Si el guion cambia, manda el guion y se anota la versión.

| Código | Propósito (resumen) | Éxito operativo (resumen) | Efecto a verificar |
|---|---|---|---|
| **T1** | Primera impresión en 5 segundos: qué se puede hacer aquí | Dice para qué sirve y nombra una acción o un camino concreto | Ninguno (solo lectura) |
| **T2** | Cuántos hay y por dónde empezar | Da un total correcto y elige un primer paso visible | Ninguno |
| **T3** | Seguir la carpeta F-A | Encuentra la carpeta, lee su estado sin creerlo aplicado y dice el siguiente paso | Ninguno (abrir el asistente no mueve) |
| **T4** | Archivos sueltos | Encuentra la cola, distingue sueltos de pendientes y lee que es solo lectura | Ninguno |
| **T5** | Qué hace organizar y qué pasará | Distingue la vista previa de la acción con efecto, lee el destino y dice qué pasará | Si confirma en biblioteca de prueba: estado final |
| **T6** | Carpeta F-B con dos series o ambigüedad | Detecta la ambigüedad y elige una vía que no aplique una sola serie a todo | Ninguno, salvo que el guion pida ejecutar |
| **T7** | Cierre: SEQ global, qué cambiaría y confianza | Da SEQ y al menos una respuesta de cierre | Ninguno |

**Carpetas de ejemplo**: `F-A` es la carpeta de una serie clara para T3; `F-B` es la carpeta con dos
series o ambigüedad para T6. Si hay dos equivalentes, se alternan entre participantes y se registra
cuál se usó (`F-A`/`F-A2`, `F-B`/`F-B2`). El nombre exacto vive en la ficha privada. Si solo hay una,
se usa en todas las sesiones y se declara como límite.

## 4. CSV copiables

Dos bloques: uno por pestaña. Se cruzan por `sesion`; los datos de sesión (fecha, dispositivo,
duración) no se repiten en la hoja T. **Separador `;`** (el que suele esperar la hoja
de cálculo en español), UTF-8, una fila por registro y sin celdas combinadas. Los textos libres van
entre comillas dobles; los tiempos son enteros y los decimales, con punto (`4.5`).

> Copia solo la cabecera y añade las filas. No cambies el orden ni el nombre de las columnas: el
> análisis y las fórmulas cuentan con ellas. Las filas de ejemplo rellenas están en el
> [piloto](piloto-tecnico-2026-11-14.md#5-filas-sintéticas), no aquí.

**CSV S — sesiones**

```csv
origen;sesion;seudonimo;fecha;hora_inicio;modalidad_sesion;dispositivo;navegador;ancho_px;tema;version_ui;modo_datos;carpeta_t3;carpeta_t6;carpetas_sinteticas;total_inicial;carpetas_inicial;import_rescan;duracion_min;consentimiento;ref_consentimiento;grabacion;moderador;observador;estado;banda_edad;banda_biblioteca;conocia_diseno;orden_efectivo;tareas_incidencias;restauracion;incidencias;notas
```

**CSV T — tareas**

```csv
origen;sesion;seudonimo;orden;tarea;tipo;carpeta;resultado;ejecucion;efecto;tiempo_s;pausa_s;tiempo_tipo;errores;error_tipos;movimientos_accidentales;intervenciones;nudges;ayuda_tipo;estado_final;cambio_estado;seq;nota;cita
```

**Al importar**:

- En LibreOffice: *Hoja → Insertar hoja desde archivo* o pegar y usar *Texto en columnas* con
  separador `;`. En Excel: *Datos → Texto en columnas* con separador `;`.
- Si tu herramienta solo acepta comas, elige `;` en el asistente de importación; **no** sustituyas
  comas por puntos y comas a ciegas, porque las notas llevan comas y quedarían partidas.
- Una fila de tarea sin `sesion` no se puede cruzar. No dejes sesiones sin fila S.
- `origen=sintetico` se filtra siempre antes de analizar: el piloto no es una sesión.

## 5. Definiciones operativas

Estas definiciones existen para que cualquier moderador clasifique igual. Si hay duda, se resuelve
**antes** de la sesión con los casos de [§5.8](#58-calibración-de-dos-moderadores); no se improvisa
durante.

### 5.1 Resultado de la tarea

| Código | Nombre | Definición | No es |
|---|---|---|---|
| `ES` | Éxito sin ayuda | Alcanza el objetivo con el enunciado y nada más. Repetir la pregunta porque no la oyó **sigue siendo sin ayuda** | No significa «sin esfuerzo» ni «rápido» |
| `EC` | Éxito con ayuda | Alcanza el objetivo después de una ayuda que orienta o cambia el camino (`N1` que desbloquea, `N2` que orienta a un control, `N3`, `N4`) | No es «lo hizo el moderador»: si el moderador ejecuta, es `NA` |
| `FA` | Fallo | No alcanza el objetivo, o lo alcanza con una idea equivocada de lo que pasa: acción equivocada, cifra inventada, «no sé» tras la pista, o describe una acción que no existe y no rectifica | No es abandono |
| `AB` | Abandono | Pide pasar, se retira, o se agota el **tiempo máximo** de la tarea sin alcanzarlo | No es un «no sé» con la persona todavía en la tarea |
| `NE` | No ejecutó | La persona no realiza la acción observable y no hay respuesta evaluable (por ejemplo, no quiere pulsar nada en T5). No es éxito ni fallo | No es fallo automático ni abandono |
| `NA` | No evaluable | Falla el montaje, hay un error de protocolo, el moderador ejecuta la acción o la tarea no existe | No es un fallo de la persona ni de la pantalla |

Reglas finas:

- **Éxito con efecto incorrecto**: si la persona hizo lo correcto pero la app no aplicó el efecto, el
  resultado puede ser `ES`/`EC` y `efecto=incorrecto`. Es un **bug**, no un fallo de comprensión. Si
  el efecto salió mal por una acción equivocada de la persona, es `FA` y `efecto=incorrecto`.
- **Miedo a mover en T5**: no se empuja. Si no pulsa nada y explica por qué, se registra `NE` y el
  motivo; no es fallo automático. Si llega a la vista previa y explica qué pasará, es `ES`/`EC`
  aunque no confirme: se registra `ejecucion=no` y `efecto=no_verificado`.
- **Miedo en T6**: el guion lo considera **abandono** (`AB`) si deja la tarea por miedo a
  equivocarse. Se anota el motivo. La misma conducta se clasifica distinto según la tarea; no se
  unifica a ciegas.
- **Tiempo máximo agotado**: `AB`, con `nota="tiempo máximo"`. El guion lo llama abandono; no se
  convierte en `FA`.
- **Corte por fallo técnico**: `NA`, con `nota="incidencia técnica"`. Se salta y no se cuenta como
  fallo de la persona.
- **Recorte del protocolo** (por ejemplo, T4 porque el tiempo aprieta): `NA`, con
  `nota="recorte del protocolo"`. No es `AB`: no lo pidió la persona.
- **Tarea saltada por la persona**: `AB` en esa tarea, con motivo.
- **Moderador ejecuta** (`N5`): `NA`, `ayuda_tipo=N5`, nota «moderador ejecutó». No es éxito de la
  persona.
- **Retirada de la sesión**: se aplica §8; no se rellena el resto y se actualiza el `n`.

### 5.2 Ayuda: qué cuenta y qué no

La escalera es la del [guion §3.2](guion-sesion-real.md#32-escalera-de-ayuda). Se empieza sin ayuda y
solo se sube un peldaño cuando la persona lleva un tiempo sin progresar. Se anota la **frase exacta**.

| Nivel | Qué dices o haces | ¿Cuenta como ayuda? | Dónde se registra |
|---|---|---|---|
| `N0` | Nada; esperas y mantienes una cara neutra | **No** | `ayuda_tipo=N0` |
| `N1` | «¿Qué estás pensando?» / «¿Qué esperabas encontrar?» | **No** por defecto; **sí** si desbloquea o cambia el camino | `nudges` si no; `intervenciones` y `ayuda_tipo=N1` si sí |
| `N2` | «¿Hay algo en la pantalla que te ayude a decidir?» | **No** si no orienta a un control concreto; **sí** si lo hace | `nudges` si no; `intervenciones` y `ayuda_tipo=N2` si sí |
| `N3` | «Mira la zona de arriba / el enlace de la izquierda» | **Sí** | `intervenciones`, `ayuda_tipo=N3` |
| `N4` | «Pulsa “X”» | **Sí** | `intervenciones`, `ayuda_tipo=N4` |
| `N5` | Lo haces tú | **No es éxito de la persona** | `resultado=NA`, `ayuda_tipo=N5`, nota «moderador ejecutó» |

- **Repetir la pregunta porque no la oyó** no es ayuda. Repetir el enunciado **literal** hasta dos
  veces tampoco; una **paráfrasis** sí cuenta (`N1`/`N2`).
- **N1** es método, no ayuda **por defecto**. Si con esa pregunta la persona cambia de camino o se
  desbloquea, sí cuenta como ayuda (`N1`) y el resultado es `EC` (el guion T1 lo llama «con ayuda»).
  Si no cambió nada, se registra como `nudge` y el resultado no cambia.
- **N2** es ambiguo a propósito: si la pregunta le lleva a un control concreto que no había
  considerado, cuenta; si sigue explorando sin destino, no. En caso de duda, se marca «orientó» si
  después usa un control concreto que antes no había nombrado.
- **Diferencia declarada con el guion**: el criterio general del guion dice «con ayuda» para niveles
  3–4; T1 y la escalera permiten que `N1`/`N2` cuenten si desbloquean u orientan. Esta hoja aplica la
  regla específica (`N1`/`N2` solo si cambian el camino u orientan a un control) y lo deja escrito.
  Si el guion se corrige, manda el guion. Se calibra con los casos C2–C5.
- **N3/N4** siempre cuentan. No señales con el dedo ni con el ratón antes de `N3`; si lo haces, es
  ayuda.
- **Después de cualquier ayuda**: pregunta «¿qué crees que ha pasado?» y sigue contando `EC` aunque
  la persona lo entienda después. La ayuda no se «descuenta».
- **No uses las palabras objetivo antes que la persona**: «vista previa», «confirmación», «mueve»,
  «renombra», «no aplicada», «mezcla». Si la persona las usa, puedes repetirlas.
- **Asistencia técnica no es ayuda**: zoom, teclado, reconectar el audio, cambiar de dispositivo o
  arreglar la videollamada. Se anota en `nota` como `asistencia_tecnica` y no cambia el resultado.
  Si el moderador toca la app para enseñar una zona, ya es `N3`; si ejecuta la tarea, `NA`.
- **Silencio, asentir o animar** no cuentan. Solo cuenta lo que se dice, se señala o se opera.
- **Ayuda de una tarea anterior**: si la persona aplica lo aprendido sin nueva ayuda, sigue siendo
  `ES`; se anota «arrastre de aprendizaje» en `nota`.
- **Ayuda después de terminar** (en el cierre): no cuenta para esa tarea; se anota si revela algo.

### 5.3 Errores y movimientos accidentales

- **Error**: acción o interpretación que no coincide con la tarea o con el modelo de la pantalla y
  que produciría un resultado no deseado si se confirmara. Incluye decir con seguridad algo falso
  sobre el efecto.
- **No es error**: dudar, preguntar, explorar sin comprometerse, leer en voz alta, elegir otro camino
  válido o pedir ayuda. La ayuda se registra aparte.
- Se cuentan **episodios**. El mismo error repetido sin información nueva cuenta una vez y se anota
  «x2» en `nota`. Dos errores distintos cuentan dos.
- `error_tipos` admite varios separados por `+`: `comprension`, `ejecucion`,
  `accion_peligrosa_evitada`, `accion_peligrosa_aplicada`, `contenido`, `ninguno`.
- **Movimiento accidental**: efecto de mover o renombrar que **se aplicó** sin que la persona lo
  quisiera. Un clic peligroso cancelado en la confirmación **no** es movimiento: se anota como error
  `accion_peligrosa_evitada` y `movimientos_accidentales` sigue a `0`.
- **«Ignorar» aplicado sin querer**: no es un movimiento; se anota `errores=1`,
  `error_tipos=accion_peligrosa_aplicada` y en `nota` (no hay deshacer en esta pantalla).
- Un fallo del sistema no es un error de la persona: se registra en `efecto` y se abre un issue.

### 5.4 Tiempo: inicio, parada y pausas

| Momento | Regla |
|---|---|
| **Inicio** | Al terminar de leer el enunciado, con la pantalla ya visible |
| **Fin** | Cuando la persona responde o actúa; en T5, hasta la vista previa si no confirma |
| **Pausa** | Solo interrupciones técnicas (llamada, fallo del dispositivo, audio). Se descuenta en `pausa_s` |
| **Pensar, leer, desplazarse o recibir ayuda** | **No** se pausa: forma parte de la tarea y del tiempo |
| **45 s sin progreso** | `N1` («¿qué estás pensando?» / «¿qué esperabas encontrar?»). No para el reloj |
| **90 s sin progreso** | `N3` (pista de zona) y marca «con ayuda». No para el reloj |
| **2 min sin progreso** | Se ofrece pasar a la siguiente tarea. Si acepta, `AB` con motivo; si sigue, hasta el máximo |
| **Tiempo máximo** | T2: 3 min; T3: 6; T4: 3; T5: 8; T6: 8. Al agotarlo sin alcanzar, `AB` con `nota="tiempo máximo"` |
| **T1 de 5 s** | Exposición fija: `tiempo_s=5`, `tiempo_tipo=exposicion`. No es tiempo de tarea ni se compara |
| **T7 (cierre)** | `tiempo_tipo=entrevista`; el tiempo es opcional y no se compara |
| **Redondeo** | Segundos enteros. Si pasa de 5 minutos, se anota fatiga en `nota` |

- Los tiempos **no** se comparan entre personas ni entre dispositivos. Se describen rangos; una
  mediana solo si hay al menos 3 medidas y se dice que es descriptiva.
- **T5** se para en la vista previa si no se confirma; si se confirma en la biblioteca de prueba, se
  para cuando termina la acción.
- **Fallo técnico**: se para el cronómetro, se anota `pausa_s`, y si bloquea la tarea se marca `NA`,
  no `FA`.

### 5.5 SEQ (facilidad percibida)

- Escala **1–7**: **1 = muy difícil**, **7 = muy fácil**. Se lee o se muestra la escala del
  [guion §4](guion-sesion-real.md#t7--cierre-y-seq) si hace falta.
- Se pregunta **después de cada tarea** y, en T7, en general («¿qué tan fácil o difícil te ha
  resultado revisar pendientes con esta pantalla?»).
- Se registra el número tal cual. Si la persona duda entre 4 y 5, se admite `4.5` y se anota. Si no
  se preguntó o lo declina, se deja **vacío**; nunca se pone `0` ni se deduce del tiempo.
- Un SEQ alto no borra un fallo, y un SEQ bajo no convierte un éxito en fallo: son datos distintos.

### 5.6 Efecto verificado

| Valor | Qué significa |
|---|---|
| `correcto` | El estado final coincide con el criterio de éxito (vinculado donde debía, sin mover, marcas conservadas…) |
| `incorrecto` | El estado final no coincide: se movió, se vinculó mal, se perdió una marca, se duplicó una decisión |
| `no_verificado` | La tarea no pedía efecto, no se confirmó o no se pudo comprobar (prototipo estático, sin acceso al estado) |
| `no_aplica` | No hay efecto posible (T1, T2, T4, T6, T7) |

El efecto lo comprueba el observador o el moderador **en la pantalla o en el estado de la app**, no
por lo que la persona cree. Si no se puede comprobar, `no_verificado`; no se supone.

`ejecucion` es distinto de `efecto`: dice si se llegó a pulsar la acción con efecto (`si`), si no
(`no`), si el guion no pedía ejecutarla (`no_requerida`, por ejemplo con datos del PO) o si no hay
acción (`no_aplica`).

### 5.7 Criterios de éxito por tarea

Antes de la primera sesión se copia el criterio **literal** del [guion §4](guion-sesion-real.md#4-tareas)
y se versiona la hoja. Después no se cambia.

| Tarea | Éxito (resumen operativo) | Fallo (resumen operativo) |
|---|---|---|
| T1 | Dice para qué sirve y nombra una acción o un camino concreto | Solo lee el título, dice «no sé / no entiendo», o describe una acción que no existe y no rectifica |
| T2 | Da un total correcto y elige un primer paso visible | No encuentra ningún total, da una cifra inventada o elige una acción que no existe; no se corrige tras la pista |
| T3 | Encuentra F-A, lee que la sugerencia no está aplicada y dice que el siguiente paso es elegir/buscar la serie | No encuentra la carpeta; cree que ya está aplicada y organizada; espera que «Elegir la serie…» mueva los archivos |
| T4 | Encuentra la cola, explica que son archivos sin carpeta, lee «solo lectura» y sabe que debe volver para actuar | Cree que puede asignar, ignorar o mover desde ahí; confunde sueltos con carpetas; no rectifica |
| T5 | Distingue las acciones, lee la nota antes de pulsar, llega a la vista previa y nombra serie/número/carpeta/nombre final; dice que «Confirmar y organizar» mueve y renombra | Cree que organizar crea una serie, copia sin mover o solo vincula; elige «Vincular» esperando un movimiento; confirma sin poder decir el destino |
| T6 | Detecta que no todos los archivos son de la misma serie y elige una vía que no aplique una sola serie a todo (o dice «no usaría la acción de carpeta») | Pulsa «Elegir la serie de esta carpeta» esperando que todos vayan a una; inventa una acción de separar que no existe; dice «no se puede» sin mirar opciones |
| T7 | Da un número SEQ y al menos una respuesta a «qué cambiarías» | No da SEQ ni responde a ninguna pregunta; no se fuerza |

**Criterios de la escalera**: `EC` cuando el objetivo se alcanza tras `N1` que desbloquea, `N2` que
orienta, `N3` o `N4`. `N5` no es éxito de la persona (`NA`). Para T5, si no se confirma, se registra
`ejecucion=no` y `efecto=no_verificado`; no convierte el éxito de comprensión en `NE`.

**T5 y el orden de lectura**: el guion pide «lee la nota antes de pulsar». Si la persona la lee
después pero entiende el destino, se clasifica por la comprensión final (`ES`/`EC` según la ayuda) y
se anota «leyó después» como observación. El orden de lectura es una fricción de diseño, no un fallo
de la persona; se lleva a la ficha y se calibra con el caso C8 del piloto.

**T5 y el «no ejecutado: confirmación»**: cuando la persona no confirma (lo normal con datos del PO),
se registra en `ejecucion` (`no` o `no_requerida`) y `efecto=no_verificado`; no se pierde el
resultado de comprensión. Solo se usa `resultado=NE` si no hay respuesta evaluable (por ejemplo, no
quiere pulsar nada y no explica su modelo).

### 5.8 Calibración de moderadores (si hay más de uno)

1. Antes de la primera sesión, `M1` y `M2` clasifican **por separado** los 12 casos del
   [piloto §4](piloto-tecnico-2026-11-14.md#4-casos-de-calibración).
2. Comparan resultado, `ejecucion`, efecto, nivel de ayuda, errores y movimiento accidental.
3. Deben coincidir en **12 de 12**. Si no, se discute el caso, se escribe la regla que faltaba y se
   repite con casos nuevos hasta que coincidan.
4. Durante el análisis, si hay dos codificadores, codifican **todas** las sesiones por separado (son
   pocas) y resuelven las diferencias hablando. Si solo hay un moderador, otra persona revisa la
   clasificación y las citas; se declara «moderador único» como límite.

## 6. Análisis

### 6.1 Preparación

- Transcribir y ordenar las notas **el mismo día** o el siguiente, mientras el recuerdo es fresco.
- Anonimizar en el momento de pasar a la hoja: sin nombres, rutas, correos ni nombres de archivos.
- Congelar una copia fechada del CSV antes de analizar. Los cambios posteriores van en una copia
  nueva; no se edita la copia congelada.
- Revisar que cada fila de tarea tiene su fila de sesión y que `origen=real` en todo lo que se
  analiza. El piloto (`origen=sintetico`) se filtra.
- Contar el **n presentado por tarea**: personas con consentimiento, sesión `realizada` y tarea
  presentada. `NA` no entra. Para el recuento de **éxito/fallo**, el denominador es `ES+EC+FA`;
  `AB`, `NE` y `NA` se informan aparte, pero `AB` y `NE` **sí cuentan** para detectar una fricción
  (son personas que se enfrentaron a la tarea).

### 6.2 Codificación temática

**Unidad de análisis**: una observación, no una frase suelta. Una observación es «lo que hizo o dijo
una persona en una tarea», con evidencia (acción, cita o ambas).

**Procedimiento**:

1. **Primera pasada, abierta**: leer las notas y anotar observaciones con un código provisional.
2. **Segunda pasada, consolidada**: agrupar códigos parecidos, definir cada uno y conservar los casos
   que lo contradicen (no solo los que lo apoyan).
3. **Recuento por persona**: una persona cuenta una vez por hallazgo, aunque lo muestre en dos
   tareas. Se anotan las tareas donde aparece.
4. **Casos negativos**: buscar explícitamente a quienes **no** tuvieron el problema. Sin ellos, el
   análisis solo ve lo malo.
5. **Ruido del instrumento aparte**: fallos técnicos, ayuda del moderador, orden de tareas,
   dispositivo o familiaridad van al código `C10`, no a un hallazgo de diseño.

**Codebook de partida** (se ajusta con lo observado; los códigos nuevos se añaden y se definen):

| Código | Qué agrupa | Ejemplo de observación (formato, no dato) |
|---|---|---|
| `C1` | Comprensión de la acción: qué hace, si mueve, crea o vincula | «Pregunta si el botón mueve el archivo antes de pulsarlo» |
| `C2` | Entrada y alcance: por dónde empezar, página frente a total | «Busca el total en la cabecera y no lo encuentra» |
| `C3` | Confianza y miedo: a mover, a perder, a duplicar | «Dice que no lo pulsa sin confirmación» |
| `C4` | Recuperación y continuidad: guardar, reanudar, deshacer, recibo | «No encuentra cómo volver a la revisión de ayer» |
| `C5` | Vocabulario: términos que no se entienden | «Pregunta qué es un pack» |
| `C6` | Estado y feedback: sabe qué pasó después de actuar | «No sabe si la marca se guardó» |
| `C7` | Accesibilidad y dispositivo: foco, teclado, lector, tamaño, barra | «El foco vuelve al principio tras marcar» |
| `C8` | Esfuerzo y carga: repetición, páginas, tiempo percibido | «Se cansa de repetir la misma acción» |
| `C9` | Casos límite del contenido: pack, conflicto, especial, suelto | «No encuentra salida para dos series en una carpeta» |
| `C10` | Ruido del instrumento: fallo técnico, ayuda, orden, dispositivo | «La vista previa no cargó; se marcó NA» |
| `C-new` | Código emergente: se define al aparecer | — |

**Reglas de codificación**:

- No se codifican estados mentales inferidos («no entiende») sin conducta observable. Se escribe lo
  que hizo o dijo: «pregunta qué hace», «pulsa el botón equivocado», «no menciona el total».
- Una cita no es una conclusión. La cita va con la observación; la interpretación va separada.
- No se mezclan tareas en un mismo código sin decirlo: `tarea` y `orden` acompañan a cada
  observación.

### 6.3 Matriz tarea × participante

Cada celda: `resultado · tiempo_s · SEQ`. `—` = no registrado; `NE` = no ejecutó; `NA` = no
evaluable; `AB` = abandono.

| Tarea | P1 | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|
| T1 |  |  |  |  |  |
| T2 |  |  |  |  |  |
| T3 |  |  |  |  |  |
| T4 |  |  |  |  |  |
| T5 |  |  |  |  |  |
| T6 |  |  |  |  |  |

**T7 (cierre)** no entra en la matriz de tareas: se informa aparte con su SEQ global, lo que la
persona cambiaría y su confianza. Si se quiere, se añade una fila `T7` a una tabla de cierre, pero no
se mezcla con los recuentos de éxito/fallo de T1–T6.

Debajo, la tabla de recuentos:

| Tarea | n presentado | ES | EC | FA | AB | NE | NA | Efectos incorrectos | Movimientos accidentales |
|---|---|---|---|---|---|---|---|---|---|
| T1 |  |  |  |  |  |  |  |  |  |
| … |  |  |  |  |  |  |  |  |  |

Se informa siempre de `n` y de los recuentos crudos. Un «3 de 5» es suficiente; un «60 %» sin `n` y
sin decir que es descriptivo, no.

### 6.4 Detección de patrones

**Cuándo algo es un hallazgo**:

- **Mínimo 3 personas distintas** y **al menos el 60 % del n presentado** (el de la tarea, sin `NA`).
  Con 3 personas: 3 de 3; con 4: 3 de 4; con 5: 3 de 5. Una sola persona **nunca** es un hallazgo;
  dos son una **señal** para vigilar, no un patrón. `AB` y `NE` cuentan como personas que vivieron la
  tarea; no se esconden fuera del denominador.
- Al menos **una instancia sin ayuda** (salvo que el hallazgo sea justamente «necesitan ayuda»; en ese
  caso se etiqueta como tal).
- **No explicado por el instrumento**: no es un fallo técnico, ni una ayuda del moderador, ni el
  efecto del orden, ni del dispositivo. Si hay duda, se marca «por confirmar» y se revisa.
- **Conducta observable**, no una impresión del moderador. La impresión se marca como tal y no cuenta
  para el umbral.
- **Persona, no tarea**: si la misma persona muestra lo mismo en T3 y T6, cuenta una vez.

**Severidad propuesta** (se puede ajustar antes de la sesión, no después):

| Nivel | Criterio | Qué implica |
|---|---|---|
| Alta | Bloquea la tarea a ≥3 personas, o produce un efecto peligroso aunque sea una vez | Corrección antes de seguir; decisión si cambia el contrato |
| Media | ≥3 personas necesitan ayuda o cometen el mismo error, pero completan | Corrección de copy, jerarquía o flujo |
| Señal | 2 personas | Vigilar; no se presenta como hallazgo |
| Anécdota | 1 persona | Anexo con cita; no se generaliza |

**Contradicción de una hipótesis**: si **≤1 persona** muestra el problema y **≥3 completan sin ayuda**,
la hipótesis no se sostiene en esta muestra. Si son **2**, queda **sin decidir**: no se cuenta como
confirmación ni como refutación. Una hipótesis que no se reproduce también se documenta: saber que H1
no apareció es un resultado útil.

**Una sola versión**: no hay comparación A/B. Si se compara con los prototipos del 2026-10-21 o con
la simulación del 2026-11-11, es **otro material** y no se mezcla. La preferencia A/B no se pregunta
en esta ronda.

**Bugs de efecto**: un `efecto=incorrecto` es un bug aunque solo ocurra una vez. No se espera a tener
3 personas para abrir un issue; lo que no se hace es llamarlo «hallazgo de comprensión».

### 6.5 Observación y recomendación, separadas

**Observaciones** (lo que pasó):

| ID | Tarea | Personas | Observación (conducta) | Cita | Código | Evidencia | Confianza |
|---|---|---|---|---|---|---|---|
| O1 |  | `3 de 5` |  |  | `C1` |  | alta / media / baja |

**Recomendaciones** (lo que se propone hacer):

| ID | Observación que la origina | Recomendación | Tipo | Coste | Riesgo | Decide | Estado |
|---|---|---|---|---|---|---|---|
| R1 | O1 |  | adoptar / adaptar / descartar / medir más | S/M/L |  | PO | propuesta |

Reglas:

- **Sin O no hay R.** Toda recomendación cita la observación que la origina.
- **Sin evidencia no hay O.** La observación lleva conducta, cita o ambas, y el recuento de personas.
- La observación **describe**, no evalúa: «no encuentra el total» en vez de «la pantalla es
  confusa». Lo segundo es una interpretación y va en la recomendación o en la hipótesis.
- La recomendación es una **propuesta**, no una decisión. Decide el PO y se registra en la ficha §13.
- Se documenta también **lo que se mantiene**: qué evidencia apoya no cambiar nada. Un análisis que
  solo propone cambios no es un análisis, es una lista de deseos.
- Formato de ejemplo (no es un dato): «O-EJ: 3 de 5 buscan el total en la cabecera y no lo
  encuentran. R-EJ: subir el desglose y repetir la prueba con 3 personas». Se marca como ejemplo.

### 6.6 Criterios pre-registrados

- Los criterios de éxito se copian del guion **antes** de la primera sesión y se versionan. No se
  mueven después de ver los datos.
- Si se cambia un criterio después, se etiqueta **post hoc** y no sirve para confirmar nada; se
  explica por qué cambió.
- **Un criterio que exige una línea base no se puede evaluar sin ella.** Por ejemplo, «reducir un
  30 % el tiempo hasta la primera decisión frente a la versión anterior» exige haber medido la
  versión anterior con el mismo instrumento. Si no existe esa medida, el criterio queda **NOT RUN**;
  no se calcula un porcentaje contra un recuerdo.
- **Con n pequeño, un criterio del tipo «5 de 5» es frágil**: una sola persona lo cambia. Se informa
  del recuento exacto y de esa fragilidad; no se convierte en una tasa.
- Si se reutiliza el kit anterior del 2026-11-13, sus criterios (5/5, 4/5, cero movimientos, −30 %)
  se copian tal cual y **no se mezclan** con estas sesiones: un solo consentimiento y un solo
  registro por persona, según el [README del kit](README.md#6-material-relacionado).

### 6.7 Qué debe llevar siempre el análisis

- `n` real y por tarea, con seudónimos.
- Matriz por persona, no solo totales.
- Ayuda prestada y su nivel; no se presenta un `EC` como autonomía.
- Efectos verificados y bugs, separados de la comprensión.
- Orden de tareas, modo de datos y dispositivo, porque explican diferencias.
- Fallos del instrumento, `NA` y `NE`.
- Límites y muestra de conveniencia ([§7.6](#76-cómo-declarar-la-muestra-y-los-límites)).
- Lo que queda **NOT RUN**.

## 7. Reglas de decisión para la ficha §13

### 7.1 Qué significa «actualizar la ficha §13»

1. **No se reescribe la historia.** La ficha
   [`decision-g1-2026-10-21.md`](../decision-g1-2026-10-21.md) conserva su §1–§7 como decisión de esa
   fecha. Se le añade una sección final, **§8 Evidencia posterior (AAAA-MM-DD)**, con: material exacto
   usado, `n`, diferencias con la simulación y enlace al informe nuevo.
2. **Si la evidencia contradice la decisión**, se abre una **ficha §13 nueva** (por ejemplo,
   `docs/design/decision-272-AAAA-MM-DD.md`), se enlaza desde la ficha antigua y se dice qué decisión
   queda vigente. La antigua no se borra ni se maquilla.
3. **Cerrar #272 exige** sesiones reales registradas, análisis con recuentos por persona y ficha §13
   actualizada. Sin eso, #272 sigue abierta.
4. **El material exacto** (SHA o imagen, navegador, ancho, tema, modo de datos, carpetas F-A/F-B y
   fechas) se copia en la ficha; sin él, la evidencia no es reproducible.

### 7.2 Qué confirmaría o contradiría la decisión G1 del 2026-10-21

La decisión aceptó la simulación para desbloquear U13, adoptó la **entrada por carpetas como base** y
dejó correcciones pendientes (H1, H2, H4, H6, H7 y H8). Esta ronda prueba la **app real**, que es la
heredera de esa base. No hay A/B que comparar. H8 (orientación con muchas carpetas) se observa en
T2/T3, sin fila propia en la tabla.

| Pregunta | Confirmaría | Contradiría | Quedaría sin decidir |
|---|---|---|---|
| ¿Se encuentra y se usa la entrada por carpetas? | ≥3 de 5 la encuentran y la usan sin ayuda en T2/T3 | ≥3 de 5 no la encuentran, eligen otra entrada pese a estar disponible, o dicen que su colección no está en carpetas | 2 de 5 |
| ¿Se entiende qué hace la acción principal (vincular / mover / crear)? | ≥3 de 5 lo explican sin ayuda y nadie mueve por error | ≥3 de 5 no lo explican, o **cualquier** movimiento accidental aplicado (seguridad) | 2 de 5, o solo dudas sin efecto |
| ¿La sugerencia se lee como «no aplicada»? | ≥3 de 5 lo dicen sin ayuda | ≥3 de 5 creen que ya está aplicada | 2 de 5 |
| ¿La carpeta con dos series tiene salida? | ≥3 de 5 encuentran una salida o dicen explícitamente que falta | ≥3 de 5 fuerzan una sola serie o inventan una acción inexistente | 2 de 5 |
| ¿La base de carpetas se sostiene? | ≥3 de 5 completan T3/T6 sin ayuda y nadie queda bloqueado por la estructura | ≥3 de 5 quedan bloqueados por la estructura de carpetas | 2 de 5 |
| ¿El alcance del lote se entiende? (H7) | **No se prueba en este guion**: la pantalla no tiene lote. Queda **NOT RUN** | — | — |

Lectura correcta de la tabla:

- **Confirmar no es demostrar.** «Confirma» significa «la conducta observada es coherente con la
  decisión y no la contradice», no «la decisión era estadísticamente correcta».
- **Un solo movimiento accidental aplicado abre corrección urgente**, aunque no sea un patrón. La
  seguridad no espera a tener 3 casos; lo que no se hace es llamarlo «los usuarios se equivocan».
- **La preferencia no se pregunta** en esta ronda. No se puede decir que una variante «gusta más»
  porque no hay variantes.
- **Si el problema no se reproduce**, se dice: «H1 no apareció en esta muestra»; no se declara que H1
  no existe.
- **H7 (lote)** no se prueba aquí: la app de «Por revisar» no ofrece el lote de los prototipos. Se
  queda **NOT RUN** y no se usa esta ronda para cerrarlo.

### 7.3 Cuándo abrir una decisión nueva

Se abre una ficha §13 nueva (y se enlaza desde la antigua) cuando:

1. La evidencia **contradice** una decisión ya implementada (entrada por carpetas, contrato de la
   acción, alcance de la vista previa, carpeta mixta).
2. Falla un **criterio pre-registrado** de forma que exige cambiar el diseño, no solo un texto.
3. Hay un **efecto irreversible no deseado** (movimiento, renombrado o «Ignorar» aplicado) aunque sea
   una vez.
4. La **premisa** de la decisión no se sostiene: por ejemplo, que los coleccionistas organicen por
   carpetas o que distingan «vincular» de «organizar».
5. Una **barrera de accesibilidad** impide completar la tarea a una persona (no es una preferencia;
   es una exclusión).
6. Hay que **cambiar el alcance** de U13/V5/V6b o cerrar #272 con una decisión de producto distinta.

La ficha nueva lleva: pregunta, evidencia (con `n` y recuentos), opciones, decisión, consecuencias,
qué queda **NOT RUN**, responsable y fecha. Decide el PO; QA documenta y no firma por él.

### 7.4 Cuándo **no** abrir una decisión

- Una **anécdota** de una persona, o una preferencia estética sin efecto en la tarea.
- Un **bug** con causa conocida: se abre un issue, no una decisión de producto.
- Un **fallo del instrumento** (montaje, guion, grabación): se corrige y se repite; no es evidencia
  sobre el diseño.
- Una **hipótesis para otra pantalla** o para otra ronda: se anota como pendiente.
- «A los usuarios les gustaría…» sin conducta observada: no es evidencia.
- Un **criterio post hoc** que se mueve después de ver los datos: no confirma nada.

### 7.5 Qué **no** se puede concluir con 3–5 personas

- Tasas, porcentajes poblacionales, medias, intervalos de confianza ni significación estadística.
- Que «los coleccionistas» prefieren, entienden o hacen algo en general.
- Que una variante es mejor que otra: en esta ronda hay **una sola versión** y no se pregunta
  preferencia.
- Que el diseño es accesible (WCAG) por haberlo probado con 3–5 personas. Solo se pueden describir
  barreras concretas observadas.
- Que no hay problemas porque no aparecieron: con `n` pequeño, un problema raro o grave puede no
  salir.
- Tiempos representativos o comparables entre personas, dispositivos o versiones sin una línea base
  medida con el mismo instrumento.
- Aprendizaje a largo plazo, retención, uso real, adopción o disposición a pagar.
- Que el efecto funciona en la app real si se probó un prototipo estático.
- Que otros perfiles no reclutados se comportarían igual.
- Causalidad: una diferencia puede ser orden, novedad, moderador, dispositivo o familiaridad.
- Que la simulación queda validada o que #272 se cierra sin ficha.
- Que H7 (lote) queda resuelto: no se prueba en esta ronda.

### 7.6 Cómo declarar la muestra y los límites

Todo informe y toda ficha llevan un párrafo como este, relleno con datos reales (los corchetes no se
publican):

> **Muestra.** `N` personas (`P1…PN`), reclutadas por `[canal o canales]` entre `[fechas]`, con
> `[criterios de inclusión]` y `[exclusiones aplicadas]`. Perfiles: `[bandas de edad]`,
> `[dispositivos]`, `[bandas de tamaño de biblioteca]`, `[relación con el proyecto]`. `[N]` había
> visto la app antes; `[N]` no. `[Incentivo: no / cuál]`.
>
> **Límites.** Muestra pequeña y de conveniencia, **no aleatoria ni representativa**. Los resultados se
> expresan como recuentos de personas («3 de 5») y citas; **no son tasas, medias ni proporciones
> poblacionales**. `[Moderador único / dos moderadores]`. `[Una sola versión de la app]`.
> `[Carpetas F-A/F-B: sintéticas o reales]`. `[Accesibilidad: qué se probó y qué no]`.
> `[Qué queda NOT RUN]`.

Se declara también lo que la muestra **no** cubre: perfiles no reclutados, dispositivos no probados,
accesibilidad no verificada, uso prolongado, otras pantallas.

### 7.7 Esqueleto de la ficha §13 nueva

```text
1. Pregunta y alcance
2. Material y entorno exactos (SHA/imagen, navegador, ancho, tema, modo de datos, F-A/F-B, guion)
3. Muestra y reclutamiento (N, canales, exclusiones, bandas, relación con el proyecto, incentivo)
4. Método (tareas T1–T7, moderación, registro, calibración, consentimiento)
5. Criterios pre-registrados y resultado (tabla con n y recuentos)
6. Hallazgos O1…On (conducta, personas, evidencia, código, confianza)
7. Bugs de efecto y decisiones urgentes, separados de los hallazgos
8. Decisiones por hallazgo (adoptar / adaptar / descartar / medir más) — propuesta; decide el PO
9. Límites y lo que no se concluye
10. NOT RUN (incluye H7, accesibilidad conforme y cualquier tarea no ejecutada)
11. Evidencia y enlaces
12. Firma y fecha
```

La ficha **no** se firma hasta que el análisis esté cerrado, las citas revisadas y el `n` validado.
Si alguien se retira después, se actualiza el `n` y se retiran sus citas (§8).

## 8. Conservación y anonimización

Manda el [consentimiento y conservación](consentimiento-y-conservacion.md). Aquí, solo lo que afecta
al registro:

- **Las notas crudas viven fuera del repositorio**: audio, transcripciones, hojas con texto libre,
  originales de consentimiento y el mapa `P1…P5 → identidad`. En `docs/` solo se publican
  **agregados** y **citas anonimizadas ya revisadas**.
- **Nada de rutas ni nombres de archivos reales.** Tampoco nombres de carpetas, series raras que
  identifiquen a la persona, ciudades, centros de trabajo ni marcas de dispositivo exactas. Se
  sustituyen por `[carpeta]`, `[archivo]`, `[serie]`, `F-A`, `F-B`; si el dato no se puede quitar sin
  perder el sentido, no se publica.
- **Citas**: se recortan con `[…]` y se marcan como `paráfrasis` si se reescriben. Las revisan **dos
  personas** antes de publicarlas: una buscando datos personales y otra buscando que no se haya
  cambiado el sentido.
- **Seudónimos**: `P1…P5` se asignan al agendar; no se reutilizan. Una cancelada conserva su código y
  no se le asigna a otra persona. En una segunda ronda se usan `P6…` o `R2-P1…`, no los mismos.
- **Plazos**: el informe se cierra en 30 días desde la última sesión; 30 días después se borran
  notas crudas, audio, transcripciones y hojas de sesión. Nunca más de 60 días desde cada sesión.
  Se anota «borrado hecho» con fecha, sin datos personales.
- **Retirada**: se borran sus notas y su audio, se marca `estado=retirada`, se excluye del `n` y se
  retiran sus citas si el informe ya se publicó. Los agregados que ya no se pueden deshacer se
  explican antes de empezar, como dice el consentimiento.
- **Incidente**: si un dato personal se cuela en un borrador, se para, se borra, se avisa al PO y se
  anota sin el dato. Si ya está en un issue, un PR o el historial, el PO decide cómo purgarlo; no se
  copia aquí.
- **Lo que no se recoge sin actualizar el consentimiento**: SUS, edad exacta, tamaño exacto de la
  biblioteca, capturas de la biblioteca, audio sin autorización. Si se quiere añadir, se cambia el
  consentimiento y se versiona **antes** de la primera sesión.

**Lista de comprobación antes de publicar**:

- [ ] Sin nombres, correos, teléfonos, IPs, rutas ni nombres de archivos o carpetas reales.
- [ ] Citas revisadas por dos personas y marcadas si son paráfrasis.
- [ ] `n` por tarea y recuentos por persona, no solo totales.
- [ ] Límites y muestra de conveniencia escritos.
- [ ] **NOT RUN** explícito (incluye H7 y accesibilidad conforme).
- [ ] Enlaces al guion, consentimiento, checklist y piloto.
- [ ] Ficha §13 actualizada o decisión nueva enlazada.

## 9. Enlaces del kit

- [README del kit](README.md)
- [Consentimiento y conservación](consentimiento-y-conservacion.md)
- [Reclutamiento](reclutamiento.md)
- [Guion de la sesión real](guion-sesion-real.md)
- [Checklist del moderador](checklist-moderador.md)
- [Piloto del instrumento (sintético)](piloto-tecnico-2026-11-14.md)
- [Ficha §13 de la decisión G1 del 2026-10-21](../decision-g1-2026-10-21.md)
- [Simulación #272 del 2026-11-11](../simulacion-272-2026-11-11.md)
- [Guion base T1–T7 de la simulación](../guion-sesion.md)
- [Kit anterior de 5 sesiones del 2026-11-13](../../validacion-ux-por-revisar-2026-11-13.md)

## 10. Versión

| Versión | Fecha | Cambio |
|---|---|---|
| 1.0 | 2026-11-14 | Hoja S y T, CSV, definiciones de resultado/ayuda/error/tiempo/SEQ, análisis por persona, reglas de decisión y conservación. Alineado con el guion de una sola versión (app real) y la escalera de ayuda N0–N5. |

Si cambia una definición después de la primera sesión, se sube la versión y se aplica **solo** a las
sesiones siguientes; las anteriores se clasificaron con la versión que estaba vigente y así se
declara.
