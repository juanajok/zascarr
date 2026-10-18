# M4 · Fase 1 bis — validar la instalación real y la protección de credenciales tras #238

> **Estado: PROPUESTA documental y scripts, sin ejecutar.** No se ha arrancado ninguna VM, descargado nada ni cambiado el tablero.
> Historia: **#121** (instalar y actualizar), feature **#107** (M4). **No cierra #121**: su contrato incluye actualización, fallos y
> evidencia en Raspberry Pi que un Debian x86-64 no acredita. Preparación y ejecución: Claude. Revisión independiente: Perplexity.
> La ejecución se aprobará sobre **este** guion acotado (§12), sin otra ronda de diseño.

## 1. Qué se quiere demostrar

> Como coleccionista, quiero completar una instalación nueva siguiendo el procedimiento publicado, sin pasos manuales ocultos, para
> abrir la interfaz y conservar mi biblioteca sin exponer las credenciales de la instalación.

Se repite porque la fase 1 dejó tres hechos que #238 dice haber corregido y que **solo** se han probado con pruebas automatizadas
(Docker de pega, contenedor `debian:12`): M4-01 falló (RC=1 por `DB_PASSWORD`), M4-02 se midió **después** de intervenir a mano, y el
`.env` era legible por cuentas no administrativas. La evidencia histórica **no se toca ni se sobrescribe** (`docs/evidencias/m4/…`
si #240 la incorpora): este ensayo genera la suya, con otro candidato y otro directorio.

## 2. Candidato y manifiesto

| | |
|---|---|
| Candidato | `f2c04212476d7ec1ed8a69cedc8130b4a7b4b9e9` — merge de #238 en `main` (padres `97f6acf` [#143] y `0df8946` [cabeza aprobada de #238]) |
| Manifiesto | [`MANIFIESTO-CANDIDATO.txt`](MANIFIESTO-CANDIDATO.txt), generado por `bash anfitrion.sh manifiesto` (solo lectura, determinista; `verificar` comprueba que sigue al día) |
| Contiene | commit, árbol, SHA-256 del `bootstrap.sh`, del CSS y de 14 ficheros clave; cabeza de Alembic esperada (`0019`); memoria declarada (512 M ×2, 16 M el servicio `credenciales`); qué flags `*_ENABLED` transmite Compose (**solo `FORUM_ENABLED`**); defaults de las fuentes; huellas del punto de partida de la VM |
| Regla | un commit posterior **no sustituye** a este candidato; un cambio de producto es un candidato nuevo |

## 3. Punto de partida de la VM

Se reutiliza, **sin modificar**, lo de la fase 1 (se abre solo como base de solo lectura de una superposición nueva):

| Pieza | Identificación (comprobada por `verificar`) |
|---|---|
| Imagen oficial Debian 12 `genericcloud-amd64` build `20261015-2632` | SHA-512 `56c0bd55…c2b37` |
| `preparacion.qcow2` (Debian + Docker 5:29.8.2 + compose 5.6.0 + imágenes `postgres:15-alpine` y `python:3.11-slim-bookworm` por digest + git + python3, **sin** el producto) | SHA-256 `6ed7f684…a0f28b9` |
| Superposición de este ensayo | `f1bis-prep.qcow2` sobre la anterior (preparación, con red) → `f1bis-ejec.qcow2` sobre esa (ejecución, sin red). La de la fase 1 (`m4-01.qcow2`) no se toca |

Consecuencia declarada: **la rama de `bootstrap.sh` que instala Docker con `get.docker.com` queda NOT RUN** (Docker ya está
instalado desde el repositorio APT oficial), igual que en la fase 1.

## 4. Entorno, límites y ventana

| Recurso | Límite (los de la fase 1) |
|---|---|
| VM | 2 vCPU · 4 GB · disco de 20 GB · QEMU/KVM sin privilegios · sin carpetas compartidas, USB ni discos físicos ni socket Docker del anfitrión · solo SSH en `127.0.0.1:2222` |
| Anfitrión | directorio nuevo y dedicado `/mnt/Datos/ensayo-m4-f1bis` (≤ 25 GB) · ≥ 10 GB libres durante toda la fase · nada fuera de él |
| Red | **abierta solo en `preparar`** (§5); **cerrada (`restrict=on`) en `ejecutar`**, y la propia ejecución lo comprueba (A-10) |
| Ventana | `preparar` ≤ 45 min · `ejecutar` ≤ 60 min (cada una con `timeout`); se propone **una ventana de 2 h** que las contiene con margen |
| Tiempo previsto | preparar ≈ 15–25 min (arranque + construcción de la imagen); ejecutar ≈ 20–30 min (instalación 1–3 min, observación de salud 5 min, identidades < 1 min, reejecución 1–3 min, fuentes ~1 min) — **estimaciones, no medidas** |
| Al agotar tiempo o presupuesto | no se inicia ningún paso más; se apaga la VM de forma controlada y se informa. **No se borra nada ajeno para hacer sitio** |

## 5. Descargas necesarias (a autorizar)

| Qué | Cuándo | Origen | Estimación | Notas |
|---|---|---|---|---|
| Paquetes Debian del `Dockerfile` (`build-essential`, `libpq-dev`, `libxml2-dev`, `libxslt-dev` en la etapa de construcción; `libpq5`, `libxml2`, `libxslt1.1`, `tini` en la final) | `preparar` | `deb.debian.org`, desde dentro del contenedor de construcción | ≈ 150–200 MB | cambia `src/` respecto a la fase 1, así que la capa de `pip` **no** está en caché |
| Dependencias de Python (`pip install .`) | `preparar` | `pypi.org` / `files.pythonhosted.org` | ≈ 50–100 MB | versiones resueltas → `pip-freeze.txt` |
| **Nada más**: las dos imágenes base ya están en la VM (se comprueba su digest y **no se descarga otra**; si difiere, se detiene) | — | — | 0 | |
| **Total** | | | **≈ 200–300 MB; tope duro 600 MB** (`vm-preparar.sh` lo mide con los bytes recibidos y aborta si lo supera) | la fase 1 recibió 374 MB entre dos imágenes y una construcción similar |

**Alternativa que se propone NO usar ahora (a decidir por el responsable): construcción en frío durante la ejecución.** El
`bootstrap.sh` construiría la imagen con red abierta. Es más fiel, pero exige red durante la instalación, justo la fase que se
quiere observar con la red cerrada, y QEMU no puede abrir solo tres nombres. Con la caché de `preparar`, **el resultado de la
construcción se registrará como «con caché (NOT RUN en frío)»** (I-04); una construcción desde cero queda para una fase con ventana
de red propia.

## 6. Fuentes realmente apagadas — cómo llegan los flags al contenedor

Hallazgo que condiciona el guion: **escribir `COMICVINE_ENABLED=false` (y las otras tres) en el `.env` no sirve.** Compose solo
pasa al contenedor las variables que declara en `environment:`, y de las `*_ENABLED` solo declara `FORUM_ENABLED`:

```
$ docker compose -f docker-compose.yml --env-file <env con las cuatro a false> config   # candidato f2c0421, sin arrancar nada
{'FORUM_ENABLED': 'false'}                                              # el contenedor recibe SOLO esa
```

| Vía | ¿Llega a la aplicación? | Estado |
|---|---|---|
| Líneas `COMICVINE_ENABLED=` … en el `.env` | **No** (inertes: Compose no las transmite) | `F-01` lo comprueba en la VM |
| `FORUM_ENABLED` | Sí; por defecto `false` | integración de descarga, otra categoría |
| `prowlarr/transmission/amule_enabled` | No se transmiten; el default de `config.py` es `False` | efectivo `False` (`F-03`, leído dentro del contenedor) |
| **Ajustes (override de runtime, fila de `runtime_settings` en la BD)**: `POST /ui/ajustes/guardar/fuentes` | **Sí**, persiste y sobrescribe el default **también al arrancar** | **vía elegida**. Probada en local con la aplicación sobre Postgres: sin cabecera `Origin` → 403; con ella → 200 y `/api/health` pasa a `disabled`; y **tras reiniciar la aplicación** (nuevo arranque sobre la misma BD) siguen `disabled`. `F-07` lo repite en la VM |
| Un `-f` extra con un override de Compose | Llegaría | el instalador invoca `compose` con `-f` fijo: habría que cambiar su invocación o los defaults ⇒ es la decisión de **#239**, no de este ensayo |

**Qué distingue este guion (corrección de la ambigüedad del plan §3.3):** *fuentes de metadatos* (Comic Vine, AniList, Tebeosfera, GCD:
`default=True` en `config.py`) **no** están apagadas de fábrica, y el ensayo las apaga por Ajustes y lo demuestra; *integraciones de
descarga y foro* (Prowlarr, Transmission, aMule, foro) **sí** nacen apagadas, y se comprueba su valor efectivo dentro del contenedor.

Orden en `vm-ejecutar.sh` (`seccion_fuentes`): (1) qué `*_ENABLED` recibe el contenedor → (2) **estado tal como se instala**
(esperado: las cuatro `enabled`; se registra como el hallazgo vigente de #239, **no** como PASS ni como defecto nuevo) → (3) descarga
efectiva → (4) POST de Ajustes → (5) `/api/health` y `runtime_settings` (sin imprimir `secret_key`) → (6) **reinicio de la aplicación
y comprobación de que persiste** → (7) cero intentos de conexión externa en los registros de **toda** la fase.

**Límite declarado (F-11):** la aplicación arranca una vez con los defaults antes de poder configurarla (el instalador no ofrece un
gancho entre las migraciones y el arranque). Esa ventana dura segundos, con red cerrada y sin aceptación legal (el orquestador omite
sus ciclos, `F-09`). **La red cerrada y la barrera legal son salvaguardas adicionales, no sustituyen apagar las fuentes.** Esta
comprobación completa la parte operativa de #239 sin decidir un cambio de defaults.

## 7. Pasos

```bash
bash docs/design/m4-fase1bis/anfitrion.sh verificar   # solo lectura (ya ejecutado sobre esta cabeza: todo en orden)
bash docs/design/m4-fase1bis/anfitrion.sh preparar    # PIDE AUTORIZACIÓN: red abierta, descargas §5
bash docs/design/m4-fase1bis/anfitrion.sh ejecutar    # PIDE AUTORIZACIÓN: red cerrada, ensayo
bash docs/design/m4-fase1bis/anfitrion.sh cerrar      # solo lectura: sin QEMU, sin puerto, huellas, almacenamiento
```

`ejecutar` corre `vm-ejecutar.sh` dentro de la VM como root, en este orden: **antes** (punto de partida limpio, huella de la
biblioteca) → **instalacion** (`bootstrap.sh` sin terminal y sin preparar `DB_PASSWORD`) → **salud** → **credenciales** →
**reejecucion** → **originales** → **fuentes** → **cierre**. Cada comprobación escribe `PASS|FAIL|NOT_RUN id detalle` y **nunca** un
valor secreto (solo longitudes, modos y huellas).

## 8. Criterios de aceptación → comprobaciones

| # | Criterio de la fase | Comprobaciones |
|---|---|---|
| 1 | Instalación completa sin editar credenciales | `A-01…A-10` (punto de partida limpio, `bootstrap.sh` = el del candidato, red cerrada) · `I-01` RC=0 · `I-02` URL publicada · `I-03` sin petición de editar el `.env` · `I-05` el `.env` lo creó el instalador · `I-04` construcción con o sin caché |
| 2 | Interfaz, BD y esquema | `S-01…S-03` (`/api/health`, `/estado`, CSS del candidato) · `S-04` BD conectada · `S-05` `alembic_version` = cabeza del candidato = cabeza en el contenedor · `S-06…S-08` aplicación y PostgreSQL sanos, **`credenciales` terminado con código 0** (salida esperada, no un servicio caído) · `S-09` memoria **efectiva** en el cgroup (512 M) · `S-10/11` 5 muestras, 0 reinicios, 0 OOM · `S-12` puertos solo en el bucle local |
| 3 | Protección efectiva | `C-01…C-07` modo, propietario, repo de root y sin escritura ajena, enlace, contraseña generada, sin valor por defecto en el compose · `C-10…C-12` **controles positivos** · `C-20-<usuario>-*` (×2 usuarios: servicio `media` y ordinario `otroprueba`): **leer, leer por el enlace, añadir, truncar, borrar, mover, sustituir, crear junto a él, redirigir (×2), y modificar compose, Dockerfile, scripts y `bootstrap.sh`** · `C-30` intacto tras los intentos · `C-31` la credencial no aparece en salida, evidencia ni registros de contenedores |
| 4 | Credencial conservada | `R-01…R-05`: reejecución con las mismas respuestas, `.env` **byte a byte igual**, modo intacto, la aplicación sigue conectando, no regenera. **No es una prueba de actualización desde otra versión** (`R-06`, NOT RUN) |
| 5 | Originales intactos | `O-01` ruta, nombre, tamaño y SHA-256 de cada original antes/después · `O-02` carpetas vacías nuevas (observación: el instalador crea la estructura documentada) · `O-03` no desaparece ninguna |
| 6 | Fuentes apagadas, sin consultas externas | `F-01…F-11` (§6) |
| 7 | Informe por candidato | §10 |

**Un fallo de seguridad detiene la fase** (§9).

## 9. Condiciones de parada

1. **Cualquier intento de lectura, modificación, sustitución o redirección que TENGA ÉXITO** por una identidad no administrativa ⇒
   `vm-ejecutar.sh` registra `FAIL`, imprime `PARADA DE SEGURIDAD` y sale con **código 3**, **sin reparar nada ni continuar**. No se
   corrige sobre la marcha para convertir el intento inicial en PASS; el hallazgo se informa y se decide después.
2. Ventana o presupuesto de descarga/almacenamiento superados, o espacio libre del anfitrión < 10 GB ⇒ no se inicia más; se apaga.
3. Un fallo del producto **no** se parchea para continuar; un fallo del arnés se clasifica primero como tal.
4. Un requisito no previsto (un recurso que el instalador necesita y no hay) ⇒ se detiene y se clasifica **antes** de declarar FAIL.

## 10. Qué entrega la ejecución (informe por candidato)

Un informe verificable con tres columnas separadas — **producto**, **arnés**, **límites del entorno** — y cada resultado como PASS,
FAIL o NOT RUN con su evidencia (`evidencia/evidencia-vm.tar.gz`, `cronologia.txt`, `huellas-finales.txt`, bytes descargados y
consumo). Se saneará (búsqueda de secretos, URLs con credenciales, cabeceras y cadenas de alta entropía) antes de compartirse, y
**no se sobrescribe** la evidencia de la fase 1.

**Adaptaciones del arnés que se registrarán** (no son resultados del producto): espejo Git local que resuelve el repositorio del
producto contra el candidato (`insteadOf`; no acredita conectividad con GitHub) · imagen construida desde la caché de `preparar` ·
acceso por SSH · biblioteca sintética y usuario `otroprueba` creados antes · Docker preinstalado.

## 11. Fuera de alcance (NOT RUN)

M4-03…M4-20 (actualización, restauración, presión de disco, fallos provocados) · producción, Raspberry Pi/ARM, fuentes reales y
bibliotecas personales · cambios de defaults o de código durante el ensayo · aceptación global de M4 · repetir #143 por formalismo
(su evidencia automatizada queda enlazada; la comprobación integrada que exija M4 sigue separada) · construcción en frío ·
instalación de Docker por `get.docker.com` · esfuerzo humano medido · particularidad de Raspberry Pi OS con el controlador de memoria.

## 12. Autorizaciones que se piden (y decisiones del responsable)

1. **Ejecutar `preparar`**: crear `/mnt/Datos/ensayo-m4-f1bis`, arrancar la VM **con red** y descargar solo lo de §5 (tope 600 MB).
2. **Ejecutar `ejecutar`**: nueva superposición limpia, VM **sin red**, ensayo completo, apagado.
3. **Decisión: construcción con caché (recomendada ahora) o en frío con ventana de red propia** (§5).
4. **Decisión: confirmar la vía de configuración efectiva de las fuentes** (Ajustes/`runtime_settings`, §6) como adaptación documentada del ensayo — no como cambio de defaults.
5. Ventana horaria (2 h) y que la ejecución la haga Claude con revisión de Perplexity.

No se pide: tocar el tablero, corregir producto, fusionar, desplegar, ni arrancar la Pi.

## 13. Qué se ha comprobado de ESTE guion (sin arrancar la VM)

- `anfitrion.sh verificar` ejecutado sobre el equipo real, **solo lectura**: KVM, QEMU, repositorio con el candidato, manifiesto al día,
  huellas de la imagen base y de `preparacion.qcow2`, VM ausente, puerto libre, 434 GB libres → **todo en orden**.
- `bash -n` de los tres scripts.
- `tests/escenarios/guion_f1bis.sh` (corre en la suite `test_credenciales_aisladas.py`, como root en un contenedor sin red): la
  sección de identidades da **32 PASS y 0 FAIL** sobre una instalación hecha por el `bootstrap.sh` real, y **se para con código 3**
  sobre una instalación heredada y expuesta, sin imprimir la credencial ni reparar. Mutaciones del guion (`negar` que da PASS siempre, el
  intento de lectura que no intenta nada, sin controles positivos) rompen esas pruebas.
- **No comprobado** (necesita la VM): las secciones `instalacion`, `salud`, `reejecucion`, `originales` y `fuentes` contra Docker real; la
  construcción de la imagen; los umbrales de tiempo. Las órdenes de esas secciones usan los mismos comandos que la fase 1, pero su
  primera ejecución real será la del ensayo; por eso, si la instalación falla, el guion no mide el resto (`X-01`, NOT RUN): solo compara los originales (un instalador que falla tampoco debe haberlos tocado) y cierra.
