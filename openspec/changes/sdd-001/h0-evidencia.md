# H0 — Evidencia exploratoria

- Baseline de producto: `ea9bc603eb2aa86265abd5b0697b3e03ef87e732`.
- Propuesta revisada inicialmente: `f3170771aebd3c001315420fdbf2a84ea46cf881`; actualización documental `49ebbb60`.
- Estado: **en curso**. Esta evidencia no activa reglas ni aprueba el pin.
- Decisión del mantenedor: la verificación efectiva de carga de instrucciones en harnesses queda como deuda T0.4 para permitir avanzar a H1; deberá completarse antes de activar gates obligatorios. No equivale a PASS ni autoriza fusión o despliegue.

## Inventario y discrepancias

- En la baseline existen dos ADR numerados `0020` y dos `0021`. Registrar ambos por nombre completo; no renumerar automáticamente ni alterar enlaces históricos.
- La CI genera `suite.xml` y `pg.xml` en jobs separados; verificar su publicación, procedencia y agregación antes de exigir trazabilidad entre jobs. Existen `scripts/ci_postgres.py` y `scripts/ci_rar_real.py`; evaluar reutilización antes de escribir validadores nuevos.
- El pipeline `.agentic/` observado en el checkout local no está en la baseline `main`; no tratarlo como herramienta integrada ni modificarlo.

### Inventario cuantitativo y límites

Sobre `git ls-tree -r --name-only ea9bc603`, contando archivos del nivel directo y no funcionalidades: 2.067 rutas rastreadas, 27 archivos ADR, 132 módulos Python en `services`, 10 en `api`, 45 en `web`, 552 archivos `tests/test_*.py` y 52 archivos de migración. Estas cifras no son números de endpoints, pruebas ejecutadas ni capacidades verificadas. El menú se documenta en `src/zascarr/web/menu.py`; el montaje de routers y bucles, en `src/zascarr/main.py`; las capacidades declaradas, en `README.md`.

La CI de `main` define suite, Postgres real, lint y builds, además de un workflow de contratos UXLab condicionado por rutas. Son definiciones, no evidencia de una ejecución concreta ni de protección de rama. El benchmark histórico `docs/design/ficha-propuestas-desde-carpetas.md` menciona Redis, mientras `docs/adr/0011-retirar-redis.md` registra su retirada; `docs/adr/0004-exposicion-de-red.md` también conserva una referencia a Redis. No se reescriben documentos históricos ni se infiere que sigan vigentes sus descripciones de infraestructura.

## Prueba aislada de OpenSpec

En un directorio de pruebas separado, con Node `v24.22.3`, npm `11.19.1` y OpenSpec publicado `2.2.0`, instalado con `npm --ignore-scripts`:

| Comprobación | Resultado |
|---|---|
| `init --tools none` | PASS |
| `validate sdd-001 --type change --strict --no-interactive` para la propuesta | PASS; comprueba estructura, no semántica |
| Delta sintético sin escenario | FAIL esperado: detecta escenario ausente |
| Delta sintético con escenario | PASS |
| `archive prueba-sintetica --yes` | PASS: consolida y archiva; no equivale a autorización de merge |
| Validación estricta de spec recién archivada | FAIL: `Purpose` queda como marcador pendiente |
| Tras sustituir manualmente el marcador `Purpose` en la spec sintética | PASS de `validate saludo --type spec --strict --no-interactive` |

Conclusión: el ciclo requiere completar y revisar `Purpose` antes de afirmar que la spec consolidada valida; no es una consolidación sin intervención. Se usaron `DO_NOT_TRACK=1` y `OPENSPEC_TELEMETRY=0` y directorios de configuración aislados. Hubo acceso al registro npm; no se verificó la ausencia de otras conexiones. Desactivar scripts de instalación no evita ejecutar después la CLI y sus dependencias. No se han verificado aún obligaciones de licencias transitivas, reproducibilidad completa ni compatibilidad efectiva de harnesses.

