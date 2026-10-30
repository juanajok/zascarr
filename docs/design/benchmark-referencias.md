# Benchmarking de referencias — procedimiento y ficha

> Regla (CLAUDE.md §13): antes de implementar una feature P0/P1 de comportamiento nuevo, o
> una historia que toque modelo, ficheros, seguridad o el ciclo de búsqueda y descarga,
> consultar referencias pertinentes y registrar, por idea, adoptar / adaptar / mejorar /
> construir sobre lo propio / descartar, con versión y pruebas. No inferir soporte de una
> función por su UI, ni ausencia por no encontrarla.

Esto es un paso habitual de **diseño**, no una obligación de copiar funciones de cinco
aplicaciones antes de cada commit. Responde a cuatro preguntas: ¿qué problema resolvieron,
qué identidad de datos asumieron, qué casos dejaron fuera y qué parte sirve para ZascArr?
La comparación con Kapowarr (2026-09-27) funcionó precisamente porque distinguimos su
vínculo archivo↔issues de nuestra cobertura editorial entre publicaciones.

## Procedimiento

1. **Fijar el problema local primero.** Escribir la historia, un caso real de la
   biblioteca, el comportamiento actual y el resultado deseado. Sin eso, el benchmark se
   convierte en una lista de funciones atractivas. Comprobar también en el código vigente
   (`origin/main`, no un checkout atrasado) qué hace ya ZascArr: parte de la historia puede
   existir (caso C6/D8).
2. **Elegir referencias pertinentes.** Sonarr/Radarr para ciclo de búsqueda, estados,
   importación y operación; Kapowarr/Mylar3 para ediciones, ficheros y metadatos de cómic;
   Suwayomi para capítulos, fuentes de manga, lectura e interoperabilidad. No hay que
   estudiar las cinco a fondo para cada historia.
3. **Inspeccionar contrato, no solo pantalla.** Por cada referencia seleccionada:
   documentación, modelo de datos, ruta de código que toma la decisión, tests, casos
   ambiguos y comportamiento ante fallo. Anotar versión o commit. «No lo encontré» no
   equivale a «no existe».
4. **Traducir, no trasplantar.** Clasificar cada idea con el vocabulario de la sección
   siguiente, explicando diferencias de unidad —grapa/tomo/capítulo—, fuentes españolas, control
   humano, Raspberry Pi y conservación de archivos.
5. **Cerrar con evidencia verificable.** Antes de implementar, escribir al menos un test
   del caso que motivó la historia y otro del límite que el competidor no cubre. Para
   schema, movimiento de ficheros, autenticación o descargas: incluir Postgres/disco/
   cliente real o simulado de forma controlada y plan de reversión.

## Vocabulario de resultado

Cada idea de la ficha acaba en uno de estos resultados. Se decide por idea, no por
aplicación entera («adaptar X de Sonarr, descartar Y de Mylar3»). La ficha propone; decide
el PO.

| Resultado | Qué significa | Cuándo |
|---|---|---|
| **Adoptar** | Tomar la regla o el contrato de la referencia tal cual: mismo problema, misma unidad, sin dependencia nueva. Nunca es copiar código (ver «Barrera legal»). | Todos los supuestos de su modelo valen en ZascArr. |
| **Adaptar** | Tomar la idea cambiando lo que aquí no vale: unidad, fuentes españolas, control humano, Pi, conservación de archivos. | Un supuesto no vale; la ficha dice cuál y qué cambia. |
| **Mejorar** | Hacer algo que la mejor referencia no cubre o cubre mal. Exige evidencia de la debilidad (código, issue, medición), un criterio comprobable de «mejor» y haber igualado antes lo básico. | Hueco probado. Sin evidencia no es mejorar, es opinión. |
| **Construir sobre lo propio** | La mejor base ya está en ZascArr; las referencias aportan patrones o vocabulario. Se registra el sobrecoste. | Lo propio cubre el núcleo y falta pulido o contrato (C6 sobre D8). |
| **Descartar** | No se toma, con motivo: licencia, coste en Pi, otra unidad, referencia archivada, no cubre el requisito. | Lo descartado también consta. |

## Quién hace qué

- **Paso 1:** quien coordina refina la historia, con el comportamiento actual verificado en el
  código vigente.
- **Pasos 2–4:** quien haga el benchmark previo. Entrega a quien coordina la ficha, la matriz ponderada (nivel
  2), los bloques IGUALAR (mínimo competitivo) y MEJORAR (con evidencia) como semilla de
  requisitos en EARS, patrones y anti-patrones para UX/UI, notas para seguridad, NOT RUN y
  caducidad (~60 días, o antes si cambia la referencia o la historia).
- **Quien coordina** la pasa a quien especifica, a UX/UI y a seguridad y lleva al PO el resultado por idea.
  Quien hace el benchmark no escribe en el repo ni en el tablero. La ficha es **insumo, no aprobación**.
- **Paso 5:** quien especifica (criterios de aceptación con los casos de prueba) y quien
  implementa (tests antes de código).

Flujo: Entrada → benchmark previo → decisión del PO → especificación → … → revisión del PO.

## Cuándo y cuánto

**Obligatoria:** P0/P1 de comportamiento nuevo, y cualquier prioridad que toque modelo de
datos, ficheros (mover o escribir), seguridad, exposición o autenticación, el ciclo de
búsqueda y descarga, o fuentes externas; también una historia que el PO reformule.
**No hace falta:** texto o CSS, arreglos evidentes, P2 que no toque lo anterior.

