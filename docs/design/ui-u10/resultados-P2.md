# Informe P2 — simulación B→A

## 1. Aviso

**Esto es una simulación, no una persona real.** El texto siguiente es la interpretación de un perfil ficticio (Javier, 42, profesor, 450 CBZ, sin experiencia en terminal ni self-hosted) hecha por un modelo de lenguaje. No hay un participante, no hay clics reales y no hay tiempos medidos. Las citas son literales del HTML; las reacciones, los tiempos y el SEQ son inventados de forma razonada, no observados.

## 2. Nota metodológica (importante para leer los resultados)

- Leí los dos prototipos completos antes de escribir T1, y además el orden real de lectura fue A y luego B, no B→A. **T1 es una reconstrucción, no una prueba de cinco segundos.** He intentado limitarme al título y al primer bloque, pero sé lo que había más abajo.
- Los prototipos son estáticos: los enlaces son `href="#"` y los botones no ejecutan nada. No puedo evaluar la pantalla de revisión, la confirmación, el deshacer ni los estados de error.
- En A no existe el botón «Asignar…» que menciona T5. Respondo sobre su acción principal, «Elegir la serie de esta carpeta». Es una comparación aproximada, no la misma tarea.
- Escala del SEQ asumida: **1 = muy difícil, 7 = muy fácil**.

---

## 3. Variante B — lista compacta

### T1 — Cinco segundos

> «Esto es una lista de archivos pendientes con casillas y un botón grande para asignarlos; arriba me dice que revise esta página y los asigne a una serie.»

Lo que me queda: es una tarea de **archivo por archivo**, en páginas. No veo carpetas por ningún lado. El botón amarillo «Asignar…» y la casilla «Marcar todos los vinculables de esta página» son lo que más pesa visualmente.

### T2–T7

| Tarea | Resultado | Qué pasó y cita |
|---|---|---|
| **T2** | Éxito sin ayuda en el recuento; duda en el arranque | Encuentro «1,322 pendientes» y «Mostrando 1–20 de 1,322». Pero no sé cuántos se marcan con «Marcar todos los vinculables de esta página»: «Solo se marca lo que se puede vincular» no me dice **cuántos** son. ¿Empiezo por aquí y repito 67 páginas? No veo orden, filtro ni búsqueda. |
| **T3** | **Fallo** | Busco la carpeta «Flash (1987)» y no existe como carpeta. Veo veinte filas «Flash 001 (1987).cbz» y una columna «Flash (1987) · 97%». Me pregunto: «¿eso es la carpeta o la serie?». Si le doy a «Marcar todos los vinculables», solo coge 20 de los 155. No sé si los demás están en la página 2 o si esto es otra cosa. |
| **T4** | **Fallo** | No hay ninguna entrada de «sueltos» en toda la pantalla. Solo existe la palabra «pendientes». No puedo distinguir «archivo sin carpeta» de «archivo pendiente de asignar»: para mí, aquí todo es lo mismo. |
| **T5** | **Con ayuda** | El texto que lo explica está escondido en un desplegable **debajo de la paginación**: «¿Qué hace «Asignar…»?». Sin que me lo señalen, no lo encuentro. Al abrirlo: «Prepara la asignación de los archivos marcados. Antes de mover nada verás una revisión y tendrás que confirmar.» Eso me tranquiliza a medias y me preocupa a medias: dice «mover», así que parece que **mueve archivos**, no que los vincula. Y no me aclara si crea una serie nueva, si usa una existente o si solo pone una etiqueta. |
| **T6** | **Fallo** | Puedo desmarcar el archivo que no es de Flash, y eso evita el error. Pero no veo cómo decir que ese archivo es de **otra** serie: la columna «Serie sugerida» es texto, no se puede cambiar. Solo puedo no asignarlo y dejarlo para luego. La interfaz no me ofrece partir la página en dos series. |
| **T7** | — | SEQ: **3/7**. Preferencia: A (ver abajo). Lo primero que cambiaría: que «Asignar…» explique **antes** qué va a pasar y cuántos archivos van a caer. |