En el código instalado de OpenSpec 2.2.0, `DO_NOT_TRACK=1`, `OPENSPEC_TELEMETRY=0` y `CI=true` desactivan cada uno la telemetría y la comprobación automática de versiones; una consulta explícita de versión tiene reglas propias. En una ejecución adicional de `validate --all --json` con `DO_NOT_TRACK=1`, interceptando en memoria `fetch`, `http(s)` y `net.Socket.connect`, no se observaron intentos en esas superficies y se validaron dos elementos. Una prueba posterior en proyecto sintético instrumentó además conexiones TLS, DNS y UDP: `init`, `validate` y `archive` terminaron con código 0 y sin intentos observados en esas superficies; la validación posterior de la spec archivada falló de nuevo por el `Purpose` pendiente. La instrumentación en memoria no es aislamiento de red del sistema operativo y no cubre módulos nativos, subprocesos ni superficies omitidas; no demuestra ausencia universal de tráfico.

La reinstalación desde el lock local con `npm ci --offline --ignore-scripts --no-audit --no-fund` terminó con código 0 y 66 paquetes, usando una caché previamente poblada. El SHA-256 del lock antes y después fue `ebcc1e4ff2c56aa22ff1952f380a052b13f9491b6937db2d69b82cf7d6905fd0`. Esto solo acredita esa instalación en Node 24.22.3/npm 11.19.1 con esa caché y ese lock. El primer intento falló por configuración npm de usuario/global duplicada; se corrigió antes de repetir.

Posteriormente, en Linux x86_64 con las mismas versiones, se creó un manifiesto con `@fission-ai/openspec: "2.2.0"`, se generó un lock v3 y se ejecutó `npm ci --ignore-scripts --no-audit --no-fund` con una **caché inicialmente vacía**, consultando el registro npm. Se instalaron 66 paquetes y la CLI respondió `2.2.0`. Los 66 paquetes del lock incluían integridad; SHA-256 del lock: `ae3e192f26314718c7041d376beb7c8cf5153c121e49b0ba07fff51d1f0c031e`. No hubo captura de tráfico y no se probaron otras plataformas; el lock es experimental, no está aprobado ni versionado para el proyecto.

Como candidato, no como pin aprobado, se propone OpenSpec `2.2.0` exacto en un directorio de tooling separado del runtime: manifiesto privado con versión sin rango, lock revisado y versionado, Node/npm fijados, `npm ci --ignore-scripts` y ejecución del binario local, sin `npx` descargador. Repetir en un entorno limpio y plataformas requeridas antes de dar reproducibilidad por demostrada. El lock experimental ya contiene versión e integridad, pero no está versionado y su manifiesto usa `^2.2.0`. Mantenerlo separado de UXLab evita acoplar esta herramienta a Playwright; un wrapper Python no elimina su dependencia de Node. La receta no sustituye revisar licencias, suministro y condiciones de ejecución.

## Autoverificación del propio cambio

La propuesta R004 exige ID estable y evidencia para cada escenario nuevo o modificado. Tras detectar que faltaban IDs explícitos, se asignaron identificadores `SDD-Rnnn-Snn` a los 12 escenarios de este delta y se registraron en el manifiesto. Las comprobaciones siguen planificadas: los IDs no acreditan ejecución ni adecuación. La validación estructural de OpenSpec no detecta esa deuda; no afirmar cumplimiento de R004 por el PASS de la CLI.

## Licencias declaradas: inventario, no dictamen

OpenSpec 2.2.0 declara MIT. El inventario de las 66 instalaciones en el lock local coincide con los paquetes instalados: 54 declaraciones MIT (incluido OpenSpec), 7 ISC, 4 BlueOak-1.0.0 y 1 BSD-3-Clause; sin licencias desconocidas en esos metadatos y con archivos de licencia presentes. Esto no audita código incorporado ni obligaciones de redistribución. El `package.json` del entorno de prueba usa `^2.2.0`: sin el lock no constituye un pin reproducible. No se ha aprobado una dependencia para el proyecto.

