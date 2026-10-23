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
| Condición: fuentes externas desactivadas | **FAIL de la condición operativa del ensayo** — las cuatro figuraban `enabled` (el plan versionado trae una cláusula sobre fuentes, §3.3, sin precisar cuáles; el código declara «activas por defecto»; ver la nota fechada de abajo). **Consultas efectivas no acreditadas**: red cerrada y 0 intentos de salida/DNS en los logs de la aplicación | 14, 15 → #239 |
| Inspección del `.env` | **Hallazgo abierto** — `.env` en modo 644 (`root:root`) dentro de `/opt/zascarr`, que pertenece a `media:media`; **abren** `ensayo` (sin sudo), `nobody` y `media`. No se leyó el contenido | 18 → #237, #238 |

## Alcance del inventario

> Inventario recuperado **completo respecto de las evidencias numeradas 00–18 y 17b, más los dos informes**.

Eso **no** es «aceptación de M4 completa». Los resultados históricos siguen siendo: instalación limpia **FAIL**, M4-02 **parcial** y candidato **no
aceptado**; los casos posteriores (M4-03…M4-20) quedaron fuera de esta fase.

**Qué es original y qué es documentación nueva.** `INFORME.md`, `informe-m4-fase1.html` y los 20 ficheros de `evidencias/` son los **22 originales**
(2 informes + 20 evidencias, `01` y `17b` incluidas); `MANIFIESTO-SHA256.csv` los cubre **todos**. `README.md` y `MANIFIESTO-SHA256.csv` son
**documentación nueva** de esta incorporación, no evidencia del ensayo, y no figuran en el manifiesto.

## Contenido y procedencia

| Parte | Qué es | Procedencia |
|---|---|---|
| `INFORME.md`, `informe-m4-fase1.html` | informe de la fase 1 (el HTML añade el anexo «Evidencias seleccionadas (saneadas)») | `adjuntos_originales_m4_fase1.zip` (SHA-256 `c3bdae53a25e572f1e8a2b3e47fc86b9279015673ab69f8ca38d670013829eed`); el MD es idéntico byte a byte a `evidencia-saneada/INFORME.md` |
| `evidencias/00…18` y `17b` (20 ficheros) | evidencia numerada | 19 del mismo ZIP, idénticos byte a byte a los de `evidencia-saneada/`; **`01-bundle.sha256` no iba en el ZIP** y se tomó de `evidencia-saneada/` (idéntico, por hash, a `evidencia/01-bundle.sha256`) |
| `MANIFIESTO-SHA256.csv` | tamaño y SHA-256 de cada fichero de esta carpeta | calculado al incorporarlo; los 21 hashes del manifiesto de recuperación del ZIP **coinciden** con los ficheros |

**Comprobaciones hechas al incorporarlo (2026-10-18), tal como se ejecutaron:**

- Sobre el ZIP: `unzip -t` (sin errores) y comparación de los 21 SHA-256 de su manifiesto con los ficheros extraídos (21 de 21 coinciden).
- Sobre `evidencia-saneada.tar.gz` (SHA-256 `a14a95736a56f07f4c4a7a9995be039426c3a5227eabca49646aa9a8e4a2a3d1`): se extrajo en una carpeta temporal y se comparó
  con la carpeta `evidencia-saneada/` (`diff -rq`, sin diferencias). Los 19 ficheros comunes con el ZIP y el HTML se compararon con `cmp` (idénticos).
- `01-bundle.sha256`: se copió de `evidencia-saneada/`. Se calculó el SHA-256 de esa copia y el de la de `evidencia/` (la carpeta **sin sanear**) y
  coinciden (`dcc593b6…c0409a`); de `evidencia/` **solo se listaron nombres y se calculó ese hash: no se abrió ningún otro fichero**.
- `candidato.bundle`: **se leyó únicamente para calcular su SHA-256** (`sha256sum`); no se modificó, no se extrajo y no se incorporó al repositorio.
  El resultado (`10d107b1…f6642`) coincide con el contenido de `01-bundle.sha256` y con el SHA-256 que el informe cita en su §2.

**Alcance de esa verificación:** acredita la **transferencia y la coherencia interna** del paquete. **No es una firma del autor ni acredita por
sí misma la procedencia histórica** de cada archivo.

