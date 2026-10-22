# U13c (#289) — Aceptación: criterio → prueba

> **Estado: evidencia de implementación. No declara la historia Ready ni cerrada.** No cambia `src/`: el comportamiento que pide #289
> **ya existía** en el SHA de contraste (`b59b00c`, ver `u13c-contraste-dor-289.md`), y lo que faltaba era acreditarlo criterio a criterio.
> La entrega de #289 es, por tanto, **verificación + pruebas fijas + este documento**, que es exactamente el delta de 3 puntos / S que fijó el contraste.
> **Base:** rama de la PR #310 (`5c33bf0`), que trae el contraste y las pruebas E1/D2/E7. **Decisiones D1/D2/D3:** sin cambios; el copy no se toca.

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
| 9 | Ambos temas, 360 px, teclado, sin jerga ni desplazamiento horizontal | **NOT RUN.** Requiere navegador real y lector de pantalla. Hay pruebas de plantilla (controles nativos, sin jerga, sin script propio), que **no sustituyen** esa verificación |

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
relacionados: **257 passed**. Sensibilidad comprobada con una mutación temporal del texto de CA8 en el servicio: la prueba nueva falló, y se revirtió.

## NOT RUN (sin PASS declarado)

Navegador real de #289, 360 px y teclado de esta pantalla, lector de pantalla, prueba de cinco segundos, **rendimiento P1/P2** (p95 ≤ 1.500 ms y
≤ 900 ms, propuestos en el contraste §6.4 y **sin aprobar**; la medición ASGI de #310 no es la medición DoD) y despliegue. La evidencia de navegador
de U13a/U13b (#309) no se hereda como PASS de #289.
