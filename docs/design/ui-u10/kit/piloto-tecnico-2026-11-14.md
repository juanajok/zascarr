# Piloto del instrumento de registro — 2026-11-14

> ## PILOTO TÉCNICO CON DATOS SINTÉTICOS — NO ES UNA SESIÓN REAL NI ACREDITA #272
>
> **No hay personas, no hay app, no hay navegador, no hay tiempos medidos y no hay resultados.** Las
> filas de este documento son de relleno (`P0`, `S00`, `origen=sintetico`) y sirven solo para probar
> que la [hoja de registro](registro-y-analisis.md) y sus CSV se pueden usar.
>
> **No sustituye al ensayo del montaje** (entorno, grabación, audio, borrado, restauración): eso es
> otra comprobación y sigue pendiente en la [checklist](checklist-moderador.md).
>
> Si alguien cita este documento como validación, se ha equivocado de documento.

## 1. Qué se ha pilotado y qué no

**Se ha pilotado, en papel:**

- La hoja S (sesión) y la hoja T (tarea) del [registro](registro-y-analisis.md).
- Los dos CSV, con sus cabeceras y una fila sintética por tarea.
- Las definiciones de resultado (`ES`, `EC`, `FA`, `AB`, `NE`, `NA`), de ayuda (`N0`–`N5`), de
  error, de tiempo y de SEQ.
- La regla de inicio y parada del cronómetro, incluida T1 (5 s), T5 (vista previa) y T7 (cierre).
- La separación entre resultado de comprensión, ejecución y efecto.
- La privacidad de los ficheros del kit.

**No se ha pilotado:**

- La app real, ni un navegador, ni un dispositivo.
- Una sesión con una persona: no hay consentimiento, ni citas, ni clics, ni tiempos.
- El montaje técnico: grabación, audio, borrado, restauración, snapshot.
- La importación en Excel o LibreOffice de verdad; solo se comprobó la estructura del CSV.
- La calibración con dos moderadores de verdad; los 12 casos están escritos, pero no los han
  clasificado dos personas distintas.

## 2. Cómo se hizo

Una sola persona (QA) alternó los papeles de moderador y de «participante imaginario» **sin abrir la
app**. Leyó el [guion](guion-sesion-real.md) y la [checklist](checklist-moderador.md), rellenó una
sesión sintética y siete tareas, y comparó cada campo con lo que el guion pide registrar. No se
cronometró nada: **la duración del piloto no se registra y no es un dato**.

Los datos de la sesión sintética son:

- `S00` / `P0`: seudónimo reservado para el piloto; **nunca** se asigna a una persona.
- `modo_datos=prueba`, carpetas `F-A` y `F-B` sintéticas, `total_inicial=12`, `carpetas_inicial=3`.
- Sin consentimiento (`n/a`), sin grabación (`ninguna`), estado `piloto`.
- Siete filas T1–T7 con resultados distintos para probar los códigos, **no** para describir a nadie.

## 3. Hoja S sintética

| Origen | `sesion` | `seudonimo` | `fecha` | `dispositivo` | `ancho_px` | `modo_datos` | `version_ui` | `duracion_min` | `estado` |
|---|---|---|---|---|---|---|---|---|---|
| **SINTÉTICO** | `S00` | `P0` | `2026-11-14` | `portatil` | `1440` | `prueba` | `n/d` (papel) | `n/d` | `piloto` |

Completa, la fila S00 queda así (los campos que no aplican van con `n/d`, `n/a` o `—`, nunca
inventados):

| Campo | Valor sintético | Para qué se probó |
|---|---|---|
| `navegador` | `n/d` | Que el campo acepta «no aplica» sin inventar una versión |
| `tema` | `claro` | Que el tema se registra |
| `carpeta_t3` / `carpeta_t6` | `F-A` / `F-B` | Que se registran códigos, no nombres reales |
| `carpetas_sinteticas` | `ambas` | Que se distingue una carpeta sintética de una real |
| `total_inicial` / `carpetas_inicial` | `12` / `3` | Que el estado de partida se puede reproducir |
| `import_rescan` | `no` | Que se registra si los datos cambian a mitad |
| `consentimiento` / `ref_consentimiento` | `n/a` / `—` | Que una fila sintética no finge un consentimiento |
| `grabacion` | `ninguna` | Que se registra qué se autorizó |
| `banda_edad` / `banda_biblioteca` | `n/a` / `n/a` | Que una fila sin persona no inventa bandas |
| `orden_efectivo` | `T1>T2>T3>T4>T5>T6>T7` | Que se registra el orden real, no el previsto |
| `restauracion` | `no_aplica` | Que se distingue «no hubo escritura» de «pendiente» |

