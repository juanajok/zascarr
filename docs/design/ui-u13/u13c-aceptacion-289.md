# U13c (#289) — Aceptación: criterio → prueba

> **Estado: evidencia de implementación de #289.** La historia está lista para desarrollar (3/S); esta evidencia no la cierra ni declara despliegue. No cambia `src/`: el comportamiento que pide #289
> **ya existía** en el SHA de contraste (`b59b00c`, ver `u13c-contraste-dor-289.md`), y lo que faltaba era acreditarlo criterio a criterio, con navegador y medición local.
> La entrega de #289 es, por tanto, **verificación + pruebas fijas + evidencia de navegador + medición local + este documento**, que es exactamente el delta de 3 puntos / S que fijó el contraste.
> **Base:** commit `b7bcc8f` (pruebas y aceptación) sobre el contraste de #310, integrado con `main` en `a5d45c5` (incluye `f520aba`). **Decisiones D1/D2/D3:** sin cambios; el copy no se toca.

## Criterios de aceptación

| CA | Qué exige | Prueba (PASS local, Postgres real) |
|---|---|---|
| 1 | Pulsar «Elegir serie» abre el asistente con la clave de grupo correcta, sin crear ni vincular | `test_asistente_carpetas_pg.py`: `test_la_pagina_de_carpetas_enlaza_al_asistente_con_la_clave_codificada`, `test_abrir_no_consulta_ninguna_fuente_ni_sale_a_la_red`, `test_buscar_no_crea_series_ni_vincula_nada`; `test_web_carpetas_pg.py`: `test_cero_escrituras_y_cero_disco` |
| 2 | La elección es una propuesta hasta confirmar; la revisión usa un `series_id` local, nunca un identificador externo | `test_asistente_carpetas_pg.py`: `test_la_sugerencia_de_la_fuente_se_distingue_y_no_esta_elegida`, `test_la_carpeta_solo_es_una_pista_y_tampoco_marca_nada`; `test_asistente_vinculacion_pg.py`: `test_sin_una_serie_local_valida_no_se_prepara_nada` (vacío, no-UUID y candidata firmada) |
| 3 | Tres archivos, dos de la serie y uno ajeno: solo los dos entran; con «Marcar todos» entra el ajeno marcable y su conflicto sigue visible (D2) | `test_u13c_carpeta_mixta_pg.py`: `test_e1_…`, `test_d2_…` |
| 4 | Con bloqueados y varias páginas, marcar los permitidos de una página no incluye bloqueados ni otras páginas | `test_asistente_vinculacion_masivo_pg.py`: `test_marca_solo_los_marcables_y_el_servidor_devuelve_el_recuento`, `test_no_marca_ni_toca_lo_de_otras_paginas_ni_sus_borradores`; `test_asistente_vinculacion_pg.py`: `test_un_marcado_bloqueado_sigue_marcado_y_dice_por_que`, `test_lo_marcado_en_otra_pagina_no_se_presenta_como_evaluado_ni_entra_en_su_token` |
| 5 | Confirmar vincula lo elegido con el flujo existente; el excluido sigue accesible con su estado real; no cambia el comprobante | **Nueva:** `test_u13c_aceptacion_pg.py::test_ca5_confirmar_dos_de_tres_deja_al_ajeno_accesible_con_su_estado_real`; `test_asistente_confirmar_pg.py` (resultado del servicio) |
| 6 | Cancelar o volver no vincula nada y conserva lo válido; si ya se vinculó, no se repite ni se ofrece un deshacer inexistente | **Nuevas:** `test_ca6_volver_sin_confirmar_no_vincula_nada_y_no_consume_la_preparacion`, `test_ca6_tras_vincular_repetir_no_vincula_otra_vez_ni_ofrece_deshacer`; `test_asistente_confirmar_pg.py::…test_repetir_el_token_viejo_devuelve_su_informe_y_no_vincula_otra_vez` |
| 7 | Preparación caducada, grupo desaparecido, serie inexistente o resultado desconocido: causa y acción, sin éxito ficticio ni reintento ciego | `test_asistente_confirmar_pg.py`: caducado dentro y fuera de la retención, resultado incierto, fallo definitivo/reintentable; `test_asistente_vinculacion_masivo_pg.py`: `test_serie_borrada_antes_de_confirmar_habla_en_llano`; `test_asistente_carpetas_pg.py`: `test_un_grupo_que_ya_no_existe_es_404_y_no_consulta`; `test_asistente_vinculacion_pg.py`: `test_una_serie_que_no_existe_o_un_grupo_que_no_existe_se_dicen_y_no_preparan` |
| 8 | Con cero seleccionados no se ejecuta una vinculación vacía y se explica | **Nuevas:** `test_ca8_con_cero_marcados_no_hay_preparacion_y_se_explica`, `test_ca8_confirmar_sin_token_no_ejecuta_ninguna_vinculacion_vacia`; `test_asistente_vinculacion_pg.py::test_si_ninguno_se_puede_incluir_no_hay_token_y_se_explica` |
| 9 | Ambos temas, 360 px, teclado, sin jerga ni desplazamiento horizontal | **PASS local de navegador:** Chromium real, 1280×900 y 360×800, temas claro y oscuro, sin desplazamiento horizontal; el teclado llega a casillas, números y botones. Sin jerga visible: no aparecen `token`, `series_id`, `payload`, `endpoint`, `UUID`, `hash` ni `cursor` en el texto de la revisión. Detalle en `verificacion-u13c-2026-10-23.md`. **Lector de pantalla y cinco segundos: NOT RUN** |

