# Benchmark: Whakoom frente a ZascArr (gap analysis)

> Ficha §13 (`docs/design/benchmark-referencias.md`). Fecha: 2026-10-28.
> Base de ZascArr: `main` en `fdb5519`, `docs/BACKLOG.md` y Kanban (proyecto 1) a esa fecha.

## Fuente y límites

- **Referencia:** «Whakoom. Guía exhaustiva de funciones para el coleccionista de tebeos» (27/10/2026),
  aportada por el responsable, con su inventario funcional F01–F37 (anexo). La guía describe lo que dicen la
  web, el centro de ayuda y las fichas de la app de Whakoom; **no es una comprobación en vivo** y ella misma
  marca lo que no pudo verificar. Aquí se usa igual: lo que dependa de un detalle de Whakoom (p. ej. los campos
  de su exportación) se verifica con un fichero real antes de construir.
- **Unidades distintas.** Whakoom cataloga **ejemplares físicos** («Mi cómic») y su lectura; ZascArr gestiona
  **archivos CBZ/CBR** de una tebeoteca digital y su catálogo. Muchas funciones no se trasladan tal cual: se
  traducen (adoptar / adaptar) o se descartan con motivo.
- **Invariantes de ZascArr** que filtran todo lo que sigue: no borra ni mueve sin confirmación; el sistema
  informa y la persona decide (ADR 0008); sin telemetría ni redistribución (LEGAL.md, CLAUDE.md §5); lector =
  Kavita (no se duplica); coste en la Pi (512 MB) y sin dependencias nuevas sin justificar (CLAUDE.md §2).

## Tabla de cobertura

Leyenda: ✅ cubierto (hecho) · 🟡 en el backlog o parcial · ❌ sin cubrir · ⛔ no aplica o se descarta.

