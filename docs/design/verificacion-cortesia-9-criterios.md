# Verificación de los 9 criterios de cortesía compartida (#134, MIT-M8-US02)

> **Estado:** informe de verificación (AC-10, criterio 9). Cierra el entregable PR-3 de
> [`especificacion-cortesia-compartida.md`](especificacion-cortesia-compartida.md) §11.
> **Base:** `4ec55cb` (merge del PR #424), `origin/main` al 2026-11-05, worktree
> `.squad/wt-134c` (rama `docs/134-matriz-cortesia`). No se ha tocado el árbol compartido.
> **Método:** lectura de la spec, del código y de la suite; ejecución de los 18 ficheros de
> prueba relevantes con `httpx.MockTransport` y reloj simulado, **sin Postgres y sin red real**.
> **Resultado:** **707 pruebas, 0 fallos**. Matriz: **40 celdas PASS, 7 FAIL, 7 n/a**. Los
> NOT RUN (red real, Pi, multi-proceso, despliegue real) están separados en §3 y **no se
> cuentan como PASS**.

---

## 0. Cómo leer esta matriz

### 0.1 Regla de evidencia

| Estado | Significado |
|---|---|
| **PASS (D)** | **Prueba directa del consumidor**: un test que falla si ese comportamiento se rompe en ese cliente. |
| **PASS (C)** | **Prueba común + cableado**: el comportamiento se acredita en la envoltura/limitador/UI compartida (un test falla si se rompe) y el consumidor pasa por ahí. No hay prueba específica del consumidor; se indica en la celda. |
| **FAIL (E)** | **Laguna de evidencia**: no hay prueba que sostenga el criterio para ese consumidor. No implica que el código esté mal; implica que la suite no lo acredita. Se dice cuál es el hueco y qué haría falta. |
| **FAIL (I)** | **La implementación contradice el criterio**: se ha comprobado el comportamiento real, no solo la ausencia de test. |
| **NOT RUN** | No medido en este entorno (red real, Pi, multi-proceso, navegador, soak). Solo en §3; nunca se convierte en PASS. |
| **n/a** | El criterio no aplica a ese consumidor, con el motivo escrito en la celda. |

**PASS significa acreditado con la suite simulada**, no validado contra servicios reales. La
validación de entorno real es NOT RUN (§3) y no se suma a ningún PASS.

### 0.2 Cómo se ha ejecutado

```bash
cd /mnt/Datos/Documentos/Repos/zascarr/.squad/wt-134c
PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.venv-ci/bin/python -m pytest \
  tests/test_cortesia.py tests/test_peticiones.py tests/test_clientes_cortesia.py \
  tests/test_cover_cortesia.py tests/test_tebeosfera_cortesia.py tests/test_cortesia_estado.py \
  tests/test_web_estado_cortesia.py tests/test_forum_scraper.py tests/test_discovery_estados.py \
  tests/test_descubrir_estados_web.py tests/test_web_ajustes.py tests/test_enricher.py \
  tests/test_cover_ssrf.py tests/test_cover.py tests/test_discovery_service.py \
  tests/test_clientes_fuente_apagada.py tests/test_fuentes_apagadas_por_defecto.py \
  tests/test_web_discovery.py -q
# 707 passed in 21.66s
```

- Python 3.14 (`.venv-ci`), `pytest`/`pytest-asyncio`.
- Sin `TEST_DATABASE_URL`: ninguna prueba de esta lista toca Postgres.
- Ninguna prueba sale a la red: todo es `httpx.MockTransport` o transporte inyectado, con
  reloj/`dormir` simulados.
- Los tests se localizaron por nombre con `grep -rn` en `tests/`; las citas `fichero:línea`
  son del árbol `4ec55cb`.

### 0.3 Matriz criterio × consumidor

Los consumidores son los seis del alcance de #134: **Comic Vine**, **AniList**, **GCD**,
**foro**, **Tebeosfera** y **portadas** (descarga externa por host). «Foro» incluye su
`login()`; «portadas» es el camino de `utils/url_portada.py` / `utils/cover.py`.

| Criterio (issue) | Comic Vine | AniList | GCD | Foro | Tebeosfera | Portadas |
|---|---|---|---|---|---|---|
| **1. Ámbito de coordinación** | PASS (D)<br>`tests/test_clientes_cortesia.py:98` | PASS (C)<br>`tests/test_clientes_cortesia.py:212`<br>`tests/test_peticiones.py:430` | PASS (C)<br>`tests/test_clientes_fuente_apagada.py:53`<br>`tests/test_peticiones.py:430` | PASS (C)<br>`tests/test_clientes_fuente_apagada.py:66`<br>`tests/test_peticiones.py:430` | PASS (D)<br>`tests/test_tebeosfera_cortesia.py:105`<br>`:125` | PASS (D)<br>`tests/test_cover_cortesia.py:119` |
| **2. Dos niveles (fuente + host)** | PASS (C)<br>`tests/test_cortesia.py:205`<br>`:212` | PASS (C)<br>`tests/test_cortesia.py:205`<br>`:212` | **FAIL (E)**<br>solo `tests/test_cortesia.py:173` (política), sin prueba de cola/host de GCD | **FAIL (E)**<br>`tests/test_forum_scraper.py:68` usa `rate_limit=0`; ningún test mide el escalonado | PASS (D)<br>`tests/test_tebeosfera_cortesia.py:153`<br>`:105` | n/a: por diseño solo hay nivel **host** (§3.2.4); host acreditado en `tests/test_cover_cortesia.py:92` |
| **3. Redirecciones acotadas** | PASS (D)<br>`tests/test_clientes_cortesia.py:124`<br>`:184` | PASS (D)<br>`tests/test_clientes_cortesia.py:212`<br>`:252` | **FAIL (E)**<br>sin prueba de redirección ni de `follow_redirects=False` en `GCDClient` | PASS (D)<br>`tests/test_forum_scraper.py:250`<br>`:268`<br>`:279` | PASS (D)<br>`tests/test_tebeosfera_cortesia.py:246`<br>`:268`<br>`:336`<br>`:344` | PASS (D)<br>`tests/test_cover_cortesia.py:92`<br>`:106`<br>`tests/test_cover_ssrf.py:280` |
| **4. Reintentos / 429 / apagada** | PASS (D)<br>`tests/test_clientes_cortesia.py:148`<br>`:166`<br>`:189`<br>`tests/test_enricher.py:83` | PASS (D)<br>`tests/test_enricher.py:117`<br>`tests/test_cortesia.py:173` | **FAIL (E)**<br>`tests/test_clientes_fuente_apagada.py:53` cubre solo apagada; sin 429/reintento de GCD | **FAIL (E)**<br>`tests/test_clientes_fuente_apagada.py:66` cubre solo apagado; sin 429/reintento | PASS (C)<br>`tests/test_cortesia.py:177` (1 intento)<br>`tests/test_tebeosfera_cortesia.py:363` (500 → sin resultados) | PASS (D)<br>`tests/test_cover_cortesia.py:113`<br>`:136`<br>`:171` |
| **5. Espera visible sin promesas** | PASS (D)<br>`tests/test_clientes_cortesia.py:277`<br>`:297` | PASS (C)<br>`tests/test_discovery_estados.py:277`<br>`src/zascarr/services/anilist.py:92-103` | PASS (C)<br>`tests/test_discovery_estados.py:277`<br>`src/zascarr/services/gcd.py:115-127` | **FAIL (I)**<br>`src/zascarr/services/forum_scraper.py:186-197` convierte `CortesiaEnEspera` en `[]`; ver §1.5 | PASS (C)<br>`tests/test_discovery_estados.py:277`<br>`src/zascarr/services/tebeosfera.py:185-195` | PASS (D)<br>`tests/test_cover_cortesia.py:182`<br>`:126`<br>`tests/test_cover_ssrf.py:547` |
| **6. Coordinación declarada** | PASS (C)<br>`tests/test_cortesia.py:314`<br>`tests/test_cortesia_estado.py:161` | PASS (C)<br>ídem | PASS (C)<br>ídem | PASS (C)<br>ídem | PASS (C)<br>ídem | PASS (C)<br>`docs/design/cortesia-compartida.md:15-16` |
| **7. FIFO y cancelación** | PASS (C)<br>`tests/test_cortesia.py:227`<br>`:251`<br>`:265` | PASS (C)<br>ídem | PASS (C)<br>ídem | PASS (C)<br>ídem | PASS (D)<br>`tests/test_tebeosfera_cortesia.py:197`<br>`:351`<br>`:372` | PASS (C)<br>ídem |
| **8. Observabilidad mínima** | PASS (C)<br>`tests/test_cortesia.py:314`<br>`tests/test_cortesia_estado.py:113`<br>`tests/test_web_estado_cortesia.py:69` | PASS (C)<br>ídem | PASS (C)<br>ídem | PASS (C)<br>ídem | PASS (C)<br>ídem | **FAIL (I)**<br>el host usado solo por portadas sale con `intervalo_min_s: 0.0` y `fuentes: []`; ver §1.8 |
| **9. Evidencia verificable** | n/a: criterio global (esta matriz y la suite); ver §1.9 | n/a | n/a | n/a | n/a | n/a |

**Recuento:** 40 PASS (15 D + 25 C), 7 FAIL (5 E + 2 I), 7 n/a. No hay celdas NOT RUN: los
NOT RUN son transversales (§3).

> **Nota sobre «FAIL (E)»:** no significa «roto». Significa que hoy la suite no tiene una
> prueba que se ponga roja si ese consumidor deja de cumplir el criterio. GCD es el caso
> más claro: su cableado a la envoltura está probado solo por la puerta de fuente apagada;
> no hay ninguna petición exitosa de `GCDClient` en la suite. Se detalla en §2.

---

## 1. Criterio por criterio: AC de la spec y prueba concreta

La trazabilidad de la spec (§13) asigna a cada criterio del issue estos AC:

| Criterio | AC que lo cubre |
|---|---|
| 1. Ámbito de coordinación | AC-01, AC-07, AC-15 |
| 2. Presupuesto por fuente y destino | AC-02 |
| 3. Redirecciones acotadas | AC-03, AC-12 |
| 4. Reintentos / 429 / fuente apagada | AC-04, AC-05, AC-15 |
| 5. Espera visible sin promesas | AC-06, AC-13, AC-14, AC-18 |
| 6. Fallos de coordinación visibles | AC-07, AC-09 |
| 7. Prioridad y cancelación | AC-08 |
| 8. Observabilidad mínima | AC-09, AC-17 |
| 9. Evidencia verificable | AC-10, AC-19 |

AC-11 a AC-19 son transversales (Tebeosfera, portadas, `to_thread`, Descubrir, fuente
apagada, espera ≠ fallo, sin dependencias, estados, coste). Se verifican en el anexo §6.

### 1.1 Criterio 1 — Ámbito de coordinación (AC-01, AC-07, AC-15)

**Qué exige.** Dos clientes distintos de la misma fuente comparten la cola del proceso;
fuentes distintas no se bloquean entre sí; el snapshot y la documentación declaran qué
está coordinado y qué no.

**Pruebas que lo sostienen hoy en `main`.**

- `tests/test_clientes_cortesia.py::TestComicVine::test_busca_por_la_cola_y_sin_cadencia_propia`
  (L98): dos búsquedas seguidas del mismo cliente esperan 1,0 s; no existe
  `_rate_limit` ni `_last_req` en la instancia.
- `tests/test_clientes_cortesia.py::TestAniList::test_post_por_la_cola_y_307_conserva_cuerpo`
  (L212): AniList entra por la misma cola y tampoco tiene cadencia propia.
- `tests/test_peticiones.py::TestPresupuestoDelLlamador::test_dos_clientes_de_la_misma_fuente_comparten_la_cola`
  (L430): dos `AsyncClient` distintos de la misma fuente se escalonan.
- `tests/test_clientes_fuente_apagada.py::test_gcd_apagada_no_envia` (L53) y
  `::test_foro_apagado_no_envia_ni_en_login_ni_en_busqueda` (L66): GCD y foro (incluido
  `login`) pasan por la envoltura común; si dejaran de hacerlo, no se lanzaría
  `FuenteApagada` y estos tests fallarían.
- `tests/test_tebeosfera_cortesia.py::TestInstanciasYCaminosDistintos::test_dos_busquedas_seguidas_con_clientes_distintos_se_espacian`
  (L105) y `::test_el_camino_de_descubrir_y_el_del_enricher_comparten_el_limite` (L125):
  Tebeosfera comparte el límite entre instancias y caminos.
- `tests/test_cover_cortesia.py::TestCadaSaltoPorLaColaDelHost::test_hosts_distintos_no_se_bloquean_y_el_mismo_si`
  (L119): las portadas comparten la cola **del host**; dos hosts distintos no se bloquean.
- `tests/test_cortesia.py::TestSnapshot::test_forma_y_datos_sin_secretos` (L314): el
  snapshot lista las seis fuentes declaradas.

**Código que lo implementa.** `src/zascarr/utils/cortesia.py:400-468` (una cola por fuente
y otra por origen normalizado, estado de proceso) y `src/zascarr/utils/peticiones.py:228-338`
(cada petición y cada salto pasan por `cortesia.esperar`). Los clientes: CV
`comic_vine.py:81-116`, AniList `anilist.py:74-99`, GCD `gcd.py:81-122`, foro
`forum_scraper.py:85-184`, Tebeosfera `tebeosfera.py:125-196`, portadas
`url_portada.py:221-263`.

**Estado.** PASS en los seis. GCD y foro son PASS (C): el cableado está probado por la
puerta de fuente apagada y la cola compartida por la prueba genérica; no hay una prueba de
escalonado propia de esos dos clientes (se anota en §5).

### 1.2 Criterio 2 — Dos niveles: fuente y host efectivo (AC-02)

**Qué exige.** Entre dos peticiones a la misma fuente, al menos su `intervalo_min_s`; entre
dos peticiones al mismo host efectivo, el **máximo** de los intervalos de las fuentes que
lo usan; la primera no espera; no hay limitador por instancia; `http`/`https` y puertos
distintos son colas distintas.

**Pruebas que lo sostienen hoy en `main`.**

- `tests/test_cortesia.py::TestDosNiveles::test_la_primera_no_espera_y_la_segunda_cumple_el_intervalo_de_fuente`
  (L205).
- `tests/test_cortesia.py::TestDosNiveles::test_el_host_efectivo_cumple_el_maximo_de_sus_fuentes`
  (L212): CV deja 1,0 s en el host y AniList espera 1,5 s (el máximo).
- `tests/test_cortesia.py::TestDosNiveles::test_fuente_y_host_se_aplican_a_la_vez` (L218).
- `tests/test_cortesia.py::TestOrigenNormalizadoComoHost::test_mismo_host_distinto_esquema_o_puerto_son_colas_distintas`
  (L361): `https`, `http` y otro puerto son colas distintas; el mismo origen espera el
  máximo (2,5 s en el ejemplo).
- `tests/test_cortesia.py::TestPortadaNoContagiaSuIntervaloAlHost::test_la_fuente_sintetica_portada_no_infla_el_intervalo_del_host`
  (L398): la portada no contagia su 2,5 s a Comic Vine.
- `tests/test_tebeosfera_cortesia.py::TestInstanciasYCaminosDistintos::test_el_limitador_es_el_compartido_del_sitio_y_no_uno_propio`
  (L153).
- `tests/test_cover_cortesia.py::TestCadaSaltoPorLaColaDelHost::test_cada_salto_espera_y_consume_el_hueco_del_host`
  (L92): el nivel host de portadas, con el intervalo del mapa allowlist→fuente.

**Código.** `utils/cortesia.py:437-444` (`_intervalo_de_host` = máximo de las fuentes) y
`utils/peticiones.py:183-193` (host = origen de la URL del salto).

**Estado.** PASS en CV, AniList y Tebeosfera; PASS (D) en el nivel host de portadas. En
portadas el nivel **fuente** es n/a por la excepción declarada §3.2.4 (su URL no lleva
fuente). **FAIL (E)** en GCD y foro: no hay prueba que mida su escalonado. La tabla
`tests/test_cortesia.py:173` acredita el **valor** de la política de GCD (2,0 s) y de foro
(2,0 s), pero no que esos clientes la apliquen a su cola.

### 1.3 Criterio 3 — Redirecciones acotadas (AC-03, AC-12)

**Qué exige.** `follow_redirects=False` en todos los clientes; tope de 3 saltos; 301/302/303
pasan a GET sin cuerpo, 307/308 conservan método y cuerpo; cada salto pasa por la cola y
consume presupuesto; `Location` ausente/malformado/con credenciales/otro origen o fuera de
allowlist falla **sin enviar**; en portadas cada salto revalida allowlist, DNS/IP y tamaño.

**Pruebas que lo sostienen hoy en `main`.**

- `tests/test_peticiones.py::TestRedirecciones` completo (L85-209): 302 a GET sin cuerpo
  (L86), 301 desde POST (L111), 307/308 (L127), cadenas de 1–3 (L144), cuarto salto
  (L159), bucle (L171), destinos prohibidos (L184), allowlist explícita (L197).
- `tests/test_peticiones.py::TestCredencialesEntreOrigenes` (L482-539): un salto a otro
  origen no reenvía `Authorization`/`Cookie`/`X-Api-Key` ni cuerpo; el mismo origen 307 sí
  conserva cuerpo y credenciales.
- `tests/test_peticiones.py::TestLocalizacionesInvalidas` (L443-475): `Location` malformado
  o error de protocolo no se reintentan.
- Comic Vine: `tests/test_clientes_cortesia.py::TestComicVine::test_sigue_302_a_mano_y_repite_la_clave`
  (L124) y `::test_el_cliente_se_abre_sin_redirecciones_automaticas` (L184).
- AniList: `tests/test_clientes_cortesia.py::TestAniList::test_post_por_la_cola_y_307_conserva_cuerpo`
  (L212) y `::test_el_cliente_se_abre_sin_redirecciones_automaticas` (L252).
- Foro: `tests/test_forum_scraper.py::TestRedirecciones` (L235-289),
  `::test_el_cliente_por_defecto_no_sigue_redirecciones_solo` (L279) y
  `::TestLoginConRedireccion::test_login_con_302_y_set_cookie_conserva_la_sesion` (L349).
- Tebeosfera: `tests/test_tebeosfera_cortesia.py::TestRedirecciones` (L242-384), con
  `::test_el_cliente_no_sigue_redirecciones_por_su_cuenta` (L246), cadena (L259), tope
  (L268), otro origen (L289), sin `Location` (L305), malformado (L312), 301/302/303 (L336)
  y 307/308 (L344).
- Portadas: `tests/test_cover_cortesia.py::test_cada_salto_espera_y_consume_el_hueco_del_host`
  (L92), `::test_el_cuarto_salto_falla_sin_enviarlo` (L106), y
  `tests/test_cover_ssrf.py::TestDescarga` (L200-383), con
  `::test_cada_salto_se_resuelve_y_se_valida_otra_vez` (L280) y
  `::test_todos_los_codigos_de_redireccion_se_tratan_a_mano` (L318).

**Código.** `utils/peticiones.py:170-221` (`_seguir_redirecciones`) y
`utils/url_portada.py:242-263` (portadas).

**Estado.** PASS en CV, AniList, foro, Tebeosfera y portadas. **FAIL (E)** en GCD: no hay
ninguna prueba de redirección con `GCDClient` ni que compruebe que su `AsyncClient` se abre
con `follow_redirects=False` (`gcd.py:92-102` lo hace, pero no se prueba). Un cambio a
redirecciones automáticas en GCD pasaría la suite.

### 1.4 Criterio 4 — Reintentos, 429 y fuente apagada (AC-04, AC-05, AC-15)

**Qué exige.** Solo se reintentan transitorios (red/timeout, 408, 5xx, 429), con backoff
2, 4, 8… (tope 30) y el máximo de la política; un 4xx no transitorio y un error de parseo
no se reintentan; un `Retry-After` (segundos o fecha HTTP) bloquea fuente y host para todos;
un bloqueo que no cabe en el presupuesto es espera visible (no duerme); una fuente apagada
no reserva, no envía y no reintenta (la prueba de Ajustes es la excepción explícita).

**Pruebas que lo sostienen hoy en `main`.**

- `tests/test_peticiones.py::TestReintentos` (L212-273): transitorios 408/500/503 con
  backoff 2 y 4 hasta el máximo (L214), timeout (L223), error de red (L237), 4xx sin
  reintento (L251), backoff no se acelera (L259), backoff que no cabe → espera visible
  (L266).
- `tests/test_peticiones.py::TestRetryAfter` (L275-353): 429 comparte fuente y host (L276),
  el segundo consumidor no se salta el bloqueo (L291), fecha HTTP (L311), inválido →
  backoff (L333), parser (L342).
- `tests/test_peticiones.py::TestFuenteApagada` (L355-415): no reserva ni envía (L356), se
  apaga durante la espera (L367) o entre saltos (L389), y la prueba de Ajustes es la
  excepción (L407).
- Comic Vine: `tests/test_clientes_cortesia.py::TestComicVine::test_un_500_se_reintenta_con_backoff`
  (L148), `::test_un_400_no_se_reintenta` (L166), `::test_un_error_de_parseo_no_se_reintenta`
  (L189); `tests/test_enricher.py::TestComicVineRetry::test_reintenta_en_429_y_devuelve_datos_al_reintentar`
  (L83).
- AniList: `tests/test_enricher.py::TestAniListRetry::test_reintenta_en_429_y_devuelve_datos_al_reintentar`
  (L117); política de 3 intentos en `tests/test_cortesia.py:173`.
- Tebeosfera: `tests/test_cortesia.py:177` (política de **1** intento) y
  `tests/test_tebeosfera_cortesia.py::test_un_fallo_en_un_salto_cuenta_y_devuelve_sin_resultados`
  (L363): un 500 devuelve «sin resultados», no se propaga como excepción.
- Portadas: `tests/test_cover_cortesia.py::TestCadaSaltoPorLaColaDelHost::test_un_429_no_se_reintenta`
  (L113), `::test_un_bloqueo_mayor_que_el_presupuesto_no_envia` (L126),
  `::TestFuenteApagadaDuranteLaEspera::test_si_la_fuente_se_apaga_durante_la_espera_no_se_descarga`
  (L136), `::TestFuenteApagadaPorSalto::test_un_salto_a_una_fuente_apagada_no_se_descarga`
  (L158) y `::TestCoverFetch::test_la_fuente_apagada_no_recibe_portadas` (L171).

**Código.** `utils/peticiones.py:253-338` (bucle de intentos, 429, `Retry-After`, backoff)
y `utils/cortesia.py:484-500` (`bloquear`).

**Estado.** PASS en CV, AniList, Tebeosfera y portadas. **FAIL (E)** en GCD y foro: la única
prueba de esos dos clientes en este criterio es la de fuente apagada
(`tests/test_clientes_fuente_apagada.py:53` y `:66`); no hay prueba de 429, de
`Retry-After` compartido ni del máximo de reintentos (2) aplicado a GCD/foro. El mecanismo
común está probado; el cableado de esos dos clientes, no.

### 1.5 Criterio 5 — Espera visible sin promesas (AC-06, AC-13, AC-14, AC-18)

**Qué exige.** Si la espera estimada no cabe en el presupuesto (10 s UI, 30 s fondo, 5 s
portada), no se envía y se muestra un aviso con la estimación, sin prometer recuperación;
Descubrir distingue `espera` de `error`; Ajustes la muestra como aviso neutro; Estado pinta
«En espera»/«Bloqueada temporalmente»; una portada sin turno deja marcador y no cachea la
ausencia.

**Pruebas que lo sostienen hoy en `main`.**

- CV/Ajustes: `tests/test_clientes_cortesia.py::TestPruebaDeAjustes::test_si_hay_que_esperar_lo_dice_sin_prometer_recuperacion`
  (L277), `::test_un_429_real_en_la_prueba_muestra_la_espera` (L297) y
  `tests/test_web_estado_cortesia.py::TestAjustes::test_la_espera_de_la_prueba_es_un_aviso_neutro`
  (L147).
- Descubrir: `tests/test_discovery_estados.py::test_cortesia_en_espera_es_limite_de_cortesia_con_el_aviso_6_5`
  (L277) y `::test_la_espera_sin_estimacion_no_inventa_segundos` (L288);
  `tests/test_descubrir_estados_web.py::TestAvisoDeCortesia::test_si_no_se_consulto_ninguna_por_cortesia_manda_la_frase_agregada`
  (L415) y `::test_la_ui_muestra_el_aviso_6_5_con_estimacion` (L422).
- Estado: `tests/test_cortesia_estado.py::TestFilasDeEstado::test_bloqueo_espera_apagada_y_sin_configurar`
  (L113) y `tests/test_web_estado_cortesia.py::TestEstadoHtml::test_pinta_la_seccion_con_los_textos_y_estados_de_la_spec`
  (L97).
- Fondo: `tests/test_enricher.py::test_espera_o_apagada_no_es_fallo_ni_consume_los_30_dias`
  (L613).
- Portadas: `tests/test_cover_cortesia.py::TestCoverFetch::test_la_espera_mayor_que_el_presupuesto_deja_marcador_sin_cachear`
  (L182) y `tests/test_cover_ssrf.py::test_el_404_de_descubrir_por_cortesia_tampoco_se_cachea`
  (L547) / `::test_el_404_por_cortesia_no_deja_cachear_la_ausencia` (L566).

**Código.** `utils/peticiones.py:190-191, 256-258` y `utils/cortesia.py:376-378` emiten
`CortesiaEnEspera`; `services/discovery.py:242-260` lo mapea a `limite_de_cortesia`;
`web/ajustes.py:410-415` lo convierte en aviso; `utils/cover.py:214-220` devuelve `False`
sin cachear.

**Estado.**

- **CV: PASS (D)** por la prueba de Ajustes. En Descubrir el aviso se acredita con el
  mapeo común (PASS C).
- **AniList, GCD y Tebeosfera: PASS (C)** con reserva: el aviso de Descubrir se prueba con
  un doble de `AniListClient` (`tests/test_discovery_estados.py:277`) y el mapeo es común a
  las cuatro fuentes; **no hay prueba de que la `CortesiaEnEspera` salga del cliente real**
  de AniList/GCD/Tebeosfera. El código lo deja propagar (`anilist.py:92-103`,
  `gcd.py:115-127`, `tebeosfera.py:185-195`), pero es inspección, no test.
- **Portadas: PASS (D)**.
- **Foro: FAIL (I).** `ForumScraper.use_ipb_search` atrapa `Exception` alrededor de `_get`
  y devuelve `[]` (`src/zascarr/services/forum_scraper.py:186-197`). `_get` sí lanza
  `CortesiaEnEspera` (`:169-174`), así que una espera por `Retry-After` o por bloqueo se
  convierte en «sin resultados» y además se registra como `forum.search_failed` con
  `logger.exception`, justo lo contrario de AC-16 («no se registra fallo»). El
  `_forum_fallback` del orchestrator vuelve a atrapar `Exception` y registra
  `orchestrator.forum_fallback_error` (`src/zascarr/services/orchestrator.py:573-574`).

  Comprobación manual (no es un test de la suite, no se ha añadido al repo): con un
  `CortesiaProceso` con la fuente `foro` bloqueada 60 s y `espera_max_s=5`, `_get` lanza
  `CortesiaEnEspera` con motivo `bloqueo_fuente`; `use_ipb_search("thorgal")` devuelve `[]`
  y registra `forum.search_failed`. Es el escenario de un 429 real con `Retry-After` mayor
  que el presupuesto del foro.

### 1.6 Criterio 6 — Fallos de coordinación visibles / coordinación declarada (AC-07, AC-09)

**Qué exige.** El snapshot declara siempre `coordinacion: "proceso"`; la documentación y
la UI dicen en llano que no hay coordinación entre procesos o instalaciones; no se presenta
el límite local como global; no se finge detectar multi-worker.

**Pruebas que lo sostienen hoy en `main`.**

- `tests/test_cortesia.py::TestSnapshot::test_forma_y_datos_sin_secretos` (L314): el
  snapshot tiene `coordinacion: "proceso"`, las seis fuentes y hosts sin URL.
- `tests/test_cortesia.py::TestDosNiveles::test_dos_registros_independientes_no_se_coordinan`
  (L241): dos registros independientes no se coordinan y ambos declaran `"proceso"`. Es la
  prueba del **límite**, no de soporte multi-proceso.
- `tests/test_cortesia_estado.py::TestDocumentoDeCoordinacion::test_el_doc_y_claude_declaran_proceso_unico_y_sin_coordinacion`
  (L161): exige en `docs/design/cortesia-compartida.md` y `CLAUDE.md` las frases «un solo
  proceso», «No hay detección de multi-worker», «otras instalaciones», «coordinacion» y
  «no se coordinan».
- `tests/test_web_estado_cortesia.py::TestEstadoHtml::test_pinta_la_seccion_con_los_textos_y_estados_de_la_spec`
  (L97) y `::TestAjustes::test_politica_dinamica_y_coordinacion` (L140): la UI lo dice en
  llano.
- `docs/design/cortesia-compartida.md:7-31` declara coordinados (CV, AniList, Tebeosfera,
  GCD, foro, portadas por host) y no coordinados (otras instalaciones, otros procesos,
  scripts/cron, LAN, webhooks).

**Código.** `utils/cortesia.py:570-575` (`coordinacion: "proceso"`),
`services/cortesia_estado.py:21-25` (textos), `Dockerfile:56-60` (`--workers 1`).

**Estado.** PASS (C) en los seis: es una declaración global, no un comportamiento por
consumidor; la prueba y el documento cubren a todos. No hay detección automática de
multi-worker y no se presenta como si la hubiera.

### 1.7 Criterio 7 — FIFO y cancelación (AC-08)

**Qué exige.** Concurrentes en FIFO sin prioridades; cancelar antes de autorizar no consume
hueco ni deja candado; cancelar después de autorizar consume el hueco (no se devuelve); la
siguiente petición respeta el intervalo; nadie queda bloqueado.

**Pruebas que lo sostienen hoy en `main`.**

- `tests/test_cortesia.py::TestDosNiveles::test_concurrentes_fifo_y_escalonadas` (L227):
  cinco concurrentes de AniList se escalonan 1,5 s y la primera no espera.
- `tests/test_cortesia.py::TestCancelacionYPresupuesto::test_cancelar_antes_de_autorizar_no_consume_ni_deja_candado`
  (L251), `::test_cancelar_tras_autorizar_la_fuente_consume_ese_hueco` (L265) y
  `::test_el_presupuesto_agotado_no_duerme_ni_envia` (L287).
- Tebeosfera: `tests/test_tebeosfera_cortesia.py::TestCancelacionYBucles::test_cancelar_una_busqueda_en_espera_no_rompe_el_espaciado_de_las_demas`
  (L197), `::test_busquedas_concurrentes_con_redirecciones_siguen_separadas` (L351) y
  `::test_cancelar_entre_saltos_no_estropea_el_espaciado_posterior` (L372).

**Código.** `utils/cortesia.py:340-397` (`Turno.__aenter__`/`_autorizar`/`liberar`) y el
`Lock` FIFO de asyncio.

**Estado.** PASS (D) en Tebeosfera. PASS (C) en CV, AniList, GCD, foro y portadas: la cola
es la misma y la cancelación se prueba en el limitador común; no hay una prueba de
cancelación con esos consumidores concretos. Para portadas, la cancelación de la tarea
durante la espera no tiene prueba propia.

### 1.8 Criterio 8 — Observabilidad mínima (AC-09, AC-17)

**Qué exige.** `GET /api/estado/cortesia` (solo lectura, `Cache-Control: no-store`) y
`/ui/estado` muestran fuente, intervalo, intentos, cola, siguiente hueco, reintentos y
bloqueo; con contraseña exige sesión como el resto; no aparece URL, query, clave,
credencial ni dato personal; el HTML pinta los textos de §6.3.

**Pruebas que lo sostienen hoy en `main`.**

- `tests/test_cortesia.py::TestSnapshot::test_forma_y_datos_sin_secretos` (L314) y
  `::test_el_estado_esta_acotado` (L339): seis fuentes, máximo 3 intentos, sin URL/query.
- `tests/test_cortesia_estado.py::TestSnapshotPublico::test_solo_publica_hosts_de_la_allowlist_y_sin_esquema_ni_puerto`
  (L77), `::test_no_hay_url_query_claves_ni_esquema_en_el_json` (L84) y
  `::test_hosts_repetidos_por_origen_se_unen_por_nombre` (L93).
- `tests/test_cortesia_estado.py::TestFilasDeEstado` (L113), `::test_nota_de_bloqueo_y_de_apagada`
  (L126), `::test_apagadas_no_cuentan_como_fallo` (L135) y `::TestPoliticaDeAjustes`
  (L143/L154).
- `tests/test_web_estado_cortesia.py::TestEndpoint::test_devuelve_el_snapshot_con_no_store_y_sin_hosts_fuera_de_la_allowlist`
  (L69), `::test_exige_sesion_como_el_resto_de_la_api` (L83),
  `::TestEstadoHtml::test_pinta_la_seccion_con_los_textos_y_estados_de_la_spec` (L97) y
  `::test_no_promete_recuperacion_ni_fecha` (L117).
- Código: `src/zascarr/api/estado.py:18-23` (`no-store`), `src/zascarr/web/estado.py:36-42`
  (pintado en servidor), `src/zascarr/services/cortesia_estado.py:59-93` (lista blanca de
  hosts) y `utils/cortesia.py:515-575` (snapshot).

**Estado.** PASS (C) en CV, AniList, GCD, foro y Tebeosfera: el snapshot lista las seis
fuentes y la UI las pinta; no hay una prueba por fuente, sino una prueba del snapshot común
más la tabla de políticas. **FAIL (I) en portadas:** el nivel host del snapshot no declara
el intervalo de una portada. Si un host solo se usa para portadas (p. ej.
`s4.anilist.co`), `CortesiaProceso.snapshot()` devuelve `fuentes: []`, `intervalo_min_s: 0.0`
y `siguiente_hueco_s: 0.0`, aunque el espaciado real sea 1,5 s (`intervalo_de_portada`), y
la fuente `portada` sale con el intervalo desconocido 2,5 s en vez del de cada host. El
espaciado real no está roto (el `Turno` usa `intervalo_s` explícito,
`utils/cortesia.py:369-382`), pero el snapshot publica un dato falso y §3.2.4 pide
declararlo. No hay test que lo cubra. Comprobado a mano con un `CortesiaProceso` y
`snapshot_publico`; no se ha añadido al repo.

### 1.9 Criterio 9 — Evidencia verificable (AC-10, AC-19)

**Qué exige.** Casos de concurrencia, redirecciones, reintentos, límite, fuente apagada,
cancelación, `Retry-After` y despliegue no coordinado; PASS/FAIL/NOT RUN separados; los NOT
RUN solo Pi/red real. AC-19 añade coste y determinismo: sin I/O añadida, estado acotado,
suite que no duerme de verdad, mismos datos ⇒ mismos reintentos/esperas.

**Pruebas que lo sostienen hoy en `main`.**

- Esta matriz es el informe de AC-10. El recuento de la suite relevante es **707 tests, 0
  fallos** (§0.2).
- Concurrencia: `tests/test_cortesia.py:227`, `tests/test_tebeosfera_cortesia.py:118`.
- Redirecciones: `tests/test_peticiones.py::TestRedirecciones`; reintentos:
  `tests/test_peticiones.py::TestReintentos`; límite:
  `tests/test_cortesia.py::TestDosNiveles`; apagada:
  `tests/test_peticiones.py::TestFuenteApagada` y `tests/test_clientes_fuente_apagada.py`;
  cancelación: `tests/test_cortesia.py::TestCancelacionYPresupuesto`; `Retry-After`:
  `tests/test_peticiones.py::TestRetryAfter`; despliegue no coordinado:
  `tests/test_cortesia.py:241`.
- Estado acotado: `tests/test_cortesia.py::TestSnapshot::test_el_estado_esta_acotado`
  (L339), 6 fuentes y máximo 3 intentos.
- Determinismo: todas las pruebas de la lista usan reloj/`dormir` simulados y
  `httpx.MockTransport`; no duermen de verdad.

**Código.** `utils/cortesia.py:515-575` no toca BD, disco ni red; `peticiones.py` no añade
peticiones.

**Estado.** PASS global (esta matriz + suite). No hay una celda por consumidor: el criterio
es el informe mismo. **Reserva de AC-19:** «sin I/O añadida» se sostiene por inspección
(el snapshot solo lee dicts), no por un test que prohíba abrir un fichero; «estado acotado»
y «determinismo» sí tienen prueba. Ningún NOT RUN se cuenta como PASS.

---

## 2. Resumen de FAIL y de evidencias frágiles

### 2.1 Los 7 FAIL de la matriz

| Celda | Tipo | Qué falta | Qué haría falta para cerrarlo |
|---|---|---|---|
| GCD · criterio 2 | E | Ninguna prueba de escalonado ni de que GCD use su política (2,0 s) y el nivel host. | Un `test_gcd_cortesia.py` con dos búsquedas de GCD y una de otra fuente al mismo host; y comprobar que `GCDClient` construye `politica_de("gcd")`. |
| GCD · criterio 3 | E | Ninguna prueba de redirección ni de `follow_redirects=False` en `GCDClient`. | Un 302 a mano con `GCDClient`, un `Location` de otro origen y la comprobación del `AsyncClient` abierto. |
| GCD · criterio 4 | E | Solo está probada la fuente apagada; sin 429, `Retry-After` ni máximo de 2 intentos. | Un 500/429 con `GCDClient` contando peticiones y esperas, y un `Retry-After` que bloquee el host. |
| Foro · criterio 2 | E | Todos los tests del foro usan `rate_limit=0` (`tests/test_forum_scraper.py:68`); no se mide el escalonado de 2,0 s. | Un test del foro con `rate_limit=2.0` y dos `_get` seguidos. |
| Foro · criterio 4 | E | Solo está probada la fuente apagada; sin 429 ni reintento máximo 2. | Un 500/429 con `ForumScraper` contando peticiones y esperas. |
| Foro · criterio 5 | **I** | `use_ipb_search` convierte `CortesiaEnEspera` en `[]` y lo registra como fallo; `_forum_fallback` vuelve a tragarlo. | Capturar `CortesiaEnEspera`/`FuenteApagada` antes del `except Exception` y dejar que suban (o devolver un resultado de omisión explícito), con test de que la espera no se convierte en «sin resultados». |
| Portadas · criterio 8 | **I** | El host de una portada sale con `intervalo_min_s: 0.0` y `fuentes: []`; la fila `portada` usa el 2,5 desconocido. | Que `snapshot()` use `intervalo_de_portada(host)` para hosts sin fuente o declare la portada por host; test del snapshot con un host solo-portada. |

### 2.2 Evidencias frágiles que **no** son FAIL de la matriz

- **AniList/GCD/Tebeosfera · criterio 5:** PASS (C) porque el aviso de Descubrir se prueba
  con un doble y el mapeo es común; no hay prueba de que la `CortesiaEnEspera` salga del
  cliente real. Si se quiere endurecer, un test por cliente con el limitador bloqueado y el
  presupuesto agotado.
- **CV/AniList/GCD/foro/portadas · criterio 7:** PASS (C) por el limitador común; no hay
  prueba de cancelación con esos consumidores. Tebeosfera sí la tiene (D).
- **Criterio 6:** PASS (C) es una declaración global; no hay una aserción por consumidor.
- **Criterio 8 (fuentes):** PASS (C) por el snapshot común; no hay una aserción por fuente
  de que su intervalo mostrado sea el suyo (la tabla de políticas sí lo fija).

---

## 3. NOT RUN (no medido, no convertido en PASS)

Nada de esto se ha ejecutado; no se suma a ningún PASS de §1. Se declara para que no se
confunda «suite verde» con «validado en producción».

1. **Red real contra Comic Vine, AniList, GCD, Tebeosfera, foro y CDNs de portadas.**
   La suite usa `httpx.MockTransport` o transporte inyectado; no se ha hecho **ninguna**
   petición externa. No medido: latencia real, DNS/TLS, comportamiento real de los CDN,
   redirecciones reales (Tebeosfera 302, CDN), 429 y `Retry-After` reales, contenido real.
2. **Raspberry Pi 4/5.** No se ha medido CPU, RAM (presupuesto 512 MB), latencia del bucle,
   coste de `asyncio.to_thread` en el resize de portadas, ni el semáforo de descargas bajo
   una rejilla de 200 series. La afirmación de «una comparación de reloj y un contador por
   petición» es de diseño/inspección, no una medición en Pi.
3. **Multi-proceso / réplicas (`uvicorn --workers N`, N > 1).** No soportado por diseño: el
   estado es memoria del proceso. No se ha desplegado ni medido. La prueba
   `tests/test_cortesia.py:241` demuestra que dos registros independientes **no** se
   coordinan; es evidencia del límite, no de soporte multi-proceso. Tampoco se ha probado
   la detección de multi-worker porque no existe (§6.7/§14.1 de la spec).
4. **Despliegue real.** `Dockerfile:56-60` declara `uvicorn --workers 1`, pero no se ha
   arrancado el contenedor ni un `uvicorn` real. `/api/estado/cortesia` y `/estado` se han
   probado con `TestClient`, no contra un servidor vivo.
5. **Navegador real.** El HTML de Estado/Ajustes/Descubrir se comprueba en el servidor; no
   se ha abierto un navegador ni se ha medido el comportamiento de HTMX o del usuario.
6. **Soak / ejecución larga.** El estado está acotado (6 fuentes, 3 intentos) y hay test de
   ello, pero no se ha medido el crecimiento en memoria tras horas de enricher/orchestrator.
7. **Postgres real en `/estado`.** La página usa una sesión para el bloque de
   disponibilidad; la suite de cortesía usa `FakeSession`. La cortesía no toca BD, pero la
   página completa con Postgres real no se ha ejecutado aquí.
8. **Foro real (IPB), login real y cookies reales.** Todo simulado; el flujo 302 +
   `Set-Cookie` está probado con transporte falso, no contra un foro real.
9. **Otras instalaciones, scripts/cron, clientes LAN (Prowlarr/Transmission/aMule) y
   webhooks.** Quedan fuera de la coordinación por diseño; no se han medido ni se presentan
   como coordinados.
10. **Fallos de red reales** (timeout, pérdida de paquetes, proxy, DNS intermitente): solo
    se simulan excepciones de `httpx`.
11. **Coste de la Pi con la UI interactiva** (Descubrir con presupuesto 10 s, Ajustes con
    prueba manual): no medido; la suite solo comprueba que no se duerme de verdad.

---

## 4. Límites: qué garantiza y qué no

### 4.1 Lo que sí garantiza (con la suite y el código actual)

- **Un solo proceso.** El limitador es estado en memoria de **un** proceso
  (`utils/cortesia.py:400-468`, `588-593`); el despliegue soportado es `uvicorn --workers 1`
  (`Dockerfile:56-60`, `docs/design/cortesia-compartida.md:7-31`). Dentro de ese proceso,
  todas las peticiones de CV, AniList, Tebeosfera, GCD, foro (incluido `login`) y portadas
  pasan por las colas; dos clientes distintos de la misma fuente comparten cola.
- **Dos niveles** por fuente y por host efectivo `(esquema, host, puerto)`, con el máximo de
  intervalos en el host; `http` y `https` son destinos distintos. Portadas: **solo host**,
  por la excepción declarada.
- **Cada petición, cada salto y cada reintento** pasan por la cola y cuentan en el
  presupuesto del llamador. Redirecciones a mano, tope 3, solo mismo origen (o allowlist
  explícita), 301/302/303 → GET sin cuerpo, 307/308 conservan método y cuerpo.
- **Reintentos acotados** solo de transitorios, backoff 2, 4, 8… con tope 30 y sin jitter;
  `Retry-After` compartido como bloqueo de fuente y host, recortado a 1 h; un bloqueo que no
  cabe en el presupuesto no duerme la tarea.
- **Fuente apagada sin tráfico**: se comprueba antes de reservar, antes de cada intento y
  antes de cada salto; una fuente apagada durante la espera no envía.
- **Espera visible sin promesas**: `CortesiaEnEspera` con fuente, host, estimación y motivo;
  Descubrir la presenta como `limite_de_cortesia`; Ajustes como aviso neutro; Estado con
  «En espera»/«Bloqueada temporalmente»; portada → 404/marcador sin cachear la ausencia.
- **Snapshot sin secretos**: fuentes, intervalos, intentos, cola, siguiente hueco,
  reintentos y bloqueo; solo lectura y `no-store`; sin URL, query, claves ni credenciales.
- **Sin dependencias nuevas, sin Redis/PostgreSQL/estado compartido, sin escritura en
  disco/BD** para el estado de cortesía (`pyproject.toml` y `alembic/` sin cambios en el
  diff de #134; `git diff 3562f3a..HEAD -- pyproject.toml alembic/` vacío).
- **Asíncrono**: el limitador vive en el bucle; `asyncio.to_thread` solo se usa para trabajo
  local (resize/escritura de portada); llamarlo desde un hilo falla explícito
  (`tests/test_cortesia.py:304`).

### 4.2 Lo que **no** garantiza

- **Coordinación entre procesos, réplicas o instalaciones.** Con N procesos, cada uno
  respeta su intervalo: la fuente puede recibir hasta N veces más peticiones. No hay
  detección de multi-worker ni se finge que la haya. Si algún día se soporta, hará falta un
  ADR y cambiar el snapshot y la documentación a la vez.
- **Coordinación con scripts/cron, clientes LAN (Prowlarr, Transmission, aMule) ni
  webhooks.** No son fuentes externas de este limitador.
- **Disponibilidad o recuperación de una fuente.** El bloqueo compartido no promete que la
  fuente vuelva; solo evita pedirle durante el tiempo indicado. No hay reintento en caliente
  de un 429 que supere el presupuesto.
- **Prioridades, jitter, histórico de métricas, fairness global.** FIFO sin prioridades;
  backoff sin jitter; el snapshot guarda como máximo 3 intentos por fuente.
- **Persistencia.** Si el proceso se reinicia, colas y bloqueos se pierden; lo peor es una
  petición más espaciada, nunca una ráfaga.
- **Garantía en la Pi real ni en red real.** Nada de §3; el PASS de §1 es de suite simulada.
- **Portadas por fuente.** Su URL no lleva la fuente; el nivel host sale del mapa
  allowlist→fuente y un host desconocido espera 2,5 s. El snapshot no declara bien el
  intervalo de un host solo-portada (FAIL I de §1.8).

---

## 5. Conclusiones

1. **Plenamente acreditados con la suite (sin celdas FAIL):** criterio **1** (ámbito),
   criterio **6** (coordinación declarada), criterio **7** (FIFO/cancelación, con Tebeosfera
   directa y el resto por la cola común) y criterio **9** (global; sus celdas por consumidor
   son n/a, esta matriz + 707 tests). El criterio **8** está acreditado para las seis fuentes
   y falla solo en el detalle de host de portadas.
2. **Acreditados con la suite salvo un consumidor:** criterio **3** (todo menos GCD) y
   criterio **4** (todo menos GCD y foro). El mecanismo común está probado; lo que falta es
   la prueba de que esos clientes lo usan en el escenario concreto (redirección, 429,
   reintento).
3. **Parciales:** criterio **2** (CV, AniList y Tebeosfera; GCD y foro sin prueba de
   escalonado; portadas solo host por diseño) y criterio **5** (CV y portadas directos;
   AniList/GCD/Tebeosfera por el mapeo común con doble; foro con un fallo de implementación:
   la espera se convierte en «sin resultados» y se registra como error).
4. **Dependen de entorno real (NOT RUN):** latencia/CPU/RAM en Pi, red real de las cinco
   fuentes y CDNs, 429/`Retry-After` reales, despliegue `uvicorn --workers 1` real,
   navegador real, soak y Postgres real en `/estado`. Ninguno se cuenta como PASS.
5. **Hallazgos que no se corrigen en este PR (es documental):**
   - **Foro, criterio 5 (FAIL I):** `use_ipb_search` debe dejar pasar
     `CortesiaEnEspera`/`FuenteApagada` (o devolver una omisión explícita) antes del
     `except Exception`; `_forum_fallback` debe distinguir la omisión del fallo.
   - **Portadas, criterio 8 (FAIL I):** el snapshot debe declarar el intervalo del host de
     portada (hoy 0,0 s y `fuentes: []`), o la fila `portada` debe reflejar el intervalo por
     host.
   - **Evidencias frágiles:** añadir tests de GCD (cola, host, redirects, 429/reintento),
     de foro (escalonado 2,0 s, 429/reintento), de Tebeosfera (propagación de
     `CortesiaEnEspera`, un solo intento contado) y de AniList (espera visible con el
     cliente real). Con ellos, los FAIL (E) pasarían a PASS (D) y las celdas C de criterio 5
     quedarían cerradas.
6. **Lo que no cambia:** Tebeosfera conserva 2,5 s, ≤3 saltos, mismo origen y 1 intento
   (AC-11); las portadas conservan allowlist/SSRF/tiempo/tamaño (AC-12); no hay dependencias
   nuevas, ni Redis/PostgreSQL, ni escritura en disco/BD (AC-17).

---

## 6. Anexo: AC-11 a AC-19 (transversales)

| AC | Qué exige | Prueba / evidencia | Estado |
|---|---|---|---|
| **AC-11** | Tebeosfera intacta: 2,5 s, ≤3 saltos, mismo origen, 1 intento, elevación de config con aviso. | `tests/test_tebeosfera_cortesia.py` completo (L103-403). | PASS |
| **AC-12** | Portadas: cada salto por la cola del host, sin reintento; allowlist/SSRF/tiempo/tamaño; espera >5 s → 404/marcador sin cachear. | `tests/test_cover_cortesia.py` (L91-218) y `tests/test_cover_ssrf.py` (L200-383, L547/L566). | PASS (salvo el detalle de host de §1.8) |
| **AC-13** | `asyncio.to_thread`: espera y petición en el bucle; resize en hilo; limitador desde un hilo falla. | `tests/test_cover_cortesia.py:191`, `tests/test_cortesia.py:304`. | PASS |
| **AC-14** | Descubrir distingue `espera` de `error`; aviso §6.5; no «Ningún resultado» por la fuente en espera. | `tests/test_discovery_estados.py:277`/`:288`; `tests/test_descubrir_estados_web.py:415`/`:422`. | PASS |
| **AC-15** | Fuente apagada sin reserva/envío/reintento en enricher, Descubrir, foro, portada; prueba de Ajustes es la excepción. | `tests/test_peticiones.py:355-415`; `tests/test_clientes_fuente_apagada.py:42-84`; `tests/test_cover_cortesia.py:135-180`; `tests/test_enricher.py:613`/`:828`. | PASS (foro: el caso «apagada durante la espera» puede acabar en `[]` por el mismo `except` de §1.5) |
| **AC-16** | Espera ≠ fallo: no `error`, no log de fallo, no degradar; `espera` en UI u omisión en fondo. | `tests/test_enricher.py:613`; `tests/test_discovery_estados.py:277`; `tests/test_cover_cortesia.py:182`. | PASS en CV/AniList/GCD/Tebeosfera/portadas; **FAIL (I) en foro** (§1.5) |
| **AC-17** | Sin dependencias nuevas, migración, Redis/PostgreSQL; estado en memoria; snapshot sin escritura. | `git diff 3562f3a..HEAD -- pyproject.toml alembic/` vacío; `utils/cortesia.py:515-575`; `pyproject.toml:6-21`. | PASS (inspección) |
| **AC-18** | Estados: apagada gris no es fallo; bloqueada «Bloqueada temporalmente (~Ns)»; foro sin URL «Sin configurar»; disponible «Disponible». | `tests/test_cortesia_estado.py:113`/`:126`/`:135`; `tests/test_web_estado_cortesia.py:97`. | PASS |
| **AC-19** | Coste/determinismo: sin I/O añadida; estado acotado; la suite no duerme; mismos datos ⇒ mismas esperas. | `tests/test_cortesia.py:339`; reloj/`dormir` simulados en toda la suite. «Sin I/O» es inspección, no test. | PASS (con reserva en «sin I/O») |

---

## 7. Registro de cambios

| Fecha | Versión | Cambio |
|---|---|---|
| 2026-11-05 | v1.0 | Primera matriz de verificación de los 9 criterios de #134 sobre `4ec55cb`: 707 pruebas relevantes, 40 PASS, 7 FAIL, 7 n/a; NOT RUN de red real/Pi/multi-proceso separados. Hallazgos: espera del foro convertida en «sin resultados» y host de portada con intervalo 0,0 s en el snapshot. |