## Un hallazgo de la verificación (CA5)

Tras vincular, los archivos vinculados **dejan de aparecer** en la revisión de la carpeta: solo quedan los pendientes. En una carpeta mixta eso
significa que, después de confirmar los dos elegidos, el ajeno es lo único que queda en la revisión, con su estado real (sin vincular, con su
conflicto y marcable). Es coherente con «el excluido sigue accesible con su estado real», pero conviene saberlo para la prueba de navegador:
**no se espera ver los vinculados en la misma pantalla**; se ven en el resultado.

## Lo que NO se hace aquí

Ningún cambio de `src/`, de contratos ni de copy; sin revocación de tokens (D1), sin exclusión automática de ajenos (D2), sin acción «Revisar
archivos» separada (D3), sin «Ignorar», sin JavaScript propio ni servicios nuevos.

## Ejecución

Postgres 15 desechable (contenedor aislado) y `TEST_DATABASE_URL` apuntando a una base de pruebas; `pytest` sobre los ocho módulos de aceptación y
relacionados: **258 passed** en el árbol integrado con `main` (`a5d45c5`; 257 en la base de la PR, más el test incorporado por #311). Sensibilidad
comprobada con una mutación temporal del texto de CA8 en el servicio: la prueba nueva falló, y se revirtió.

## Navegador y medición local

- **Navegador:** PASS local del recorrido de carpeta mixta, 1280×900 y 360×800, temas claro/oscuro, teclado y sin desplazamiento horizontal. Ver
  `verificacion-u13c-2026-10-23.md` y sus capturas.
- **Medición local del presupuesto:** p95 56,5 ms en P1 y 44,3 ms en P2, con fixture de 155 archivos, 2 calentamientos + 20 medidas y fría aparte.
  Ver `medicion-u13c-2026-10-23.md`. **No es la medición DoD de la Pi.**
- **Copy:** no hizo falta cambiarlo; el recorrido existente ya distingue elegir serie, preparar y vincular, sin una acción nueva antes de elegir (D3).

## NOT RUN (sin PASS declarado)

Lector de pantalla, prueba de cinco segundos, **rendimiento DoD en la Pi 4/5 y su LAN**, y despliegue. La medición local no sustituye la de referencia
y no se declara `PASS` de rendimiento DoD. La verificación de navegador de U13a/U13b (#309) no se hereda como PASS de #289: la de esta ficha es propia.