## 4. Casos de calibración

Antes de la primera sesión, `M1` y `M2` deben clasificar estos 12 casos **por separado** y coincidir
en los 12. No son datos: son viñetas para fijar las definiciones. El caso 7 y el 8 son los más
importantes, porque separan «no ejecutó» de «éxito de comprensión sin confirmar».

| # | Conducta observada (viñeta) | Resultado | Ejecución | Efecto | Ayuda | Por qué |
|---|---|---|---|---|---|---|
| C1 | No oyó la pregunta; el moderador la repite literal y completa sin más | `ES` | `no_aplica` | `no_aplica` | `N0` | Repetir por no oír **no** es ayuda |
| C2 | Con «¿qué estás pensando?» cambia de camino y completa | `EC` | `no_aplica` | `no_aplica` | `N1` | `N1` desbloqueó: cuenta como ayuda |
| C3 | Con «¿qué estás pensando?» sigue igual, no completa y no pide pasar | `FA` | `no_aplica` | `no_aplica` | `N0` | `N1` no cambió nada; el fallo es de la tarea |
| C4 | Con «¿hay algo que te ayude?» va a un control concreto que no había usado y completa | `EC` | `no_aplica` | `no_aplica` | `N2` | `N2` orientó a un control: cuenta |
| C5 | Con una pista de zona («mira arriba») completa | `EC` | `no_aplica` | `no_aplica` | `N3` | `N3` siempre cuenta |
| C6 | El moderador pulsa por ella y la tarea sale | `NA` | `si` | `no_verificado` | `N5` | No es éxito de la persona; se registra «moderador ejecutó» |
| C7 | En T5 no quiere pulsar nada, explica que teme mover el archivo y no hay respuesta evaluable | `NE` | `no` | `no_verificado` | `N0` | «No ejecutó»: no es éxito ni fallo |
| C8 | En T5 llega a la vista previa, nombra serie/número/carpeta/nombre final y no confirma | `ES` | `no` | `no_verificado` | `N0` | El criterio de T5 es comprensión; no confirmar no lo convierte en `NE` |
| C9 | En T6 deja la tarea por miedo a equivocarse | `AB` | `no` | `no_aplica` | `N0` | El guion T6 lo llama abandono; se anota el motivo |
| C10 | En T2 se agotan los 3 minutos sin encontrar el total | `AB` | `no_aplica` | `no_aplica` | `N0` | El guion llama abandono al tiempo máximo agotado, no fallo |
| C11 | La vista de T4 no carga y la tarea se salta | `NA` | `no` | `no_verificado` | `N0` | Incidencia técnica: no es fallo de la persona |
| C12 | En T5 elige «Elegir la serie de esta carpeta» esperando que mueva todos los archivos | `FA` | `no` | `no_aplica` | `N0` | Idea equivocada del efecto: fallo de comprensión, no `NE` |

**Dos casos extra** que no cuentan para los 12, pero conviene haber leído:

- **Efecto incorrecto con acción correcta**: la persona hace lo que la pantalla propone y la app no
  aplica el cambio. Resultado `ES`/`EC`, `efecto=incorrecto`, `ejecucion=si`; es un **bug**, no un
  fallo de comprensión.
- **«Ignorar» aplicado sin querer**: `errores=1`, `error_tipos=accion_peligrosa_aplicada`,
  `movimientos_accidentales=0` (no es mover ni renombrar), `cambio_estado=ignorado`, nota «sin
  deshacer en esta pantalla».

## 5. Filas sintéticas

Una fila por tarea. **Todas llevan `SINTÉTICO` en la primera columna y en la nota.** Los tiempos y
los SEQ son de relleno: no se han medido y no describen a ninguna persona. Se usan para comprobar que
la hoja acepta un número, un vacío y un tipo de tiempo.

