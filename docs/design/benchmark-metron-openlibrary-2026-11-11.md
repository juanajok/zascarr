# Benchmark — Metron y Open Library como fuentes (2026-11-11)

> **Ficha de benchmarking** según `benchmark-referencias.md` (CLAUDE.md §13).
> **Petición del PO:** «Añade Metron y Open Library a fuentes» (2026-11-11).
> **Persona:** «El Coleccionista»; ZascArr en Pi 4/5, sin SPA ni Node, sin nuevas
> dependencias de runtime.
> **Alcance de esta entrega:** fuentes de **Descubrir** (búsqueda de serie/tomo y alta),
> visibles en **Ajustes**. **No** se integran en el enricher todavía (mismo corte que GCD:
> `config.py` documenta que GCD solo se usa en Descubrir); ampliarlo exige otra historia.

## 1. Cambio de decisión sobre Metron

El benchmark `benchmark-features-coleccionista-metron.md` (2026-11-09) concluyó **no
integrar Metron como fuente** por: cobertura EN/IT, token y datos CC BY-SA 4.0. Esa
decisión queda **reabierta por petición explícita del PO** el 2026-11-11. No se borra la
ficha anterior: este documento registra el cambio y sus condiciones.

Open Library ya estaba recomendada para **ISBN/tomos** en
`benchmark-fuentes-metadatos-referencias.md` (2026-11-09): barata, sin clave y con tomos
españoles; no cubre grapas. Esta entrega la incorpora como fuente de Descubrir.

## 2. Referencias y método

| Fuente | Referencia | Fecha/versión | Licencia / condiciones |
|---|---|---|---|
| Metron | API README (`Metron-Project/metron`, commit `7699fe2`) y blog oficial de uso comercial | API v1.12; consultado 2026-11-11 | Código GPL-3.0; **datos CC BY-SA 4.0**; portadas **no** cubiertas por esa licencia; token; 20 req/min, 5.000/día |
| Open Library | Search API y guía de APIs (`openlibrary.org/developers/api`) | consultado 2026-11-11 | Datos de la IA; API pública sin clave; 1 req/s (3 con User-Agent identificado); no usar como backend masivo; caché |

**Método:** lectura de documentación pública y del código de ZascArr; **no** se ha llamado
a las APIs, no se ha creado cuenta, no se han descargado datos ni se ha copiado código.
Todo lo que no se ha probado en vivo queda **NOT RUN**.

## 3. Qué se adopta

| Idea | Veredicto | Concreción |
|---|---|---|
| Open Library: buscar **obras/tomos** por título y dar de alta una serie local | **Adaptar** | `search.json` con `fields` acotados y `limit`; `key` de obra como id externo (`OL…W`); portada por `cover_i` a través del proxy existente; sin ISBN como identificador de serie (BL-R5 ya lo excluye) |
| Open Library: detalle de obra (título, año, editorial/idioma cuando consten) | **Adaptar** | `GET /works/{key}.json`; no se inventan campos ausentes; no se usa para grapas |
| Metron: buscar series por nombre y dar de alta | **Adoptar con condiciones** | `GET /api/series/?q=…` con `Authorization: Bearer <token>`; una página (los resultados se recortan a `limit`); estados #133 |
| Metron: detalle de serie (año, editorial, tipo, idioma, descripción) | **Adaptar** | `GET /api/series/{id}/`; sin portada (licencia de imágenes aparte); atribución visible y enlace a la ficha |
| Enricher con Metron/Open Library | **Descartar en esta entrega** | Igual que GCD: primero Descubrir; el enricher tiene su propio alcance (ADR 0002) y exige decidir precedencia por campo |
| Descarga masiva / dumps | **Descartar** | Open Library lo prohíbe para la API; Metron tiene cuotas por cuenta; ZascArr consulta solo al pedir |
| Portadas de Metron | **Descartar** | Su licencia no cubre las imágenes; se enlaza la ficha, no se hotlinkea ni se cachea la portada |
| Token de Metron compartido entre instalaciones | **Descartar** | Cada instalación usa su propio token; se guarda en Ajustes y es secreto (patrón `SECRET_FIELDS`) |

## 4. Contrato de integración (primera entrega)

- **Fuente nueva** = `MetadataSource.METRON` y `MetadataSource.OPEN_LIBRARY`.
- Identidad local: `Series.metron_id` (entero único) y `Series.open_library_id` (texto
  único, clave de obra `OL…W`). Migración aditiva; no toca datos existentes.
- Ajustes: interruptores `metron_enabled` y `open_library_enabled`; `metron_token` secreto
  (si falta, `configuracion_incompleta`, sin red). Open Library no necesita clave.
- Descubrir: se consultan solo si están encendidas y, en Metron, con token. Una fuente
  apagada/sin token no se instancia; un fallo no tumba a las demás (#133).
- Resultado: `external_id` = id de Metron o clave de obra; `site_url` = ficha; sin portada
  de Metron. Open Library puede ofrecer `cover_i` (se sirve por el proxy de portadas).
- Atribución: cuando se muestran datos de Metron, la pantalla incluye
  «Datos de Metron, CC BY-SA 4.0» y enlace; Open Library enlaza su ficha.
- Límites: sin ISBN como identificador, sin enricher, sin descarga masiva, sin cambios de
  precedencia.

## 5. Riesgos y límites

- **Licencia Metron:** CC BY-SA 4.0 exige atribución y ShareAlike si se redistribuye. La
  caché privada de ZascArr no se distribuye; la UI sí debe atribuir. Portadas fuera.
- **Cobertura Metron:** EN/IT; no resuelve la edición española. Se ofrece como complemento,
  nunca como sustituto de Tebeosfera/GCD; el orden es neutro.
- **Open Library:** obras/tomos, no grapas; los datos de edición pueden faltar. No se
  inventan campos ni se usa como backend masivo.
- **Rendimiento:** consultas solo al pedir; límites de cortesía por fuente; sin caché
  persistente en esta entrega (Open Library pide cachear; se puede añadir después).
- **Verificación real de API:** **NOT RUN** para ambas; la entrega se acredita con
  transporte simulado y pruebas, y se probará en vivo cuando el PO lo autorice.

## 6. Criterio de hecho

- Descubrir muestra ambas fuentes con estados #133, sin consultar si están apagadas.
- Alta de serie guarda el id externo y `metadata_source` correctos.
- Metron sin token = configuración incompleta; Open Library sin clave funciona.
- Pruebas de cliente (transporte simulado), descubrimiento, alta y UI; suite/CI verde.
- Ficha y limitaciones visibles; sin cambios de enricher.