## Lo que NO está en esta carpeta

Discos de la VM, imágenes Docker, el `candidato.bundle` (24 MB; solo consta su hash en `evidencias/01`), el `evidencia-saneada.tar.gz`, el `.env`, el ZIP de
recuperación y sus documentos nuevos (`README-RECUPERACION.md`, manifiesto de recuperación). El paquete **no incluye más que la numeración 00–18 y 17b** que
cita el informe; cualquier otra comprobación no adjunta sigue pendiente.

## Revisión de contenido antes de publicar

Se hizo una **revisión manual**: lectura completa de los 20 ficheros de evidencia y de `INFORME.md` (el HTML equivale al informe más un anexo con extractos de
esas mismas evidencias), más una **búsqueda con `grep` de patrones** sensibles (contraseñas, claves, tokens, correos, claves privadas, direcciones MAC,
rutas de usuario) sobre el paquete y sobre las diferencias añadidas por cada commit de la rama. **No es un escaneo automatizado de secretos.**

- **Sin credenciales ni valores secretos.** Aparece el **nombre** `DB_PASSWORD`; el informe declara que la contraseña era sintética y «no se reproduce aquí».
- **Direcciones y nombres internos de la VM:** `10.0.2.x`, `172.17/18.x`, `127.0.0.1`, direcciones IPv6 de la red de usuario de QEMU (`fec0::`/`fe80::`,
  derivadas de la MAC por defecto de QEMU, no de una interfaz real), usuarios `ensayo`, `media`, `nobody` y la ruta `/home/ensayo/…` (de la VM).
- **Una ruta del anfitrión** en `informe-m4-fase1.html` (`/mnt/Datos/ensayo-m4/evidencia-saneada.tar.gz`). No contiene nombre de usuario ni de equipo. Se conserva
  **sin editar** para no alterar el original y mantener su trazabilidad.
- **Valoración:** no se ha encontrado en el paquete ningún dato que desaconseje publicarlo en este repositorio. Es una valoración de quien lo incorpora, **no
  una certificación**; la decisión final es de quien revise la PR.
- Si se decidiera retirar o redactar algo, la copia resultante dejaría de ser idéntica al original: habría que **recalcular su hash** y dejar nota de la
  redacción en este README.

## Notas de lectura (fechadas; no modifican los originales ni sus hashes)

**2026-10-18, a raíz de la revisión de #240.** Dos afirmaciones de `INFORME.md` §7 se leen con este alcance. Se dejan aquí, aparte, y el informe y la
evidencia 18 quedan **tal como están**:

1. **«Sin ACL»** se dedujo de la ausencia del indicador `+` en la salida de `ls -l` (ev. 18, sección «ACL»). **No se inspeccionó con `getfacl`**: no
   estaba instalado y no se instaló. Es una deducción razonable, no una comprobación directa.
2. **«El secreto no está incorporado a la imagen»** se apoya en que `/app/.env` es un enlace que no se resuelve dentro del contenedor y en que los
   contenedores no montan el `.env` (ev. 18). Acredita eso sobre **esa ruta**; **no se revisaron todas las capas de la imagen** ni otras rutas dentro de
   ella.

Ambas proceden del informe de la fase 1 y esta nota no las cambia: acota lo que cada una permite afirmar.

**2026-10-18, errata de este README (no del informe).** Una versión anterior de la tabla de resultados decía que «el plan versionado no contiene esa cláusula» sobre las fuentes. Es incorrecto: `docs/design/m4-plan-de-aceptacion-debian.md` §3.3 (fila «Red») dice «las fuentes de tebeos permanecen apagadas (valor por defecto) y no se consulta ninguna». El plan no define si «fuentes de tebeos» son las de descarga o las de metadatos, y su premisa «(valor por defecto)» es cierta para Prowlarr, Transmission, aMule y foro (`false`) y falsa para las cuatro fuentes de metadatos (`true`, `config.py`). El informe (§6) ya formulaba el resultado como FAIL de una **condición operativa** exigida para el ensayo, que es compatible con esta lectura.

## Reglas

Los resultados históricos no se reescriben; una aclaración posterior va como **nota o errata fechada y enlazada**, aparte.