Una revisión acotada de nombres de archivos y manifiestos encontró en `skills` un `ThirdPartyNoticeText.txt` y un fichero comprimido `THIRD-PARTY-LICENSES.md.gz`. Este último declara código incorporado bajo Apache-2.0, ISC y MIT, incluido `@vercel/detect-agent` bajo Apache-2.0; por tanto, los metadatos de los 66 paquetes no describen por completo las licencias del código empaquetado. La licencia declarada por el paquete principal no resume por sí sola todos los avisos. Los 66 paquetes tienen un archivo de licencia no vacío en su raíz; no se ha cotejado íntegramente cada texto ni certificado la exhaustividad de los avisos.

A nivel general, [MIT](https://opensource.org/license/mit) e [ISC](https://www.isc.org/licenses/) exigen conservar avisos en las copias; [BSD-3-Clause](https://opensource.org/license/bsd-3-clause) añade condiciones para redistribuciones binarias y no respaldo; [BlueOak-1.0.0](https://blueoakcouncil.org/license/1.0.0) exige entregar el texto o enlace de la licencia a quien reciba una copia de cualquier parte. Usar una herramienta aislada no es por sí solo redistribuirla. Antes de distribuir paquetes, plantillas o fragmentos incorporados, hay que identificar el contenido realmente entregado, revisar avisos y obligaciones, y distinguir agregado de obra combinada. No se afirma compatibilidad legal definitiva ni se sustituye asesoría jurídica.

## Generación de adaptadores en OpenSpec 2.2.0

En un proyecto sintético nuevo, `openspec init --tools claude,codex,opencode,agents --scope project` terminó con código 0 y generó siete skills en `.claude/skills/` y siete en `.agents/skills/`, además de la estructura `openspec/`; no generó carpetas `.codex` ni `.opencode` en esta configuración. El entorno y directorios de usuario fueron aislados y se desactivó telemetría; un preload Node rechazó conexiones y DNS, pero no es una frontera de red del sistema operativo. El primer intento con permisos de escritura insuficientes falló; la ejecución descrita usó un directorio nuevo. Esto verifica generación, **no** que los harnesses carguen los archivos.

## Harnesses disponibles: verificación local sin inferencia

Con entorno mínimo, entrada cerrada y sin credenciales proporcionadas: `claude --version` devuelve `2.1.332` y `codex --version` devuelve `0.170.0`; sus ayudas responden correctamente. `opencode --version` y `--help` fallan con código 46: Snap no puede crear el ámbito transitorio DBus en este entorno. Son pruebas de disponibilidad y ayuda, **no** pruebas de carga real de instrucciones, funcionamiento autenticado o equivalencia entre harnesses. La versión anterior indicada para Claude en el pipeline local no versionado no corresponde al ejecutable observado en esta comprobación.

Tras la autorización explícita para utilizar exclusivamente suscripciones, se comprobó el modo declarado por las herramientas: Claude informa `claude.ai`/Pro y Codex informa ChatGPT. No se ejecutó inferencia: estas declaraciones no demuestran por sí solas la ruta efectiva bajo toda la configuración ni el aislamiento de herramientas y políticas. Se intentó una única prueba sintética con `codex exec`, configuración de usuario omitida y autenticación ChatGPT declarada; terminó con código 1 por `Read-only file system (os error 30)` antes de iniciar el cliente; DSH informó denegación de acceso del sandbox y no se identificó la ruta concreta. No se reintentó ni se eludió esa política. No se enviaron datos a proveedores ni se verificó la lectura de `AGENTS.md`. El sandbox read-only restringe escritura, no garantiza aislamiento de lectura. Queda pendiente una prueba de carga efectiva con garantías suficientes de que no se usan APIs.