| Origen | Tarea | Resultado | Ejecución | Efecto | Tiempo (s) | Errores | Interv. | Nudges | Ayuda | SEQ | Nota |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **SINTÉTICO** | T1 | `ES` | `no_aplica` | `no_aplica` | 5 | 0 | 0 | 0 | `N0` | 5 | 5 s de exposición; no es tiempo de tarea |
| **SINTÉTICO** | T2 | `EC` | `no_aplica` | `no_aplica` | 38 | 1 | 1 | 0 | `N3` | 4 | Pista de zona; total encontrado |
| **SINTÉTICO** | T3 | `FA` | `no` | `no_aplica` | 95 | 1 | 0 | 1 | `N0` | 3 | Cree que la sugerencia ya está aplicada |
| **SINTÉTICO** | T4 | `AB` | `no_aplica` | `no_aplica` | 60 | 0 | 0 | 0 | `N0` | — | Pide pasar; abandono de tarea |
| **SINTÉTICO** | T5 | `NE` | `no` | `no_verificado` | 84 | 0 | 0 | 0 | `N0` | 3 | No quiere pulsar nada; teme mover el archivo |
| **SINTÉTICO** | T6 | `ES` | `no` | `no_aplica` | 72 | 0 | 0 | 0 | `N0` | 6 | Detecta dos series y elige revisar una a una |
| **SINTÉTICO** | T7 | `ES` | `no_aplica` | `no_aplica` | — | 0 | 0 | 0 | `N0` | 4 | Cierre completado; no se pregunta preferencia A/B |

### 5.1 CSV S — sesión sintética

```csv
origen;sesion;seudonimo;fecha;hora_inicio;modalidad_sesion;dispositivo;navegador;ancho_px;tema;version_ui;modo_datos;carpeta_t3;carpeta_t6;carpetas_sinteticas;total_inicial;carpetas_inicial;import_rescan;duracion_min;consentimiento;ref_consentimiento;grabacion;moderador;observador;estado;banda_edad;banda_biblioteca;conocia_diseno;orden_efectivo;tareas_incidencias;restauracion;incidencias;notas
sintetico;S00;P0;2026-11-14;10:00;presencial;portatil;n/d;1440;claro;n/d;prueba;F-A;F-B;ambas;12;3;no;n/d;n/a;—;ninguna;M1;M1;piloto;n/a;n/a;n/a;T1>T2>T3>T4>T5>T6>T7;ninguna;no_aplica;SINTÉTICO: sin personas ni app;"SINTÉTICO — fila de relleno; no es una sesión real. Tiempos y SEQ inventados para probar la hoja."
```

### 5.2 CSV T — siete tareas sintéticas

```csv
origen;sesion;seudonimo;orden;tarea;tipo;carpeta;resultado;ejecucion;efecto;tiempo_s;pausa_s;tiempo_tipo;errores;error_tipos;movimientos_accidentales;intervenciones;nudges;ayuda_tipo;estado_final;cambio_estado;seq;nota;cita
sintetico;S00;P0;1;T1;tarea;—;ES;no_aplica;no_aplica;5;0;exposicion;0;ninguno;0;0;0;N0;pendientes;ninguno;5;"SINTÉTICO — primera impresión; 5 s de exposición, no tiempo de tarea";"«Revisar los archivos que no ha sabido ordenar» (SINTÉTICA)"
sintetico;S00;P0;2;T2;tarea;—;EC;no_aplica;no_aplica;38;0;tarea;1;comprension;0;1;0;N3;carpetas;ninguno;4;"SINTÉTICO — pista de zona tras 90 s; entiende el total";"«Ah, el número está abajo» (SINTÉTICA)"
sintetico;S00;P0;3;T3;tarea;F-A;FA;no;no_aplica;95;0;tarea;1;comprension;0;0;1;N0;asistente;ninguno;3;"SINTÉTICO — cree que la sugerencia ya está aplicada; N1 no cambió el camino";"«Ya está, la sugerencia está puesta» (SINTÉTICA)"
sintetico;S00;P0;4;T4;tarea;—;AB;no_aplica;no_aplica;60;0;tarea;0;ninguno;0;0;0;N0;sueltos;ninguno;;"SINTÉTICO — pide pasar tras encontrar la cola; abandono de tarea";"«Déjalo, ya lo he visto» (SINTÉTICA)"
sintetico;S00;P0;5;T5;tarea;—;NE;no;no_verificado;84;0;tarea;0;ninguno;0;0;0;N0;pendientes;ninguno;3;"SINTÉTICO — no quiere pulsar nada y teme mover el archivo; no ejecutó, no es fallo";"«No lo pulso; no sé si mueve el archivo» (SINTÉTICA)"
sintetico;S00;P0;6;T6;tarea;F-B;ES;no;no_aplica;72;0;tarea;0;ninguno;0;0;0;N0;carpetas;ninguno;6;"SINTÉTICO — detecta dos series y elige revisar una por una; no ejecuta";"«Esta carpeta no es toda de la misma serie» (SINTÉTICA)"
sintetico;S00;P0;7;T7;cierre;—;ES;no_aplica;no_aplica;;0;entrevista;0;ninguno;0;0;0;N0;pendientes;ninguno;4;"SINTÉTICO — cierre completado; no se pregunta preferencia A/B";"«Cambiaría el aviso de lo que va a pasar» (SINTÉTICA)"
```

