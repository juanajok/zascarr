# #295 — Asistente de carpetas: ausencia de sugerencia y procedencia (2026-10-29)

> **Estado: PASS de los criterios de #295 que se han podido ejecutar.** La variante «sin
> sugerencia» se comprueba en el asistente de carpetas con Chrome real, BD y biblioteca
> sintéticas y fuentes controladas. La evidencia de Descubrir del 2026-10-22 se reutiliza:
> el contrato, la copy de `pista_de_tradicion` y la presentación no cambian en `2cd42f8`.
> **No se convierten en PASS** los NOT RUN de AniList/Comic Vine ni se acredita el
> comportamiento de GCD/Tebeosfera reales en el asistente: ver §5.

## 1. Alcance

Issue [#295](https://github.com/juanajok/zascarr/issues/295), deuda de verificación de U15
(#202/#276). No se implementa producto ni se cambia código: esta nota y sus capturas son
evidencia. No se toca la Pi, la biblioteca real ni el catálogo real. El asistente se detiene
en la **revisión**; no se pulsa «Crear serie vacía» ni se vincula nada.

## 2. Código de referencia y vigencia de la evidencia del 2026-10-22

| Elemento | Valor |
|---|---|
| `origin/main` verificado | `2cd42f85f7674fa839cecc01d644d4e837292ceb` (`2cd42f8`) |
| Evidencia previa de Descubrir | `docs/design/ui-u15/verificacion-navegador-2026-10-22.md` (SHA `bf67699`) |
| Contrato | `docs/design/ui-u15/u15b-ausencia-procedencia.md` |
| Fecha de esta comprobación | 2026-10-29 |

Comprobaciones de vigencia sobre el diff `bf67699..2cd42f8`:

- `src/zascarr/web/descubrir_texto.py`: solo se movió `texto_plano` a
  `zascarr.utils.texto_html`; **`pista_de_tradicion` es idéntica** y conserva las cuatro
  procedencias y la ausencia sin texto.
- `src/zascarr/web/templates/carpetas.html` y `_politica_serie.html` tienen cambios de
  #311/#296 (descripción/portada y accesibilidad de la política), **no de la copy de U15**.
- El contrato de `u15b-ausencia-procedencia.md` sigue siendo el mismo: `tradition_guess`
  opcional, procedencia de cuatro valores, sin preselección y sin inventar texto cuando no
  hay sugerencia.
- Por tanto, la evidencia de Descubrir del 2026-10-22 **sigue siendo válida como PASS de
  presentación** en `2cd42f8`; no se ha reejecutado una búsqueda real nueva sobre este SHA.

## 3. Entorno y método de la comprobación nueva

| Elemento | Valor |
|---|---|
| Aplicación | `uvicorn zascarr.main:app`, local, `127.0.0.1:8770`; un worker |
| Código | worktree `zascarr-295`, `HEAD=2cd42f8`; `PYTHONPATH` al worktree |
| Base de datos | PostgreSQL 15, base desechable `zascarr_test_browser_295`; `alembic upgrade head` |
| Biblioteca | sintética, temporal, sin datos reales; **no** se toca la biblioteca del usuario |
| Fuentes | **controladas**: Tebeosfera con `por_defecto` y GCD con `tradition_guess=None`; sin red |
| Navegador | Google Chrome **156.0.8078.47**, headless, motor real |
| Automatización | Chrome DevTools Protocol con `websockets` ya disponible; **sin dependencias nuevas** |
| Viewports | 1280 × 900 y 360 × 800 |
| Autenticación | `AUTH_MODE=none`, solo `127.0.0.1` |
| Fecha | 2026-10-29 |

El montaje usa una app real y plantillas reales; solo se sustituye
`DiscoveryService.search_detallada` por dos candidatas deterministas. Es el mismo método que
la evidencia previa permite para «fabricar de forma controlada» un resultado sin sugerencia.
No se ha creado ninguna serie: la comprobación termina en la vista previa de revisión.

## 4. Resultado en el asistente de carpetas

Apertura sobre el grupo sintético `Comics/Flash (1987)`: **1 registro**, consulta propuesta
«Flash», sin consultar fuentes al abrir.

| Comprobación | Resultado | Detalle |
|---|---|---|
| Candidata GCD sin sugerencia | **PASS** | `tradition_guess=None`: **sin `<small>` ni texto de pista**; selector `required`, `value=""`, solo el marcador vacío `selected`. |
| Candidata Tebeosfera con sugerencia | **PASS** | Pista literal: «La fuente no indica tradición: se sugiere Tebeo español por defecto. Es solo una pista de la fuente, no de la obra: elige tú.»; selector `required`, vacío y sin preselección. |
| La elección manda | **PASS** | Sobre la candidata con pista se elige **Manga**; la revisión muestra «Tradición elegida: Manga» y «La fuente sugería Tebeo español (era solo una sugerencia)». |
| Procedencia en la revisión | **PASS** | «Procedencia de la sugerencia: valor por defecto: la fuente no lo indica. La tradición aplicada es la que elegiste.» |
| No escribe | **PASS** | «Elección anotada. Todavía no se ha creado ninguna serie…». `series`, `alta_operaciones`, `vinculacion_operaciones` y `asignacion_operaciones` siguen a **0**. |
| 360 px | **PASS** | `clientWidth = scrollWidth = 360`; sin scroll horizontal. |
| 1280 px | **PASS** | Sin scroll horizontal; tarjetas y revisión legibles. |

Capturas nuevas:

- [`capturas/2026-10-29-asistente-295-resultados-1280.png`](capturas/2026-10-29-asistente-295-resultados-1280.png)
  — GCD sin pista y Tebeosfera con pista, ambos selectores vacíos.
- [`capturas/2026-10-29-asistente-295-revision-1280.png`](capturas/2026-10-29-asistente-295-revision-1280.png)
  — elección Manga, procedencia como contexto y aviso de que no se ha creado nada.
- [`capturas/2026-10-29-asistente-295-resultados-360.png`](capturas/2026-10-29-asistente-295-resultados-360.png)
  — resultados a 360 px sin desbordamiento.

Capturas de Descubrir que se reutilizan (evidencia del 2026-10-22):

- [`capturas/2026-10-22-descubrir-mortadelo-1280.png`](capturas/2026-10-22-descubrir-mortadelo-1280.png)
- [`capturas/2026-10-22-descubrir-mortadelo-360.png`](capturas/2026-10-22-descubrir-mortadelo-360.png)
- [`capturas/2026-10-22-descubrir-mortadelo-gcd-sin-sugerencia-1280.png`](capturas/2026-10-22-descubrir-mortadelo-gcd-sin-sugerencia-1280.png)
- [`capturas/2026-10-22-descubrir-lucky-luke-gcd-sin-sugerencia-1280.png`](capturas/2026-10-22-descubrir-lucky-luke-gcd-sin-sugerencia-1280.png)
- [`capturas/2026-10-22-descubrir-revision-manga-1280.png`](capturas/2026-10-22-descubrir-revision-manga-1280.png)

## 5. PASS / FAIL / NOT RUN

| Criterio / escenario | Estado | Evidencia |
|---|---|---|
| Descubrir: GCD sin sugerencia, sin pista, selector vacío | **PASS** | Evidencia real del 2026-10-22 (`bf67699`), contrato/copy sin cambios en `2cd42f8` |
| Descubrir: copy con procedencia `por_defecto`/`transformada` y sin preselección | **PASS** | Evidencia real del 2026-10-22; 19 pistas, 0 preselecciones |
| Descubrir: elección explícita y vista previa sin escribir | **PASS** | Evidencia real del 2026-10-22; 0 series |
| Asistente: candidata sin sugerencia | **PASS** | Chrome real, fuentes controladas, §4 |
| Asistente: candidata con sugerencia `por_defecto` | **PASS** | Chrome real, fuentes controladas, §4 |
| Asistente: procedencia en la revisión y elección de la persona | **PASS** | Chrome real, §4; 0 series |
| Asistente: 360/1280 sin scroll horizontal | **PASS** | Chrome real, §4 |
| Tests automáticos de Descubrir y asistente | **PASS** | 787 passed, 0 skips, 0 fallos (BD PG desechable) |
| GCD/Tebeosfera **reales** en el asistente | **NOT RUN** | Se usaron fuentes controladas para hacer determinista la variante; no se acredita el comportamiento de las fuentes reales en esta pantalla |
| AniList / Comic Vine reales, copy `explicita` | **NOT RUN** | Sin clave / API no disponible; no se convierte en PASS. La copy está cubierta por tests automáticos y por la evidencia de Descubrir, pero no en vivo |

### Tests ejecutados

```bash
TEST_DATABASE_URL='postgresql://test:test@127.0.0.1:54331/zascarr_test_verify_295' \
PYTHONPATH=/tmp/opencode/zascarr-295/src \
  pytest -q -rs \
  tests/test_asistente_carpetas_pg.py \
  tests/test_descubrir_dos_pasos_pg.py \
  tests/test_descubrimiento_grupo_pg.py \
  tests/test_descubrir_estados_web.py \
  tests/test_tokens_revision.py \
  tests/test_core_carpetas.py \
  tests/test_tradiciones_de_la_carpeta.py \
  tests/test_revision_senales.py \
  tests/test_revision_carpetas_pg.py
```

Resultado: **787 passed, 0 skipped, 0 failed**.

## 6. Límites

- Chrome real **headless**: DOM y motor reales, sin una persona mirando ni lector de
  pantalla; no sustituye la validación con personas de U21.
- Las fuentes del asistente son controladas; no se prueba la disponibilidad, el orden ni
  los datos reales de GCD/Tebeosfera en esa pantalla. La evidencia real del 2026-10-22 sí
  cubre Descubrir con GCD/Tebeosfera reales.
- AniList y Comic Vine siguen **NOT RUN** por falta de fuente/clave. No se extrapola su
  comportamiento.
- No se toca la Pi ni se despliega nada. No se crea ninguna serie; la comprobación se para
  en la revisión.

## 7. Cierre de #295

Los dos huecos concretos de #295 —resultado sin sugerencia en navegador y procedencia en la
revisión del asistente— quedan cubiertos con PASS. Los NOT RUN de AniList/Comic Vine son
límites ya declarados de U15 y no se convierten en PASS. #295 puede cerrarse con esta
evidencia; el arreglo de producto, si apareciera un fallo, iría a una historia nueva.
