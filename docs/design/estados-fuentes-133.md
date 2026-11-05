# Estados por fuente y capacidad (MIT-M8-US01, #133)

> Contrato implementado sobre `origin/main` `3562f3a`. Sin migración, sin dependencias nuevas y sin JS propio.
> Sustituye el estado único de cuatro valores por un conjunto cerrado por fuente **y capacidad**, y hace que la
> interfaz lo pinte sin deducir causas ni plazos.

## 1. Conjunto cerrado

| Estado | Qué significa | Se consulta |
|---|---|---|
| `ok` | La fuente respondió y devolvió al menos un resultado. | Sí |
| `sin_resultados` | La fuente respondió correctamente, pero no encontró coincidencias. | Sí |
| `fallo_transitorio` | La consulta falló por un error de red, HTTP o del cliente. | Sí |
| `configuracion_incompleta` | La fuente está encendida, pero falta la clave o el ajuste necesario. | **No** |
| `limite_de_cortesia` | La fuente pidió esperar (429) y se agotaron los reintentos del cliente. | Sí |
| `fuente_apagada` | La fuente está desactivada en Ajustes. | **No** |

`ESTADOS_DE_FUENTE` es el conjunto cerrado; un valor fuera de él no se presenta como disponible. El estado se
acompaña de la capacidad, el motivo en español y, solo si el contrato lo aporta, los segundos para reintentar.

## 2. Capacidades

En esta entrega la única capacidad **verificada** es `busqueda` para las cuatro fuentes. No se declaran metadatos ni
portadas: que una fuente devuelva una descripción o una portada en un resultado no acredita una capacidad distinta.
La pantalla no presenta una capacidad no verificada como disponible.

## 3. Cómo se decide

`DiscoveryService.search_detallada` clasifica cada fuente después de `asyncio.gather`:

1. Apagada → `fuente_apagada`, sin instanciar el cliente ni hacer tráfico.
2. Comic Vine encendida sin clave → `configuracion_incompleta`, sin tráfico.
3. `CortesiaEnEspera` o `ReintentosAgotados` con 429 → `limite_de_cortesia`; `reintentar_en` solo si el contrato de #134 aporta una espera estimada.
4. Otra excepción → `fallo_transitorio`.
5. Lista vacía → `sin_resultados`; lista con elementos → `ok`.

El limitador compartido de #134 (`utils/peticiones.py`) lanza `CortesiaEnEspera` cuando la espera no cabe en el presupuesto y `ReintentosAgotados` con `ultimo_codigo=429` al agotar los reintentos; DiscoveryService los clasifica como `limite_de_cortesia`. Tebeosfera conserva su limitador compartido: su espera no se convierte en error.

`Busqueda.fuentes` se conserva para los consumidores anteriores; `Busqueda.detalles` añade fuente, capacidad, motivo y
reintento. Una búsqueda construida a mano solo con `fuentes` completa los detalles sin inventar motivo ni plazo.

## 4. Presentación

- **Descubrir:** tras buscar, una lista plegada por fuente muestra nombre, capacidad, estado, motivo y, si consta,
  «Puedes reintentar en N s». Las fuentes apagadas, sin configurar o limitadas no se mezclan con los fallos.
- **Anuncio:** «Ningún resultado» solo se dice si alguna fuente respondió sin coincidencias; si todas fallaron, se
  dice que ninguna respondió. Una fuente apagada no es un fallo.
- La página explica en un `<details>` qué significa cada estado y que, por ahora, solo se busca series.
- El asistente de carpetas usa el mismo contrato y no duplica causas.

## 5. Criterios → pruebas

| # | Criterio de #133 | Pruebas |
|---|---|---|
| 1 | Seis estados por fuente y capacidad; la UI no confunde fallo con ausencia | `test_discovery_estados.py::test_el_conjunto_de_estados_es_cerrado`, `…todas_ok`, `…sin_resultados`, `…fallo_transitorio`, `…limite…`, `…configuracion…`; `test_descubrir_estados_web.py::TestEstadoPorFuente` |
| 2 | Contexto: fuente, capacidad, motivo y reintento solo si consta | `test_descubrir_estados_web.py::test_se_muestra_fuente_capacidad_estado_y_motivo`, `…el_reintento_solo_se_pinta_si_el_contrato_lo_trae` |
| 3 | Solo capacidades verificadas | `test_discovery_estados.py::test_la_capacidad_verificada_es_solo_busqueda`; `test_descubrir_estados_web.py::test_una_capacidad_no_verificada_no_se_presenta_como_disponible` |
| 4 | Fuente apagada sin tráfico | `test_discovery_estados.py::test_una_fuente_apagada_no_se_consulta_y_las_demas_si`, `…todas_apagadas_no_tocan_la_red` |
| 5 | Apagado con alcance y plazo | `test_la_capacidad_verificada_es_solo_busqueda`; `EstadoFuente` lleva fuente, capacidad y motivo; el apagado es por fuente, no global |
| 6 | Recuperación explícita | `test_discovery_estados.py::test_una_fuente_apagada_que_se_enciende_vuelve_a_consultarse` |
| 7 | Límite de cortesía separado | `test_el_limite_de_cortesia_con_plazo_lo_conserva`, `…sin_plazo_no_inventa_uno`; `test_descubrir_estados_web.py::test_el_limite_de_cortesia_es_aparte…` |
| 8 | Configuración incompleta separada | `test_comic_vine_sin_clave_es_configuracion_incompleta_sin_trafico`, `…no_se_confunde_con_un_fallo` |
| 9 | Evidencia PASS/FAIL/NOT RUN | Este documento y la suite; NOT RUN en §6 |

## 6. NOT RUN

- **Fuentes reales:** no se ha consultado ninguna; las pruebas simulan clientes y 429.
- **Pi:** no se ha medido latencia ni memoria; el cambio no añade peticiones.
- **Navegador real:** no se ha repetido una pasada visual en esta revisión; la presentación está cubierta por pruebas
  de plantilla. La medición de U14 sigue siendo la referencia para el indicador.
- **Cortesía de Tebeosfera:** su espera compartida no se convierte en estado (decisión de #134); no se afirma que el
  límite de Tebeosfera se exponga como `limite_de_cortesia`.