### 5.3 Comprobación de estructura

- **S**: cabecera de **33 campos** y **1 fila** con 33 campos.
- **T**: cabecera de **24 campos** y **7 filas** con 24 campos cada una.
- Las comillas dobles están equilibradas; los campos con `;` van entrecomillados.
- Los vacíos (`tiempo_s` de T7, `seq` de T4) se leen como «no registrado», no como `0`.
- `P0` y `S00` están reservados; el análisis filtra `origen=sintetico`.
- No se ha probado en Excel ni en LibreOffice: solo la estructura y el número de campos. La prueba de
  pegado real queda pendiente en [§9](#9-pendiente-antes-de-la-primera-sesión).

## 6. Fricciones detectadas y cambios aplicados

Se detectaron al comparar la hoja con el [guion](guion-sesion-real.md), la
[checklist](checklist-moderador.md) y el [consentimiento](consentimiento-y-conservacion.md), y al
rellenar las siete filas. **No son hallazgos sobre la app.**

| # | Fricción detectada | Cambio aplicado |
|---|---|---|
| F1 | El guion prueba **una sola versión** (app real), pero la hoja tenía columnas de variante A/B y preferencia | Se quitaron `variante`, `orden_variante`, `preferencia` y `orden_variantes`; se añadieron `modo_datos`, `carpeta_t3`, `carpeta_t6` y `carpetas_sinteticas` |
| F2 | El guion y la checklist usan **«no ejecutó»**, pero la hoja solo tenía éxito/ayuda/fallo/abandono | Se añadió `NE`, separado de `FA` y `AB`, y la columna `ejecucion` |
| F3 | En T5, «no confirmar» se podía confundir con fallo; el criterio de T5 es comprensión | Se separaron `resultado` (comprensión), `ejecucion` (se pulsó o no) y `efecto` (qué pasó). T5 puede ser `ES` con `ejecucion=no` |
| F4 | La escalera de ayuda real es **N0–N5**, no A0–A4 | Se adoptó `N0`–`N5`; `N1`/`N2` solo cuentan si cambian el camino u orientan a un control; `nudges` frente a `intervenciones` |
| F5 | No había regla de tiempos por tarea; el corte no es «3 minutos» | Se añadieron 45 s (`N1`), 90 s (`N3`), 2 min (ofrecer pasar) y máximos T2 3 / T3 6 / T4 3 / T5 8 / T6 8; el máximo agotado es `AB`, no `FA` |
| F6 | Faltaba distinguir tiempo de tarea, exposición y entrevista | Se añadió `tiempo_tipo` (`tarea`, `exposicion`, `entrevista`, `no_medido`) y `pausa_s` |
| F7 | El guion pide registrar la carpeta (F-A/F-B), el estado final y el cambio de estado; no había columnas | Se añadieron `carpeta`, `estado_final` y `cambio_estado`; los nombres exactos quedan en la ficha privada |
| F8 | Sin `modo_datos`, `total_inicial`, `carpetas_inicial` e `import_rescan` no se reproduce el estado de partida | Se añadieron a la hoja S |
| F9 | Faltaban `tema`, `navegador` y `ancho_px` para reproducir el entorno | Se añadieron; sistema, zoom y tipo de entrada se quedan en la ficha privada y se anotan en `incidencias` si explican una diferencia |
| F10 | Sin `orden_efectivo`, `tareas_incidencias` y `restauracion` no se sabe si la siguiente persona parte del mismo estado | Se añadieron a la hoja S |
| F11 | El SEQ se podía leer como «por variante»; en esta ronda hay una sola app | Se aclaró: SEQ por tarea y SEQ global en T7; T7 se marca `tipo=cierre` y no entra en la matriz de tareas |
| F12 | `error_tipos` no distinguía acción peligrosa **aplicada** de **evitada**; «Ignorar» no es un movimiento | Se añadieron `accion_peligrosa_evitada` y `accion_peligrosa_aplicada`; `movimientos_accidentales` solo cuenta mover/renombrar aplicado |
| F13 | Una cita podía llevar un nombre, una carpeta o una ruta | Se añadió la regla de anonimización y revisión por dos personas; en el repo solo van `F-A`, `F-B` y `C1/C2` |
| F14 | Las filas sintéticas podían contaminar el análisis | Se añadió `origen` (`real`/`sintetico`) y `P0`/`S00` reservados; el análisis filtra |
| F15 | El consentimiento todavía dice «preferencia A/B» y «por variante»; el guion dice una sola versión | **No aplicado**: es otro fichero. Se anota para que la persona responsable del consentimiento lo adapte antes de firmar (guion §1.1) |
| F16 | El README describe este fichero como «ensayo técnico del montaje»; este piloto es del instrumento | **No aplicado**: es otro fichero. Se anota; el montaje sigue pendiente en la checklist |
| F17 | La misma conducta (miedo a mover) es `NE` en T5 y `AB` en T6; el guion T5 la titula «Abandono» pero pide registrar «no ejecutó» | Se documentó la diferencia en las definiciones y en los casos C7/C9; en T5 manda el «no ejecutó» (`NE`), en T6 el guion dice abandono (`AB`). No se unifica a ciegas |
| F18 | El criterio de T5 dice «lee la nota antes de pulsar»; si la lee después pero entiende el destino, no estaba claro qué anotar | Se decidió clasificar por la comprensión final y anotar «leyó después» como observación; la diferencia se lleva a la ficha. Requiere calibración (caso C8) |
| F19 | No había sitio para «moderador ejecutó» | `resultado=NA`, `ayuda_tipo=N5`, nota «moderador ejecutó» |
| F20 | El guion pide comprobar el estado y las cifras después de cada sesión; no había campo | Se añadieron `restauracion` e `incidencias`; la verificación numérica se anota en `incidencias` si no coincide |
| F21 | El criterio general del guion dice «con ayuda» para niveles 3–4, pero T1 y la escalera permiten que N1/N2 cuenten si desbloquean u orientan | Se aplica la regla específica (`N1`/`N2` solo si cambian el camino u orientan) y se declara en §5.2 del registro; se calibra con C2–C5 |

**Fricciones que no se han podido cerrar en este piloto**:

- **F15** y **F16** afectan a otros ficheros del kit; no se tocan aquí.
- La importación real en Excel/LibreOffice no se ha probado.
- La calibración de los 12 casos no se ha hecho con dos personas.
- El ensayo del montaje (grabación, audio, borrado, snapshot) no se ha hecho.

## 7. Comprobación de privacidad

**Fecha:** 2026-11-14. **Alcance:** todos los ficheros del kit presentes al cerrar este documento
(`README.md`, `consentimiento-y-conservacion.md`, `reclutamiento.md`, `guion-sesion-real.md`,
`checklist-moderador.md`, `registro-y-analisis.md` y este piloto).

### 7.1 Patrones buscados

| Patrón | Qué busca | Coincidencias | Dónde |
|---|---|---|---|
| `/media/` | rutas de bibliotecas en medios extraíbles | 1 | solo en esta tabla de comprobación; no es una ruta real |
| `/mnt/`, `/home/`, `C:\`, `~/` | rutas locales de una persona | 1 línea | solo en esta tabla de comprobación; no hay ninguna ruta real |
| `zascarr_session` | nombre de sesión o carpeta de trabajo | 1 | solo en esta tabla de comprobación |
| correo (texto con arroba y dominio) | direcciones de correo | 0 | — |
| teléfono (números seguidos con prefijo) | números de teléfono | 0 | — |
| IP (cuatro bloques numéricos) | direcciones de red | 0 | — |
| nombre del responsable (no se escribe aquí) | nombre propio en los ficheros del kit | 0 | — |
| nombres de pila de personas | nombres propios que parezcan reales | 0 | solo hay `P1…P5`, `P0`, `M1` y `M2` |

> Las únicas coincidencias de los patrones de ruta son **los propios patrones de esta tabla**. No hay
> ninguna ruta ni sesión real en el kit. Los patrones se describen aquí para poder repetir la
> comprobación; no se copia ningún dato encontrado.

### 7.2 Revisión manual

- **Solo hay seudónimos y códigos**: `P0` (piloto), `P1…P5`, `M1`, `M2`, `S00`, `S01…S05`, `C-01…`,
  `F-A`, `F-B`. No hay nombres de personas reales.
- **No hay nombres de carpetas ni de archivos de una biblioteca**: las filas sintéticas usan `F-A` y
  `F-B`; los enunciados del guion usan un ejemplo de serie, no una carpeta de una persona.
- **No hay rutas, correos, teléfonos, IPs ni credenciales** en los ficheros del kit.
- **No hay capturas ni audio** en el repositorio; el audio es opcional y vive fuera.
- El **mapa seudónimo → identidad** no está en el kit: vive solo en el original privado del
  consentimiento.
- El **README** ya no usa nombres de pila para las personas simuladas: habla de `P1…P5` y de la
  simulación sin nombre. Correcto.
- El **consentimiento** usa `[NOMBRE]` como marcador, no un nombre real. Correcto.
- La **invitación** del reclutamiento usa `[nombre]` como marcador. Correcto.

### 7.3 Conclusión de la comprobación

**No se ha encontrado PII ni rutas reales en los ficheros del kit.** Las únicas coincidencias son los
patrones de la propia tabla; no hay nombres de personas, correos, teléfonos ni direcciones. La
comprobación se debe repetir cuando se añada o se modifique cualquier fichero del kit y antes de
publicar la ficha §13.

## 8. Qué no prueba este piloto

- **No prueba que la hoja sea fácil de usar en una sesión real.** Prueba que se puede rellenar y que
  los campos existen.
- **No prueba que las definiciones sean inequívocas.** Prueba que 12 casos tienen una respuesta
  acordada; dos moderadores de verdad todavía no los han clasificado.
- **No prueba tiempos, comprensión, confianza ni efecto.** No hay personas ni app.
- **No prueba la importación en una hoja de cálculo.** Solo la estructura del CSV.
- **No prueba el montaje técnico** (grabación, audio, borrado, restauración).
- **No acredita #272, U10 ni G1.** Nada de lo que hay aquí se puede presentar como validación.
- **No sustituye al guion ni a la checklist.** Si hay conflicto, mandan ellos.

## 9. Pendiente antes de la primera sesión

- [ ] Copiar los criterios literales del guion a la tabla de [§5.7 del registro](registro-y-analisis.md#57-criterios-de-éxito-por-tarea)
      y versionar la hoja.
- [ ] Que `M1` y `M2` clasifiquen los 12 casos de [§4](#4-casos-de-calibración) por separado y
      coincidan en los 12.
- [ ] Importar los dos CSV en la hoja de cálculo real y comprobar que las columnas caen bien; el
      piloto solo comprobó la estructura.
- [x] Reconciliado el 2026-11-14: el [consentimiento](consentimiento-y-conservacion.md) ya no
      menciona «preferencia A/B»; esta ronda prueba **una sola versión** de la app (guion §1.1).
- [ ] Hacer el **ensayo del montaje** con la [checklist](checklist-moderador.md): entorno, grabación,
      audio, borrado, snapshot y restauración.
- [ ] Borrar o aislar las filas `S00/P0` antes de analizar; el filtro es `origen=real`.
- [ ] Comprobar que la ficha privada de sesión tiene URL, nombres exactos de F-A/F-B y el mapa
      seudónimo → identidad; nada de eso va al repositorio.
- [ ] Repetir la comprobación de privacidad de [§7](#7-comprobación-de-privacidad) cuando el kit
      cambie.

## 10. Enlaces y versión

- [Registro y análisis](registro-y-analisis.md)
- [Guion de la sesión real](guion-sesion-real.md)
- [Checklist del moderador](checklist-moderador.md)
- [Consentimiento y conservación](consentimiento-y-conservacion.md)
- [Reclutamiento](reclutamiento.md)
- [README del kit](README.md)
- [Ficha §13 de la decisión G1 del 2026-10-21](../decision-g1-2026-10-21.md)

| Versión | Fecha | Cambio |
|---|---|---|
| 1.0 | 2026-11-14 | Piloto del instrumento con 7 filas sintéticas, 12 casos de calibración, fricciones y comprobación de privacidad. Sin personas, sin app, sin resultados. |
