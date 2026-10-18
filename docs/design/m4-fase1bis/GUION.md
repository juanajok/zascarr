# M4 · Fase 1 bis — validar la instalación real y la protección de credenciales tras #238

> **Estado: PROPUESTA documental y scripts, sin ejecutar (2.ª versión, tras la devolución de #242).** No se ha arrancado ninguna VM, descargado nada ni cambiado el tablero.
> Decisiones ya confirmadas: construcción **con caché** (la construcción en frío queda NOT RUN) y **Ajustes** como vía efectiva de las fuentes (adaptación del ensayo, sin cambiar defaults).
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

## 4. Entorno, límites y ventana — y cómo se HACEN CUMPLIR

Un límite que solo se declara no es una garantía. Cada fila dice quién lo vigila, cuándo y qué exceso cabe (código en `lib-ensayo.sh` y
`anfitrion.sh`; las pruebas con dobles, en `tests/test_ensayo_f1bis_arnes.py`). Unidades: **MiB/GiB** (1 MiB = 1.048.576 bytes).

| Límite | Valor | Quién lo hace cumplir y con qué exceso posible |
|---|---|---|
| VM | 2 vCPU · 4 GiB · disco de 20 GiB · QEMU/KVM sin privilegios · sin carpetas compartidas, USB, discos físicos ni socket Docker del anfitrión · solo SSH en `127.0.0.1:2222` | opciones de QEMU en `arrancar` |
| **Descarga** | **tope 600 MiB** | **Dos capas.** (1) **Tope en el núcleo** (`instalar_tope_de_red`, nftables en la VM, enganchado en `prerouting` para ver también el tráfico de los contenedores de la construcción): cuenta lo que entra por la interfaz —salvo el SSH de control— y **descarta** lo que pase de la cuota (**98 % del tope = 588 MiB**, por la diferencia entre lo que cuenta nftables y `rx_bytes`). No depende de ningún proceso ni de una muestra: el exceso posible es **un paquete** (≈ 1,5 KB). Comprobado de forma funcional en un espacio de nombres de red real. (2) **Vigilante** (`con_limite_de_descarga`, cada 1 s): al llegar al umbral de corte (500 MiB) **corta la red** (descarta todo salvo el SSH) y **termina el grupo de procesos entero —TERM, KILL— comprobando que no queda NINGÚN miembro vivo**, no solo el líder; si queda alguno, devuelve 5. `docker build` es un **cliente**: BuildKit construye en el servicio y matar el cliente no prueba que haya dejado de descargar; por eso el corte de **red** va primero y es lo que garantiza el tope (el constructor puede seguir sin red hasta que sus pasos fallen por tiempo de espera, sin gastar descarga) |
| **Almacenamiento** | ≤ 25 GiB en `/mnt/Datos/ensayo-m4-f1bis` | `vigilante_anfitrion` (cada 2 s mientras la VM trabaja): si lo supera, escribe `.parada` y **para la VM propia**. Exceso posible: el crecimiento de un disco en 2 s |
| **Espacio libre** | ≥ 10 GiB en el anfitrión | el mismo vigilante; el fallo ya no se descarta: `.parada` marca la fase como interrumpida y ni `preparacion.ok` ni la ejecución se dan por buenas |
| **Ventana** | `preparar` ≤ 45 min · `ejecutar` ≤ 60 min (2 h en total con margen) | **Un plazo único por fase, desde que empieza** (bundle, superposición, arranque, espera de SSH, copias, orden remota, recuperación de evidencias y apagado están DENTRO). `paso_permitido` se pregunta antes de cada paso que no es limpieza: si no queda más que la **reserva de cierre (300 s: evidencias ≤ 120 s + apagado ≤ ~120 s + margen)**, no se empieza, se escribe `.parada` y se va a la limpieza. La espera de SSH la corta el plazo, no el número de intentos; las copias usan `min(120 s, restante − reserva)`; y la orden remota usa **lo que queda menos la reserva** (`timeout --kill-after=30` dentro de la VM, no una cifra fija) |
| Red | **abierta solo en `preparar`**; **cerrada (`restrict=on`) en `ejecutar`** | la propia ejecución lo comprueba (A-10) y, si no es PASS, F-10 falla |
| Tiempo previsto | preparar ≈ 15–25 min; ejecutar ≈ 20–30 min | **estimaciones, no medidas** |

**Ciclo de vida de la VM:** `trap` ante salida normal, error y señal (`INT`, `TERM`, `HUP`); el comando remoto largo va en segundo plano y se espera
con `wait`, porque bash difiere los `trap` mientras corre una orden en primer plano. La VM propia se identifica por **PID y atributos**
(`-name m4-f1bis` y un disco bajo el directorio del ensayo): un PID que no los cumple **no se señala jamás**. El apagado es limpio por SSH
(acotado), luego TERM, luego KILL, con esperas acotadas; **no se borra el PID ni se anuncia «apagada» hasta comprobar que el proceso ha terminado**
(un zombi cuenta como terminado). `pgrep -x qemu-system-x86_64` **no** se usa: el nombre de proceso se trunca a 15 caracteres y esa comparación
nunca casaría; se recorre `/proc`. Si la VM no se puede parar, se dice y se sale con error.

**`ejecutar` rechaza una preparación incompleta o fallida:** exige `preparacion.ok` (escrito solo si el comando remoto terminó con RC=0, imprimió
`PREPARACIÓN TERMINADA`, no hubo `.parada` y la VM se comprobó apagada), del mismo candidato, con el disco sin cambios desde entonces, y no
reutiliza una ejecución previa.

**Al agotar tiempo o presupuesto** no se inicia ningún paso más; se apaga la VM de forma controlada y se informa. **No se borra nada ajeno para hacer sitio.**

## 5. Descargas necesarias (a autorizar)

| Qué | Cuándo | Origen | Estimación | Notas |
|---|---|---|---|---|
| Paquetes Debian del `Dockerfile` (`build-essential`, `libpq-dev`, `libxml2-dev`, `libxslt-dev` en la etapa de construcción; `libpq5`, `libxml2`, `libxslt1.1`, `tini` en la final) | `preparar` | `deb.debian.org`, desde dentro del contenedor de construcción | ≈ 150–200 MiB | cambia `src/` respecto a la fase 1, así que la capa de `pip` **no** está en caché |
| Dependencias de Python (`pip install .`) | `preparar` | `pypi.org` / `files.pythonhosted.org` | ≈ 50–100 MiB | versiones resueltas → `pip-freeze.txt` |
| **Nada más**: las dos imágenes base ya están en la VM (se comprueba su digest y **no se descarga otra**; si difiere, se detiene) | — | — | 0 | |
| **Total** | | | **≈ 200–300 MiB estimados; tope 600 MiB** (§4: cuota en el núcleo al 98 %, y corte de red + grupo de procesos al umbral de 500 MiB) | la fase 1 recibió 374 MiB entre dos imágenes y una construcción similar |

**Decisión confirmada: construcción con caché. La construcción en frío durante la ejecución queda NOT RUN** (alternativa descartada por ahora): El
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

**Orden (corregido tras la devolución): las fuentes se apagan JUSTO tras instalar, no al final.** `seccion_fuentes_iniciales` va inmediatamente
después de la instalación y antes de la observación de salud, las identidades y la reejecución:

1. primera respuesta utilizable de `/api/health`;
2. `F-01` qué `*_ENABLED` recibe el contenedor (solo nombres);
3. `F-02` **estado tal como se instala** (esperado: las cuatro `enabled`; hallazgo vigente #239, ni PASS ni defecto nuevo);
4. `F-04` apagado **inmediato** por Ajustes (`POST` con `Origin` local) y `F-05` estado efectivo en `/api/health`;
5. `F-11` **ventana medida** (arranque de la aplicación → apagado), en segundos, con red cerrada y sin aceptación legal;
6. `F-06` la fila de `runtime_settings`: **solo se exportan los cuatro flags** (`concat_ws` de esos cuatro valores; no se vuelca la configuración
   de runtime, ni siquiera «excluyendo `secret_key`»);
7. `F-03` integraciones de descarga y foro apagadas, leídas **dentro del contenedor** (`docker exec -i`: sin `-i` el programa del heredoc no se entrega).

Si las fuentes no quedan apagadas, **el ensayo no continúa** (X-02): no se mide nada con fuentes activas.
`seccion_fuentes_persistencia` va **después**, y lo dice: `F-07a` tras la reejecución del instalador (que recrea la aplicación) siguen
`disabled`; **reinicio deliberado** de la aplicación (registrado como tal en `reinicios-deliberados.txt`, fuera de la observación de salud) y `F-07`;
`F-08` **no observados** intentos de conexión externa ni referencias a fuentes en los registros de la aplicación (acredita ausencia *en esos
registros*, no ausencia universal de intentos); `F-09` ciclos del orquestador omitidos por falta de aceptación legal; `F-10` solo es PASS si
`A-10` lo fue (la red cerrada es una salvaguarda adicional, no un sustituto).

**Límite declarado (F-11):** la aplicación arranca una vez con los defaults antes de poder configurarla (el instalador no ofrece un gancho entre las
migraciones y el arranque); esa ventana **se mide** y no se mantiene el resto del ensayo con las fuentes activas. Esta comprobación completa la parte
operativa de #239 sin decidir un cambio de defaults.

## 7. Pasos

```bash
bash docs/design/m4-fase1bis/anfitrion.sh verificar   # solo lectura (ya ejecutado sobre esta cabeza: todo en orden)
bash docs/design/m4-fase1bis/anfitrion.sh preparar    # PIDE AUTORIZACIÓN: red abierta, descargas §5
bash docs/design/m4-fase1bis/anfitrion.sh ejecutar    # PIDE AUTORIZACIÓN: red cerrada, ensayo
bash docs/design/m4-fase1bis/anfitrion.sh cerrar      # solo lectura: sin QEMU, sin puerto, huellas, almacenamiento
```

`ejecutar` corre `vm-ejecutar.sh` dentro de la VM como root, en este orden: **antes** (punto de partida limpio, huella de la
biblioteca) → **instalacion** (`bootstrap.sh` sin terminal y sin preparar `DB_PASSWORD`) → **fuentes_iniciales** (apagado inmediato) →
**salud** → **credenciales** → **reejecucion** → **originales** → **fuentes_persistencia** → **cierre**. Cada comprobación escribe `PASS|FAIL|NOT_RUN id detalle` y **nunca** un
valor secreto (solo longitudes, modos y huellas).

## 8. Criterios de aceptación → comprobaciones

| # | Criterio de la fase | Comprobaciones |
|---|---|---|
| 1 | Instalación completa sin editar credenciales | `A-01…A-10` (punto de partida limpio, `bootstrap.sh` = el del candidato, red cerrada) · `I-01` RC=0 · `I-02` URL publicada · `I-03` sin petición de editar el `.env` · `I-05` el `.env` lo creó el instalador · `I-04` construcción con o sin caché |
| 2 | Interfaz, BD y esquema | `S-01…S-03` (`/api/health`, `/estado`, CSS del candidato) · `S-04` BD conectada · `S-05` `alembic_version` = cabeza del candidato = cabeza en el contenedor · `S-06…S-08` aplicación y PostgreSQL sanos, **`credenciales` terminado con código 0** (salida esperada, no un servicio caído) · `S-09` memoria **efectiva** en el cgroup (512 M) · `S-10/11` 5 muestras, 0 reinicios, 0 OOM · `S-12` puertos solo en el bucle local |
| 3 | Protección efectiva | `C-01…C-07` modo, propietario, repo de root y sin escritura ajena, enlace, contraseña generada, sin valor por defecto en el compose · `C-10…C-12` **controles positivos** · `C-20-<usuario>-*` (×2 usuarios: servicio `media` y ordinario `otroprueba`): **leer, leer por el enlace, añadir, truncar, borrar, mover, sustituir, crear junto a él, redirigir (×2), y modificar compose, Dockerfile, scripts y `bootstrap.sh`** · `C-30` intacto tras los intentos · `C-31` la credencial no aparece en salida, evidencia ni registros de contenedores |
| 4 | Credencial conservada | `R-01…R-05`: reejecución con las mismas respuestas, `.env` **byte a byte igual**, modo intacto, la aplicación sigue conectando, no regenera. **No es una prueba de actualización desde otra versión** (`R-06`, NOT RUN) |
| 5 | Originales intactos | `O-01` ruta, nombre, tamaño y SHA-256 de cada original antes/después · `O-02` carpetas vacías nuevas (observación: el instalador crea la estructura documentada) · `O-03` no desaparece ninguna |
| 6 | Fuentes apagadas, sin consultas externas | `F-01…F-11` (§6): apagado inmediato tras instalar, ventana medida, persistencia tras reejecución y tras reinicio deliberado, **no observados** intentos externos en los registros |
| 7 | Informe por candidato | §10 |

**Un fallo de seguridad detiene la fase** (§9).

## 9. Condiciones de parada

1. **Cualquier intento de lectura, modificación, sustitución o redirección que TENGA ÉXITO** por una identidad no administrativa ⇒
   `vm-ejecutar.sh` registra `FAIL`, imprime `PARADA DE SEGURIDAD` y sale con **código 3**, **sin reparar nada ni continuar**.
2. **Una precondición fallida impide instalar** (red cerrada, candidato, espejo, punto de partida limpio, usuario ordinario sin privilegios): se
   registra `X-00` («problema del arnés o del entorno, NO del producto»), se cierra y se sale con **código 2** sin haber ejecutado `bootstrap.sh`.
3. **Controles positivos fallidos** (`C-10…C-12`): no se ejecutan ni se interpretan las denegaciones (`C-13`, código 2): «denegado» no demostraría nada.
4. **La instalación falla** (`I-01`, `I-02` o `I-05` en FAIL): no se mide el resto (`X-01`); solo se comparan los originales y se cierra.
5. **Las fuentes no quedan apagadas** tras el POST de Ajustes: no se continúa con fuentes activas (`X-02`).
6. Ventana, presupuesto de descarga, almacenamiento o espacio libre superados (§4): se corta/para y se informa; `ejecutar` y `preparar` no se dan por buenos.
7. Un fallo del producto **no** se parchea para continuar; un fallo del arnés se clasifica primero como tal. Un requisito no previsto ⇒ se detiene y se clasifica **antes** de declarar FAIL.

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

## 12. Autorizaciones y decisiones

**Confirmadas por el responsable (devolución de #242):** construcción con caché (la construcción en frío queda NOT RUN) · Ajustes como vía efectiva de
configuración de las fuentes, como adaptación documentada del ensayo y sin cambiar defaults, **con apagado inmediato tras el arranque inicial** (§6) ·
ventana de 2 h, `preparar` ≤ 45 min y `ejecutar` ≤ 60 min como presupuesto propuesto, **ahora hecho cumplir por el arnés** (§4).

**Siguen sin autorizar (se piden de nuevo sobre la cabeza definitiva de esta PR):**
1. **`preparar`**: crear `/mnt/Datos/ensayo-m4-f1bis`, arrancar la VM **con red** y descargar solo lo de §5 (tope 600 MiB, corte a 500 MiB).
2. **`ejecutar`**: nueva superposición limpia, VM **sin red**, ensayo completo, apagado comprobado.

No se pide: tocar el tablero, corregir producto, fusionar, desplegar, ni arrancar la Pi.

## 13. Qué se ha comprobado de ESTE guion (sin arrancar la VM)

- `anfitrion.sh verificar` ejecutado sobre el equipo real, **solo lectura**: todo en orden (KVM, QEMU, candidato en el repo, manifiesto al día, huellas de la
  base y de `preparacion.qcow2`, sin QEMU, puerto libre, 434 GiB libres).
- **El arnés se prueba con dobles y procesos controlados** (`tests/test_ensayo_f1bis_arnes.py`, 61 casos; ni QEMU, ni Docker, ni red externa): una «VM» de mentira
  cuyo `argv[0]` es `qemu-system-x86_64` (`tests/_vm_falsa.py`), un contador de bytes recibidos manejable, un **reloj manejable** y órdenes remotas sustituidas.
  Demuestra: el corte de descarga **termina el grupo entero** (un líder que muere con TERM y un hijo que lo ignora: el hijo muere; si nada se puede matar, devuelve 5,
  no 4) y **corta la red antes** de matar; **el tope en el núcleo es real** (una prueba funcional con un par veth en un espacio de nombres de red sin privilegios: con tope
  de 5 MiB se reciben ≈ 4 MiB de 30 enviados, tras cortar la red 0, y el puerto 22 pasa siempre); el vigilante **para la VM** por poco espacio libre o almacenamiento; la VM
  propia se reconoce por PID y atributos y **un proceso ajeno jamás se señala**; el apagado escala TERM→KILL y **no borra el PID si no consigue matarla**; una **señal durante
  `preparar` limpia al momento**; **`ejecutar` rechaza** una preparación incompleta (sin marcador, otro candidato, RC≠0, disco cambiado, `.parada`, ejecución previa); **el plazo
  es único por fase**: un arranque lento, una copia lenta o una espera de SSH lenta impiden el siguiente paso, dejan `.parada`, no lanzan la orden remota y limpian; la orden remota
  recibe lo que queda menos la reserva; una precondición fallida impide instalar; las fuentes se apagan justo tras instalar; unos controles positivos fallidos no permiten interpretar
  denegaciones. Las mutaciones del arnés (el corte que solo mira al líder, que no corta la red, la cuota al 150 %, el SSH no exceptuado, un paso sin guarda de plazo, la espera de SSH
  sin plazo, la orden remota con plazo fijo, borrar el PID sin comprobar la muerte, la limpieza que no para la VM…) rompen pruebas; las que sobrevivían a la primera tanda se cerraron.
- `tests/escenarios/guion_f1bis.sh` (en la suite de credenciales, como root en un contenedor sin red): la sección de **credenciales** del guion
  da **41 PASS y 0 FAIL** sobre una instalación hecha por el `bootstrap.sh` real —incluidas las comprobaciones estáticas con las órdenes de **Debian 12**
  (`stat` sobre el enlace, `find -perm`)— y **se para con código 3** sobre una instalación heredada y expuesta, sin imprimir la credencial ni reparar.
- **No comprobado** (necesita la VM): que la regla de nftables se cargue en el Debian de la VM (el paquete `nftables` es dependencia de `docker-ce`; `vm-preparar.sh` aborta antes de descargar si no se puede cargar); las secciones `instalacion`, `salud`, `reejecucion`, `originales` y `fuentes_*` contra Docker real; la construcción de la imagen;
  el comportamiento real de la red de QEMU con `restrict=on`; los tiempos. Sus órdenes reutilizan las de la fase 1, pero su primera ejecución real será el ensayo.