**Ruido concreto de B:** hay dos botones con el mismo nombre y distinto alcance, el de la barra y el de cada fila. No sé si el de la fila asigna solo ese archivo o abre la misma revisión. Y el aviso de seguridad está en el peor sitio posible: después de veinte filas y de «Siguientes →», justo donde ya no se lee.

---

## 4. Variante A — carpetas primero

### T1 — Cinco segundos

> «Esto es una lista de mis carpetas pendientes, cada una con la serie que el programa cree que es y un botón para confirmarla; puedo ir carpeta por carpeta.»

Lo que me queda: esto se parece a mis carpetas de Windows. Veo «108 carpetas», «1,322 pendientes» y «14 archivos sueltos». La primera tarjeta es Flash con 155 archivos. Entiendo que el programa **propone** una serie, no que la haya aplicado.

### T2–T7

| Tarea | Resultado | Qué pasó y cita |
|---|---|---|
| **T2** | Éxito sin ayuda, con una duda de jerarquía | El recuento está claro: «1,322 pendientes en 108 carpetas» y los chips. La frase dice «Empieza por una carpeta», pero lo primero que aparece es un botón «Ver los 14 archivos sueltos». Me paro: ¿empiezo por los sueltos porque están primero, o son un caso aparte? Finalmente elijo Flash porque es la primera tarjeta y la que más archivos tiene (155). No sé si el orden es por tamaño, por probabilidad o alfabético. |
| **T3** | Éxito sin ayuda | Encuentro la tarjeta y entiendo el estado: «Es una sugerencia: no está elegida ni asignada.» El siguiente paso es «Elegir la serie de esta carpeta». Pero no sé qué pasará: ¿se aplica a los 155 de golpe?, ¿me deja revisar antes?, ¿mueve los archivos? El botón promete «elegir», no «aplicar». |
| **T4** | Éxito sin ayuda, con reserva | Encuentro «14 archivos sueltos» y «Ver los 14 archivos sueltos». Entiendo que son los que no están en ninguna carpeta. La reserva es de números: la frase dice «1,322 pendientes en 108 carpetas» y luego hay 14 sueltos. O los sueltos están dentro de los 1.322 y la frase está mal escrita, o son 1.336. Con Excel en la mano, eso me hace desconfiar del recuento. |
| **T5** | **Fallo** | En esta pantalla no hay ningún «Asignar…». La acción es «Elegir la serie de esta carpeta» y **no se explica en ningún sitio**. No sé si crea una serie, si mueve los CBZ a otra carpeta, si los copia o si solo los vincula. Tampoco veo revisión ni confirmación: pulsar el botón amarillo parece el paso definitivo. Eso es exactamente lo que me da miedo. |
| **T6** | **Fallo** | La tarjeta solo admite **una** serie sugerida. No hay forma de partirla en dos. Probaría «Ver archivos» a ver si desde ahí puedo seleccionar unos y otros, pero no hay nada que me lo prometa; sería yo inventando el flujo. Si no existe, tendría que mover archivos a mano en el explorador antes de volver, y eso es justo lo que quería evitar. |
| **T7** | — | SEQ: **4/7**. Preferencia: A. Lo primero que quitaría: la frase «Es una sugerencia: no está elegida ni asignada.» repetida veinte veces. A la tercera tarjeta ya no la leo, y es el aviso más importante de la página. |

**Ruido concreto de A:** veinte tarjetas idénticas con veinte botones amarillos compiten por mi atención; no hay jerarquía entre «empieza por esta» y «las demás». Tampoco hay buscador ni orden para 108 carpetas, y la paginación solo ofrece «Siguientes →». Con mis 450 archivos quizá no lo necesite; con 1.322, sí.

---

## 5. Preferencia A/B

**Prefiero A.** Motivo: se parece a cómo tengo yo las cosas (carpetas dentro del disco), me dice cuántos archivos hay en cada una, y sobre todo **me avisa de que la sugerencia no está aplicada**. Eso reduce mi miedo a que el programa decida por mí. En B me siento delante de una hoja de cálculo con un botón de «asignar todo»: más rápido, pero con más riesgo de equivocarme en bloque y de no saber qué ha pasado.

