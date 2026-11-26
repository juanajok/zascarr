# H0 — Evidencia exploratoria

- Baseline de producto: `ea9bc603eb2aa86265abd5b0697b3e03ef87e732`.
- Propuesta revisada inicialmente: `f3170771aebd3c001315420fdbf2a84ea46cf881`; actualización documental `49ebbb60`.
- Estado: **en curso**. Esta evidencia no activa reglas ni aprueba el pin.

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

La reinstalación desde el lock local con `npm ci --offline --ignore-scripts --no-audit --no-fund` terminó con código 0 y 66 paquetes, usando una caché previamente poblada. El SHA-256 del lock antes y después fue `ebcc1e4ff2c56aa22ff1952f380a052b13f9491b6937db2d69b82cf7d6905fd0`. Esto solo acredita esta instalación en Node 24.22.3/npm 11.19.1 con esa caché y ese lock, no una instalación con caché vacía ni en otras plataformas. El primer intento falló por configuración npm de usuario/global duplicada; se corrigió antes de repetir.

## Licencias declaradas: inventario, no dictamen

OpenSpec 2.2.0 declara MIT. El inventario de las 66 instalaciones en el lock local coincide con los paquetes instalados: 54 declaraciones MIT (incluido OpenSpec), 7 ISC, 4 BlueOak-1.0.0 y 1 BSD-3-Clause; sin licencias desconocidas en esos metadatos y con archivos de licencia presentes. Esto no audita código incorporado ni obligaciones de redistribución. El `package.json` del entorno de prueba usa `^2.2.0`: sin el lock no constituye un pin reproducible. No se ha aprobado una dependencia para el proyecto.

## Harnesses disponibles: verificación local sin inferencia

Con entorno mínimo, entrada cerrada y sin credenciales proporcionadas: `claude --version` devuelve `2.1.332` y `codex --version` devuelve `0.170.0`; sus ayudas responden correctamente. `opencode --version` y `--help` fallan con código 46: Snap no puede crear el ámbito transitorio DBus en este entorno. Son pruebas de disponibilidad y ayuda, **no** pruebas de carga real de instrucciones, funcionamiento autenticado o equivalencia entre harnesses. La versión anterior indicada para Claude en el pipeline local no versionado no corresponde al ejecutable observado en esta comprobación.