| Nivel | Cuándo | Qué se entrega |
|---|---|---|
| 0 | Texto, CSS, arreglo evidente | Nada; la tarjeta lo dice en una línea |
| 1 | Comportamiento nuevo reversible sobre un servicio que ya existe | Ficha corta: ≤ 2 referencias, sin matriz |
| 2 | Toca modelo, ficheros, seguridad, búsqueda o descarga; difícil de revertir; o hay duda de si ya existe | Ficha completa con matriz ponderada |

Clasifica quien coordina al refinar; el PO puede subir o bajar el nivel.

**Criterios y pesos por defecto (nivel 2; suman 100):** encaje con el flujo del
Coleccionista 25 · coste en Pi 20 · seguridad, legalidad y licencia 20 · cobertura del
requisito core 15 · adaptabilidad al stack y al modelo de datos 10 · mantenimiento de la
referencia 5 · lock-in y coste de salida 5. Se acuerdan con quien coordina o el PO **antes** de
abrir comparativas y se muestran siempre junto al resultado. Se pueden mover como máximo
tres pesos por historia, justificándolo; no se cambian después de ver los candidatos.

## Dónde vive la ficha

`docs/design/benchmark-<ID>-<tema>.md`. Se enlaza desde la fila de la historia en
`docs/BACKLOG.md` y desde la tarjeta; su cabecera cita la historia, la fecha y el SHA
contrastado. Nivel 1: la ficha va dentro de la PR de la historia. Nivel 2: PR solo de
documentos, previa a la historia, porque la decisión debe estar tomada antes de implementar;
es la excepción razonada a «una PR por historia» (§9), ya que la ficha no se despliega. El
DoR de una historia P0/P1 incluye la ficha enlazada (o el nivel 0 justificado).

## Ficha breve por historia

Basta una página enlazada desde el backlog, no un informe enciclopédico:

```text
Historia / problema observado:
Datos reales y medición de partida:
Referencias consultadas (URL, versión/commit):
Cómo lo resuelve cada una:
Supuestos de su modelo que NO valen en ZascArr:
Resultado por idea (adoptar / adaptar / mejorar / construir sobre lo propio / descartar), con motivo:
Invariantes de ZascArr (no mentir, no borrar, confirmación, coste Pi):
Casos de prueba antes de implementar:
Decisión final / ADR si cambia arquitectura:
Matriz (criterios y pesos; solo nivel 2):
IGUALAR / MEJORAR (con evidencia):
NOT RUN:
Caduca (~60 días):
```

## Gate

Ninguna historia P0/P1 de comportamiento nuevo se implementa sin esta ficha. Un arreglo
evidente de texto o CSS no necesita una investigación de medio día: el esfuerzo de
comparación debe ser proporcional al riesgo. Si no existe referencia comparable, documentar
dónde se buscó y continuar; un parche urgente de seguridad puede entrar primero, con
revisión retrospectiva después. La ficha es insumo: no autoriza implementar; el PO decide y
la especificación recoge su decisión.

## Referencias por dominio

| Dominio | Referencias pertinentes |
|---|---|
| Ciclo de búsqueda, estados, importación, operación | Sonarr / Radarr |
| Ediciones, ficheros, metadatos de cómic | Kapowarr / Mylar3 |
| Capítulos, fuentes de manga, lectura, interoperabilidad | Suwayomi; Kaizoku (`oae/kaizoku`, **archivado**: patrón histórico de descarga y de aviso a Komga/Kavita, no referencia viva) |

## Qué nos habría ahorrado

- **B15:** ver una identidad por volumen/edición antes de reutilizar serie + número habría
  expuesto antes la colisión grapa↔ómnibus.
- **Huecos:** comparar cómo cada aplicación define su «episodio/número esperado» habría
  obligado a comprobar que `sort_order` se escribía y que AniList daba capítulos, no tomos.
- **D10:** estudiar la frontera entre resultado mostrado y descarga confirmada habría
  puesto el token firmado y la reclamación atómica en los criterios iniciales.
- **B20:** contrastar hardlinks, metatagging y lectores que escriben habría revelado la
  falta de aislamiento del origen antes de fijar la spec.

## Límites del benchmarking

La comparación no sustituye medir ZascArr: Sonarr anuncia búsqueda manual y gestión de
descargas fallidas; Mylar3 anuncia metatagging, TPB y arcos; Suwayomi, fuentes por
extensión y seguimiento de capítulos. Son soluciones a problemas relacionados, pero
ninguna demuestra por sí misma que una regla funcione con CBR españoles, Tebeosfera y una
Pi. No se infiere soporte de una función por su UI, ni ausencia por no encontrarla. Leer
código no es ejecutarlo: lo no ejecutado se marca NOT RUN, y una ficha caduca (~60 días, o
antes si cambia la referencia o la historia).

## Barrera legal (separada del procedimiento)

Inspirarse en un patrón no es copiar código. Kapowarr y Mylar3 publican GPL-3.0, mientras
Suwayomi declara MPL-2.0 e identifica componentes de terceros bajo Apache-2.0; Kaizoku (`oae/kaizoku`) es MIT y está escrito en TypeScript, y su derivado Rensaio es GPL-3.0. Antes de
reutilizar una implementación hay que revisar la licencia y los avisos del **fichero de
origen** concreto, no asumir que «todas tienen la misma licencia». La licencia del propio
ZascArr está en `LICENSE`; `src/zascarr/LEGAL.md` trata aparte el uso de contenido y las
fuentes, no la reutilización de código de terceros.