Pero es una preferencia **con reservas**: A me dice mejor *qué* hay, y B (en su letra pequeña) me dice mejor *qué va a pasar*. Ninguna de las dos me da las dos cosas en el mismo sitio. La pantalla que me gustaría es A para entrar y B para revisar dentro de una carpeta, con la explicación y la confirmación visibles antes de tocar nada.

---

## 6. Las tres cosas que más me confunden o me hacen desconfiar

1. **No sé qué hace el botón principal.** En A, «Elegir la serie de esta carpeta» no explica si crea, mueve, copia o vincula. En B, «Asignar…» solo se explica en un desplegable que está debajo de la tabla y que habla de «mover». Sin confirmación visible ni «deshacer» en ninguna de las dos, no pulso. Mi regla es: si no sé si mueve archivos, no lo toco.
2. **Miedo a duplicar series al ir por partes.** En B, si asigno 20 archivos de Flash y luego paso a la página 2, ¿se suman a «Flash (1987)» o me crea otra «Flash (1987)»? En A, si elijo la serie de la carpeta y luego vuelvo a los archivos, ¿se vuelve a aplicar? Los porcentajes («94%», «97%») no me ayudan: al contrario, me hacen calcular cuántos de los 155 estarán mal (un 6% de 155 son unos nueve). Prefiero que me enseñe los archivos antes de aplicarlo todo.
3. **El vocabulario no me queda claro: pendiente, suelto, vinculable, sugerida, asignar, elegir.** «Solo se marca lo que se puede vincular» me deja preguntando «¿y cuántos son?». «Serie sugerida: Flash (1987) · 94%» no me aclara si «Flash (1987)» es la carpeta, la serie o una etiqueta. Y en A, «1,322 pendientes en 108 carpetas» junto a «14 archivos sueltos» no me cuadra: o los sueltos están dentro o son 1.336.

Añado una desconfianza de contexto: **yo tengo unos 450 archivos, no 1.322.** Si la app me enseña 1.322, pienso que ha escaneado otra carpeta, que cuenta archivos que yo no veo o que ha duplicado. En una herramienta que me va a tocar mi biblioteca, eso es motivo para parar y revisar antes de seguir.

---

## 7. Qué NO se puede concluir de esta simulación

- **No es evidencia de comportamiento real.** Un modelo interpretando un perfil no equivale a un usuario: no hay torpeza motora, ni dudas reales, ni cansancio, ni clics accidentales.
- **No hay tiempos ni tasas válidas.** Los segundos son inventados y el SEQ es una opinión construida, no medida. No se puede comparar A con B con n=1 simulado.
- **T1 está contaminado.** Leí los archivos completos y en orden A→B, así que la «primera impresión» no es una prueba de cinco segundos ni respeta el orden B→A. No sirve para medir qué se ve primero.
- **No se puede evaluar el flujo posterior ni la seguridad.** Los botones no hacen nada: no se ha visto la revisión, la confirmación, el deshacer, el estado de error, la carga, el caso de cero archivos ni la accesibilidad.
- **No se puede concluir que B no tenga carpetas.** Solo se puede decir que *esta pantalla* no las muestra. Puede existir otra pantalla fuera del prototipo; el fallo es de lo que se enseña, no necesariamente del producto.
- **T5 no es comparable entre variantes.** En A no existe «Asignar…»; la comparación se hizo contra «Elegir la serie de esta carpeta». El guion da por hecho que ambas variantes tienen la misma acción y no es así.
- **No se puede generalizar a otros perfiles.** Que este P2 prefiera A no dice nada de P1, P3 ni de usuarios con más experiencia. Tampoco se ha medido aprendizaje ni confianza real, solo preferencia declarada.
- **Los datos del prototipo no son los del perfil.** 1.322 archivos y 108 carpetas no coinciden con los 450 CBZ declarados; las reacciones a la escala son hipotéticas.
