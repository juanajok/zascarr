# M4 — fase 1 del ensayo en Debian (2026-10-18): evidencia histórica

> **Evidencia histórica, no se reescribe.** Resultados de la fase 1 de M4 sobre el candidato
> `0a591d6f91a6b54f8cecb1e675afc59dc0290873` (merge de #225), en una máquina virtual Debian 12 aislada. **El candidato no quedó aceptado.**
> Las correcciones posteriores (#237, #238) y el seguimiento de fuentes (#239) **no son resultados de este ensayo**: se enlazan, no se mezclan.

- **Plan de referencia:** `docs/design/m4-plan-de-aceptacion-debian.md` (PR #226, merge `f2c45c4b276c07dfea0a7c2baf96cc712f84fdcb`). Decía
  «no se ha ejecutado nada» y era cierto en su fecha; **no se reescribe**.
- **Alcance ejecutado:** M4-01 y M4-02, más una inspección adicional del `.env` (ev. 17–18). **M4-03…M4-20: NOT RUN y sin autorización.**
- **No acredita** Raspberry Pi/ARM, rendimiento real ni esfuerzo humano (#122). Datos exclusivamente sintéticos (9 CBZ de 3 series).

## Resultados (fuente: `INFORME.md`; evidencia entre paréntesis)

| Caso / condición | Resultado | Evidencia |
|---|---|---|
| M4-01 instalación limpia, sin terminal | **FAIL** — RC=1: «DB_PASSWORD tiene el valor por defecto. Edita /opt/zascarr/.env…». El intento 2 solo completó tras **editar la contraseña a mano** y no convierte el intento 1 en PASS | 10–13, 17b |
| M4-02 salud y esquema | **Parcial** — PASS en aplicación, CSS, base de datos, esquema `0019`, límite de memoria efectivo (512 M), sin OOM ni reinicios, puertos solo en `127.0.0.1`; `degraded` por Transmission/aMule/VPN ausentes | 14–16 |
| Condición: fuentes externas desactivadas | **FAIL de la condición operativa del ensayo** — las cuatro figuraban `enabled` (el plan versionado no contiene esa cláusula; el código declara «activas por defecto»). **Consultas efectivas no acreditadas**: red cerrada y 0 intentos de salida/DNS en los logs de la aplicación | 14, 15 → #239 |
| Inspección del `.env` | **Hallazgo abierto** — `.env` en modo 644 (`root:root`) dentro de `/opt/zascarr`, que pertenece a `media:media`; **abren** `ensayo` (sin sudo), `nobody` y `media`. No se leyó el contenido | 18 → #237, #238 |

## Contenido y procedencia

| Parte | Qué es | Procedencia |
|---|---|---|
| `INFORME.md`, `informe-m4-fase1.html` | informe de la fase 1 (el HTML añade el anexo «Evidencias seleccionadas (saneadas)») | `adjuntos_originales_m4_fase1.zip` (SHA-256 `c3bdae53a25e572f1e8a2b3e47fc86b9279015673ab69f8ca38d670013829eed`); el MD es idéntico byte a byte a `evidencia-saneada/INFORME.md` |
| `evidencias/00…18` y `17b` (20 ficheros) | evidencia numerada | 19 del mismo ZIP, idénticos byte a byte a los de `evidencia-saneada/`; **`01-bundle.sha256` no iba en el ZIP** y se tomó de `evidencia-saneada/` (idéntico, por hash, a `evidencia/01-bundle.sha256`) |
| `MANIFIESTO-SHA256.csv` | tamaño y SHA-256 de cada fichero de esta carpeta | calculado al incorporarlo; los 21 hashes del manifiesto de recuperación del ZIP **coinciden** con los ficheros |

**Comprobaciones hechas al incorporarlo (2026-10-18):** el ZIP supera `unzip -t`; los 21 hashes de su manifiesto coinciden; `evidencia-saneada.tar.gz`
(SHA-256 `a14a95736a56f07f4c4a7a9995be039426c3a5227eabca49646aa9a8e4a2a3d1`) contiene lo mismo que la carpeta `evidencia-saneada/`;
el contenido de `01-bundle.sha256` (`10d107b1…f6642`) coincide con el SHA-256 que el informe cita para el bundle del candidato (§2) y con el hash recalculado de
`candidato.bundle`.

**Alcance de esa verificación:** acredita la **transferencia y la coherencia interna** del paquete. **No es una firma del autor ni acredita por
sí misma la procedencia histórica** de cada archivo.

## Lo que NO está en esta carpeta

Discos de la VM, imágenes Docker, el `candidato.bundle` (24 MB; solo consta su hash en `evidencias/01`), el `evidencia-saneada.tar.gz`, el `.env`, el ZIP de
recuperación y sus documentos nuevos (`README-RECUPERACION.md`, manifiesto de recuperación). El paquete **no incluye más que la numeración 00–18 y 17b** que
cita el informe; cualquier otra comprobación no adjunta sigue pendiente.

## Revisión de contenido antes de publicar

Lectura completa de los 20 ficheros de evidencia y de `INFORME.md`, y búsqueda de patrones sensibles (contraseñas, claves, tokens, correos, claves privadas,
MAC) en todo el paquete. Resultado:

- **Sin credenciales ni valores secretos.** Aparece el **nombre** `DB_PASSWORD`; el informe declara que la contraseña usada era sintética y «no se reproduce aquí».
- **Direcciones y nombres internos de la VM** (no sensibles): `10.0.2.x`, `172.17/18.x`, direcciones QEMU `fec0::`/`fe80::`, usuarios `ensayo`, `media`, `nobody`.
- **Una ruta del anfitrión** en el HTML (`/mnt/Datos/ensayo-m4/evidencia-saneada.tar.gz`). Se conserva tal cual: es histórica y no hay datos personales.
- Revisión por lectura, no por herramienta de detección de secretos. Quien publique la carpeta debe confirmarla.

## Reglas

Los resultados históricos no se reescriben; una aclaración posterior va como **nota o errata fechada y enlazada**, aparte.