| ID | Función de Whakoom | ZascArr hoy | Estado | Decisión |
|---|---|---|---|---|
| F01 | Identificar la edición concreta | Identidad editorial (ADR 0003, Kanban #181–#184); BL-R6 copia/variante/edición (#235) | 🟡 | Ya en curso |
| F02 | Añadido individual | Descubrir + alta manual (#189) + vincular (U19/U20) | ✅ | — |
| F03 | Escaneo de código de barras | `Issue.isbn` existe; no hay alta por código | ⛔ | Descartar: la colección es de archivos, no de ejemplares con código |
| F04 | «Los tengo todos» | Vincular una carpeta con «marcar todos los vinculables» (U20) | ✅ digital / ❌ papel | Adaptar a papel: **WK1** |
| F05 | Faltantes | Huecos (C2), limitados a series con recuento (fronteras de C2/B22) | 🟡 | — (en la tarjeta de estado de colección se distingue «no se puede calcular») |
| F06 | Deseados / buscados | Deseados (D1, D8–D10, U3/V8) | ✅ | — |
| F07 | Estado de serie: en curso, completa, por completar, no completar | `Series.status` (sin UI), `wishlist_policy` (D8) | ❌ | Adaptar: **WK2** |
| F08 | Novedades editoriales | D5 (#162) / S6, sin construir | 🟡 | Añadir criterios a D5 (abajo) |
| F09 | Aviso de nuevo número de una serie seguida | Avisos al móvil solo al importar (E4) | 🟡 | Dentro de D5/S6 |
| F10 | Preferencias de idioma/mercado en novedades | S4 (prioridad castellano), no para novedades | ❌ | Criterio nuevo en D5 |
| F11 | Pendientes de leer | `ReadingProgress` en el modelo; C3 (#150) sin construir | 🟡 | Adaptar: la lectura vive en Kavita, **WK5** |
| F12 | Cola de lectura ordenable | — | ⛔ | Descartar: Kavita ya tiene «Leer más tarde» y listas; arrastrar exige JS (ADR 0001/0005) |
| F13 | Siguiente número a leer | — | ⛔ | Descartar: «Continuar leyendo» de Kavita |
| F14–F16 | Fechas, lectura en lote, estadísticas de lectura | — | ⛔ | Descartar: Kavita registra la lectura real; un registro manual aquí sería una segunda verdad |
| F17 | Estado de conservación | Calidad del archivo: D2 (#153), D3 (#154), BL-PORT1 (#300) | 🟡 | Analogía digital ya registrada |
| F18 | Ubicación física | Ruta real del host (#279, #294); reparto entre discos A5 (#156) | 🟡 | Analogía digital ya registrada |
| F19 | Notas por ejemplar | `ReadingProgress.notes` y `Wishlist.notes` sin UI | ❌ | Adoptar: **WK4** |
| F20 | Préstamos | — | ⛔ | Descartar: prestar un archivo es redistribuirlo (LEGAL.md) |
| F21–F22 | Filtros de cómics y series | BL-IT01–IT03 (#283, #284, #286); BL-R7 vistas (#236) | 🟡 | Faceta «estado de colección» en WK2 |
| F23 | Exportar comicteca y buscados | Copia de la BD (E3), no legible; Kavita (B20) | ❌ | Adoptar: **WK3** |
| F24 | Exportar listas | — | ❌ | Dentro de WK3 |
| F25–F27 | Firmas, originales, encargos | — | ⛔ | Descartar: no es tebeoteca digital; fotos en la Pi |
| F28 | Perfil y colección pública | — | ⛔ | Descartar: autoalojado, un operador, sin telemetría; publicar una tebeoteca digital roza la redistribución |
| F29 | Puntuaciones y reseñas | `ReadingProgress.rating`; C3 (#150) | 🟡 | Solo privada, dentro de la decisión de WK5 |
| F30 | Listas personalizadas | C4 (#151), D7 (#163); `ReadingList` en el modelo | 🟡 | Ya registrada |
| F31 | Cuenta privada | — | ⛔ | No aplica: ZascArr es privado por diseño (ADR 0004) |
| F32 | Crear fichas ausentes | Alta manual (#189) | ✅ | — |
| F33 | Exploración comunitaria | — | ⛔ | Descartar (como F28) |
| F34–F37 | Extras PRO: sin anuncios, insignia, estadísticas, sorteos | Inicio «Tu colección ahora» | ⛔ / 🟡 | Aplazado: estadísticas por tradición/editorial/tamaño, si alguien las pide |
| — | **Importar desde Whakoom** | S5 (BACKLOG, sin tarjeta) | 🟡 | **Refinar S5** con la exportación (abajo) |

Resumen: de las 37 funciones, **4 cubiertas** (F04 solo en digital), **11 en el backlog o parciales**,
**5 sin cubrir** y **17 descartadas o aplazadas** con motivo (lectura duplicada con Kavita, físico sin análogo,
comunidad y préstamo por postura legal, extras de suscripción). Esos 5 huecos, el papel de F04 y la importación
se cubren con las historias nuevas y con los criterios que se añaden a D5 (F10).

## Lo que se trae (adoptar / adaptar)

| Historia | Viene de | Por qué le sirve al coleccionista | P propuesta |
|---|---|---|---|
| **S5 (refinada)** Importar mi exportación de Whakoom | Importación, F23 | Quien ya cataloga en Whakoom no vuelve a teclear qué sigue ni qué busca. **Cambia el spike de S5:** la guía documenta una exportación propia (Excel de comicteca y buscados, CSV de listas), así que se importa **el fichero del usuario** en vez de leer el HTML de Whakoom: sin peticiones a su web, sin cortesía que respetar y con datos que son del propio usuario | P1 |
| **WK1** «Lo tengo en papel» | F02/F04 | Muchos coleccionistas españoles combinan papel y digital. Hoy un número que tienes en papel aparece como «te falta» y una política de búsqueda lo pediría | P2 |
| **WK2** Estado de colección por serie | F07, F21–F22 | Separar «la tengo completa», «me faltan N» y «decidí no completarla» (Whakoom: «separar decisiones deliberadas de olvidos») y filtrar la Biblioteca por eso | P1 |
| **WK3** Exportar mi colección | F23–F24 | Sacar los datos a una hoja de cálculo: lista de la compra, inventario, salida del sistema. La copia de la BD no sirve para eso | P2 |
| **WK4** Notas por serie y por número | F19 | «Faltan las páginas 12-13», «traducción de tal», «es la edición de Hachette»: lo que el coleccionista sabe y el catálogo no | P2 |
| **WK5** Spike: lo leído, desde Kavita | F11–F16, F29 | La lectura ocurre en Kavita: replicarla a mano en ZascArr (C3) crea una segunda verdad. Medir si se puede **traer** de Kavita antes de construir C3 | P2 |

**Criterios que se añaden a D5 (#162, novedades)**, sin crear historia nueva: filtro por mercado/idioma
(España, EE. UU., Japón) (F10); distinguir «anunciado» de «publicado» y no tratar la fecha anunciada como
segura (F07); aviso por serie seguida reutilizando el notificador de E4 (F09). Y la recomendación ya anotada
en el BACKLOG: **fusionar S6 en D5**.

## Supuestos de Whakoom que no valen aquí

- **El ejemplar es la unidad.** En ZascArr la unidad es el archivo vinculado a un número; un número puede
  tener varios archivos (BL-R6) y ninguno.
- **La comunidad da valor.** ZascArr no tiene servidor central, ni cuentas, ni catálogo compartido. Su
  catálogo sale de las fuentes y del propio usuario.
- **La lectura se registra a mano.** Con Kavita, la lectura real ya queda registrada al leer.
- **La exportación es la salida.** Aquí es, además, la **entrada** (S5): el sentido inverso que la guía
  marca como no verificado en Whakoom.

## Invariantes que deben respetar las historias

- Nada se crea ni se desea sin confirmación (ADR 0008): la importación propone y la persona elige.
- Añadir a Deseados desde una importación pasa por la aceptación legal (`require_legal_acknowledgment`,
  CLAUDE.md §5.2), como cualquier otra petición de búsqueda.
- Sin dependencias nuevas: un `.xlsx` es un ZIP con XML y se lee con la biblioteca estándar (`zipfile`,
  `xml.etree`); el CSV, con `csv`. Si el spike muestra que no basta, se justifica aparte.
- La exportación no incluye rutas del disco salvo que se pida (privacidad, CLAUDE.md §5.4) y no envía nada
  fuera de la Pi.
- Ninguna historia toca archivos del disco.

## Casos de prueba antes de implementar

- **S5:** un fichero real exportado de Whakoom por el responsable (comicteca y buscados), con tildes, eñes y
  una serie con varias ediciones; medir cuántas filas casan solas, cuántas quedan dudosas y cuántas no casan.
- **WK1:** una serie con números en papel y en digital; los huecos y la política de búsqueda no deben
  contar el papel como falta salvo que la persona lo pida.
- **WK2:** una serie sin recuento (no se puede decir «completa») y una que decidiste no completar con huecos
  reales: ninguna debe aparecer como «te faltan N».

## Decisión

Adoptar o adaptar las seis historias de arriba y descartar el resto, con el motivo de la tabla. **No hay ADR**
mientras nada cambie la arquitectura; WK1 lo necesitará si la posesión en papel exige un modelo nuevo de
«posesión sin archivo».
