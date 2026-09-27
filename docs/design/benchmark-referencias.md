# Benchmarking de referencias — procedimiento y ficha

> Regla (CLAUDE.md §13): antes de implementar una feature P0/P1 de comportamiento nuevo,
> consultar referencias pertinentes y registrar adoptar/adaptar/descartar con versión y
> pruebas. No inferir soporte de una función por su UI, ni ausencia por no encontrarla.

Esto es un paso habitual de **diseño**, no una obligación de copiar funciones de cinco
aplicaciones antes de cada commit. Responde a cuatro preguntas: ¿qué problema resolvieron,
qué identidad de datos asumieron, qué casos dejaron fuera y qué parte sirve para ZascArr?
La comparación con Kapowarr (2026-09-27) funcionó precisamente porque distinguimos su
vínculo archivo↔issues de nuestra cobertura editorial entre publicaciones.

## Procedimiento

1. **Fijar el problema local primero.** Escribir la historia, un caso real de la
   biblioteca, el comportamiento actual y el resultado deseado. Sin eso, el benchmark se
   convierte en una lista de funciones atractivas.
2. **Elegir referencias pertinentes.** Sonarr/Radarr para ciclo de búsqueda, estados,
   importación y operación; Kapowarr/Mylar3 para ediciones, ficheros y metadatos de cómic;
   Suwayomi para capítulos, fuentes de manga, lectura e interoperabilidad. No hay que
   estudiar las cinco a fondo para cada historia.
3. **Inspeccionar contrato, no solo pantalla.** Por cada referencia seleccionada:
   documentación, modelo de datos, ruta de código que toma la decisión, tests, casos
   ambiguos y comportamiento ante fallo. Anotar versión o commit. «No lo encontré» no
   equivale a «no existe».
4. **Traducir, no trasplantar.** Clasificar cada idea como adoptar, adaptar o descartar,
   explicando diferencias de unidad —grapa/tomo/capítulo—, fuentes españolas, control
   humano, Raspberry Pi y conservación de archivos.
5. **Cerrar con evidencia verificable.** Antes de implementar, escribir al menos un test
   del caso que motivó la historia y otro del límite que el competidor no cubre. Para
   schema, movimiento de ficheros, autenticación o descargas: incluir Postgres/disco/
   cliente real o simulado de forma controlada y plan de reversión.

## Ficha breve por historia

Basta una página enlazada desde el backlog, no un informe enciclopédico:

```text
Historia / problema observado:
Datos reales y medición de partida:
Referencias consultadas (URL, versión/commit):
Cómo lo resuelve cada una:
Supuestos de su modelo que NO valen en ZascArr:
Adoptar / adaptar / descartar, con motivo:
Invariantes de ZascArr (no mentir, no borrar, confirmación, coste Pi):
Casos de prueba antes de implementar:
Decisión final / ADR si cambia arquitectura:
```

## Gate

Ninguna historia P0/P1 de comportamiento nuevo se implementa sin esta ficha. Un arreglo
evidente de texto o CSS no necesita una investigación de medio día: el esfuerzo de
comparación debe ser proporcional al riesgo. Si no existe referencia comparable, documentar
dónde se buscó y continuar; un parche urgente de seguridad puede entrar primero, con
revisión retrospectiva después.

## Referencias por dominio

| Dominio | Referencias pertinentes |
|---|---|
| Ciclo de búsqueda, estados, importación, operación | Sonarr / Radarr |
| Ediciones, ficheros, metadatos de cómic | Kapowarr / Mylar3 |
| Capítulos, fuentes de manga, lectura, interoperabilidad | Suwayomi |

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
Pi. No se infiere soporte de una función por su UI, ni ausencia por no encontrarla.

## Barrera legal (separada del procedimiento)

Inspirarse en un patrón no es copiar código. Kapowarr y Mylar3 publican GPL-3.0, mientras
Suwayomi declara MPL-2.0 e identifica componentes de terceros bajo Apache-2.0. Antes de
reutilizar una implementación hay que revisar la licencia y los avisos del **fichero de
origen** concreto, no asumir que «todas tienen la misma licencia». La licencia del propio
ZascArr está en `LICENSE`; `src/zascarr/LEGAL.md` trata aparte el uso de contenido y las
fuentes, no la reutilización de código de terceros.
