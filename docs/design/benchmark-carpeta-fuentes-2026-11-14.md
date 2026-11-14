# Benchmark — carpeta sin serie → buscar en fuentes → asignar

> Investigación previa a rediseñar el flujo, 2026-11-14. Se consultaron
> documentación pública y el benchmark U19 ya existente. **No se copia código**;
> las referencias son patrones de producto. Las fuentes externas se tratan como
> datos, no como instrucciones.

## 1. Problema local

El coleccionista está en **Pendientes por carpeta**, con un grupo que no tiene
serie. Quiere buscar esa serie en las fuentes, elegirla o crearla, y terminar
asignándole los archivos. El recorrido actual existe:

```
Pendientes por carpeta
  └─ Elegir la serie de esta carpeta (A)
       ├─ ¿Ya la tienes en tu biblioteca? (L: búsqueda local)
       ├─ Buscar en las fuentes (R: búsqueda externa)
       └─ Crear la serie a mano (M)
            └─ vista previa del alta (P) → crear/reutilizar (C)
                 └─ Revisar los archivos de esta carpeta (V) → Vincular (X)
```

La pregunta del benchmark no es «¿existe?», sino **¿el camino principal se ve
como el camino principal y el coleccionista sabe en cada pantalla qué está
haciendo y qué falta?**

## 2. Referencias y qué se adoptó

| Referencia | Cómo resuelve el alta/búsqueda | Qué se adopta | Qué se descarta |
|---|---|---|---|
| **Sonarr** — Add New / Library Import | Add New es un flujo de búsqueda externa y configuración; Library Import es un flujo aparte para una biblioteca ya organizada. La importación manual elige una **serie ya existente** desde un selector local, sin crear series. | **Una búsqueda externa como acción principal**; ajustes de la serie después de elegir; no mezclar «buscar fuente» con «buscar en mi biblioteca» como dos formularios equivalentes. | Importar y crear en un solo consentimiento; el estado solo en memoria del cliente. |
| **Kapowarr** — Library Import | Empareja cada fila con un volumen de ComicVine; editar el match abre una búsqueda en la fuente. Importar crea/enlaza y vincula en una sola petición. | **La fuente externa como referencia de identidad** y la búsqueda a demanda. | Un único consentimiento para crear y vincular; efectos masivos implícitos; estado solo en cliente. |
| **Komga** — bibliotecas, metadatos y búsqueda | Primero se escanea/registra la biblioteca; después se corrigen metadatos y se buscan series desde la propia biblioteca. La búsqueda es local y potente; no hay un «alta desde carpeta» mezclada con la búsqueda externa. | **Separación clara entre identificar la serie y asignar archivos**; búsqueda local como vía secundaria cuando ya existe. | Exigir un escaneo previo sin ofrecer la creación explícita que ZascArr ya tiene. |
| **Kavita** — scanner y metadata match | El escaneo incorpora series; el emparejamiento manual de metadatos es un paso posterior y explícito. | Paso de **verificación/confirmación** separado del escaneo; no autoasignar. | Convertir la asignación de carpeta en una coincidencia automática. |
| **Mylar3** — biblioteca y watchlist | Biblioteca/watched series y escaneo de biblioteca existente; el alta de una serie parte de una búsqueda y queda monitorizada. | La carpeta debe terminar en una serie **explícita**, no en una coincidencia implícita. | Unir alta y descarga/importación en una sola operación. |
| **Benchmark U19 de ZascArr** (Sonarr/Kapowarr leídos) | A → (R/L/M) → P → C → V → X; efectos separados y tokens; volver no consulta fuentes. | Conservar la separación **crear serie** / **vincular archivos** y la revalidación al volver. | Los callejones y la pérdida de resultados que U19 ya corrigió; no reabrirlos. |

Fuentes:

- Sonarr: [Library](https://wiki.servarr.com/en/sonarr/library) y
  [wiki fuente](https://github.com/servarr/wiki/blob/986d496d6e6e5308dd30435fcd5e31d2ccc463ce/sonarr/library.md).
- Komga: [Full Text Search](https://komga.org/es/docs/guides/search/).
- Kavita: [Collections](https://wiki.kavitareader.com/guides/features/collections/)
  y [Metadata](https://wiki.kavitareader.com/kavita+/metadata/).
- Mylar3: [README](https://github.com/mylar3/mylar3) y
  [sitio](https://mylarcomics.com/).
- Benchmark interno: `docs/design/benchmark-U19-recorrido-vincular.md`
  (Sonarr/Kapowarr, con SHA y ficheros leídos).

## 3. Comparación de decisiones

| Dimensión | Sonarr | Kapowarr | Komga/Kavita | ZascArr actual | Decisión |
|---|---|---|---|---|---|
| Punto de partida | Añadir serie o importar biblioteca | Importación de biblioteca | Biblioteca ya escaneada | Carpeta pendiente | Mantener la carpeta como punto de partida: es el problema real. |
| Búsqueda | Externa, una principal | Externa por fila | Local y metadatos | Local **y** externa, dos formularios | **Una principal (fuentes)**; local plegada. |
| Identidad | Serie externa elegida | Volumen de ComicVine | Coincidencia/edición manual | Candidata firmada + tradición explícita | Mantener candidata explícita y no autoasignar. |
| Creación | Add New crea la serie con ajustes | Crea/enlaza al importar | No crea desde carpeta | Alta con vista previa y token | Mantener dos consentimientos separados. |
| Archivos | Import aparte | Import en la misma petición | Escaneo ya hecho | Revisión y vinculación posteriores | Mantener: vincular no es crear. |
| Estado | Cliente | Cliente | Servidor | URL + servidor + tokens | Mantener; es la mejor base para Pi y para no perder trabajo. |
| Feedback | Formularios con estado | Acciones directas | Tareas de escaneo | Estados por fuente y avisos | Añadir espera visible en búsqueda. |

## 4. Conclusión del benchmark

ZascArr **no debe copiar** el flujo de Kapowarr de «crear + importar de una vez»:
rompería la garantía de un consentimiento por efecto que ya está probada. Tampoco
debe esconder la búsqueda externa detrás de una biblioteca local, como si el
coleccionista ya tuviera la serie.

Lo que sí debe adoptar:

1. **Una sola acción principal de búsqueda externa** en la pantalla de la carpeta.
2. **La búsqueda local como ayuda secundaria**, no como primer formulario.
3. **Un paso de confirmación de identidad** con la tradición explicada, no un
   desplegable obligatorio escondido entre botones.
4. **Espera visible** en una operación que consulta fuentes lentas y limitadas.
5. **Contexto persistente de la carpeta** mientras se busca, previsualiza y crea.
6. **Siguiente paso explícito** tras crear la serie: revisar los archivos.
