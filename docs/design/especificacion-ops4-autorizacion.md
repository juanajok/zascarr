# SPEC — autorización corta app→host para actualizar ZascArr (#443, OPS4)

> **Snapshot previo a la fase de desarrollo (55baba87).** Los recuentos de tests de este documento son los de entonces; el estado final está en [QA](qa-ops4-autorizacion-2026-11-20.md) y en la matriz: 49 casos de contrato, 59 de composición, 791 OPS4/paridad y 8781 de suite completa.

> **Estado: especificación de contrato. No implementa, no conecta y no habilita
> nada.** Base: rama `feat/ops4-seguridad-443`, commit `55baba87` (2026-11-20).
> Recoge la decisión del usuario del 2026-11-20: **la app reautentica la
> contraseña actual y emite una autorización corta de un solo uso; el host la
> verifica y no vuelve a leer el hash de la BD para esta comprobación**
> ([ficha de la decisión](ops4-autorizacion-app-host.md)). El
> [benchmark](benchmark-ops4-autorizacion.md) es el insumo previo; esta SPEC
> fija el contrato que faltaba y **no lo aprueba**: la aprobación corresponde al
> PO y a la revisión de seguridad del SHA final.
>
> La actualización desde la UI sigue **DESHABILITADA**: no se conecta la UI, el
> auxiliar, `main.py` ni ninguna unidad; `update.sh` no se instala ni se ejecuta;
> no se toca la Pi, Docker de producción, systemd instalado ni datos reales. Nada
> de este documento autoriza a hacerlo. Las fases posteriores de implementación,
> integración y habilitación necesitan autorización explícita y separada.

## 1. Documentos de referencia y relación

| Documento | Papel respecto a esta SPEC |
|---|---|
| [benchmark-ops4-autorizacion.md](benchmark-ops4-autorizacion.md) | Insumo (nivel 2): problema, alternativas, riesgos y casos que faltan. No es aprobación. |
| [ops4-autorizacion-app-host.md](ops4-autorizacion-app-host.md) | Registro de la decisión y de sus pendientes; esta SPEC los desarrolla. |
| [ops4-concordancia-seguridad.md](ops4-concordancia-seguridad.md) | Por qué el host no puede tomar el hash de la BD como prueba de la configuración efectiva (M3 abierto). |
| [ops4-registro-repeticiones.md](ops4-registro-repeticiones.md) | Contrato del registro durable experimental que sirve de base al consumo único. |
| [ops4-propuesta-epoca.md](ops4-propuesta-epoca.md) | Hipótesis de época/fencing **no adoptada**; sus contraejemplos se usan como revisión adversarial. |
| [ops4-verificacion-contrasena.md](ops4-verificacion-contrasena.md) | Límites del verificador PBKDF2 del host. Aplica a OPS2 y a la vía v3 con contraseña, **no a esta ruta**. |
| [ops4-especificacion-main.md](ops4-especificacion-main.md) | Política de `main` y migraciones; su §3.2 contradice la decisión (ver §13). |
| [especificacion-BL-OPS4.md](especificacion-BL-OPS4.md) | SPEC histórica de C-12; se conserva **sin editar**. Sus §§2.4 y AC-04/AC-05 contradicen la decisión vigente (ver §13). |
| [especificacion-BL-OPS1.md](especificacion-BL-OPS1.md) y [especificacion-BL-OPS2.md](especificacion-BL-OPS2.md) | Contratos v1/v2 del auxiliar, que no cambian. |
| [ADR 0021](../adr/0021-auxiliar-del-host-para-operaciones.md) | Socket, `ops.key` y grupo del auxiliar. Al integrar: ampliarlo o crear un ADR de autorización app→host. |
| [verificacion-OPS4-host-2026-11-20.md](verificacion-OPS4-host-2026-11-20.md) | Evidencia de host sin privilegios y de la puerta actual. No acredita esta ruta. |

Código existente leído y no modificado por esta fase:
[emisor](../../src/zascarr/services/autorizacion_actualizacion.py),
[verificador](../../deploy/ops/verificador_autorizacion_ops4.py),
[registro durable experimental](../../deploy/ops/registro_repeticiones_ops4.py),
[admisión v3](../../deploy/ops/admision_actualizar_ops4.py),
[protocolo v3](../../deploy/ops/protocolo_actualizar_ops4.py),
[auxiliar](../../deploy/ops/zascarr_ops.py),
[reautenticación](../../src/zascarr/services/reautenticacion.py) y
[preparación de solicitud](../../src/zascarr/services/solicitud_actualizacion.py).
Pruebas: [autorización](../../tests/test_ops4_autorizacion.py),
[aislamiento](../../tests/test_ops4_aislamiento.py),
[UI deshabilitada](../../tests/test_ops4_ui_deshabilitada.py) y
[registro](../../tests/test_ops4_registro_repeticiones.py).

## 2. Alcance y no-alcance

### 2.1 Alcance

Esta SPEC es normativa para el contrato **app→host de una sola operación
`actualizar`**, y solo para él:

1. La composición obligatoria `auth_mode → reautenticación → emisión`.
2. La clave dedicada (requisitos y provisión pendiente).
3. El formato exacto del testigo, su dominio, sus límites y su verificación.
4. El consumo durable de un solo uso y su separación del registro de
   peticiones v3.
5. La ligadura del testigo al ID de petición/operación.
6. Los códigos de respuesta cerrados de app y host.
7. Los criterios de aceptación verificables y los requisitos de pruebas.
8. La exigencia de mantener la UI, el auxiliar, `main.py` y la unidad
   deshabilitados, y la puerta que haría falta para habilitar.

### 2.2 No-alcance

Queda **fuera** de esta SPEC y no se decide aquí:

- Habilitar, fusionar, desplegar o probar la actualización real, en cualquier
  entorno.
- Implementar la provisión de la clave, el transporte, el registro durable, la
  composición o la integración con el auxiliar.
- La fijación de `S` (SHA completo de `origin/main`), el origen autorizado, el
  lector/exportador de objetos Git, el build, las migraciones, la copia previa,
  el ejecutor, la salud, el cerrojo y la reconciliación de estados inciertos.
  Siguen rigiéndose por [ops4-especificacion-main.md](ops4-especificacion-main.md)
  y las puertas de [ops4-estado-bloqueo-2026-11-20.md](ops4-estado-bloqueo-2026-11-20.md).
- Cambiar los contratos v1/v2 de OPS1/OPS2, retirar código de la vía v3 con
  contraseña o añadir la acción `actualizar` a la tabla `UNIDADES`.
- La UX, los textos y la pantalla de confirmación de una futura UI (deberán
  tener su propia especificación; ver [§14](#14-riesgos-abiertos-y-preguntas-que-requieren-decisión)).
- Aprobar la aprobación root `A` de C-12 (retirada como política de producto
  para esta vía) ni la época/fencing de [ops4-propuesta-epoca.md](ops4-propuesta-epoca.md).
- Editar la SPEC histórica ni los documentos que contradicen la decisión: se
  señalan en §13 y se corregirán en el cambio de integración.
- Crear el ADR: se recomienda ampliar [ADR 0021](../adr/0021-auxiliar-del-host-para-operaciones.md)
  o crear uno nuevo **al integrar**, no en esta fase.

### 2.3 Lo que esta SPEC no autoriza

Ninguna frase de este documento equivale a «se puede habilitar ya». Hasta
cumplir [§12.3](#123-puerta-de-habilitación-explicita-y-separada) siguen
prohibidos la UI, el auxiliar, la unidad, `main.py`, el socket de producción,
`update.sh`, la Pi y Docker de producción. El contrato
[autorizacion_actualizacion.py](../../src/zascarr/services/autorizacion_actualizacion.py)
y
[verificador_autorizacion_ops4.py](../../deploy/ops/verificador_autorizacion_ops4.py)
permanece aislado y sin importar desde la aplicación, el auxiliar ni `main.py`.

## 3. Modelo de confianza y límites

### 3.1 Cadena de autoridad

```
persona ──(sesión+origen)──► app ──(contraseña actual)──► reautenticación OPS3
                                   │  solo si Reauth.OK
                                   ▼
                          emisor HMAC (clave dedicada) ──► testigo corto
                                   │
                                   ▼
             host: verifica testigo + consumo durable ──► guardas de operación
             (instalación, cerrojo, estado, unidad, S)  ──► unidad fija
```

- **La app es la autoridad de reautenticación** para esta ruta: comprueba la
  contraseña actual con el servicio compartido de OPS3
  (`comprobar_contrasena_actual`: mismo PBKDF2, mismo retardo progresivo y
  bloqueo de `/login`, cola de 3), y solo tras `Reauth.OK` emite.
- **El host no ve la contraseña ni el hash de la BD** en esta ruta. La prueba
  que recibe es la posesión de una clave dedicada por parte de la app, emitida
  solo para `accion="actualizar"`, un ID, una ventana corta y con consumo único.
- **El HMAC acredita posesión de la clave, no salud de la app, no identidad de
  la persona y no autorización del SHA.** El host debe seguir validando
  instalación, rutas, propiedad, cerrojo, estado y unidad antes de cualquier
  efecto, y fijar `S` por su cuenta.
- **El testigo no sustituye ninguna garantía de OPS1/OPS2** ni convierte el
  grupo del socket en autoridad de reautenticación.

### 3.2 Amenazas cubiertas por el contrato

| Amenaza | Defensa |
|---|---|
| Reutilizar el testigo (replay) dentro de su ventana | TTL corto (60 s por defecto, 300 s máx.), tolerancia de reloj acotada y consumo durable de un solo uso antes de cualquier efecto. |
| Manipular campos o añadir campos | Esquema cerrado con exactamente cinco claves, tipos estrictos (los booleanos no son enteros), ID hexadecimal, acción fija y HMAC sobre los bytes exactos del cuerpo. |
| Reutilizar una firma de otro protocolo | Dominio propio `zascarr-ops4-autorizacion-v1\n`, distinto de los dominios de `ops.key` v1/v2/v3 y de la firma del auxiliar. |
| Forjar el testigo con `ops.key` de grupo | Clave dedicada distinta; un token firmado con `ops.key` no verifica con la clave de autorización. |
| Usar el testigo en otra acción u otra petición | `accion="actualizar"` cerrada y `id_esperado` obligatorio en la integración: el ID del testigo debe coincidir con el ID de la petición autenticada. |
| Trasladar el testigo a otra instalación | La clave es aleatoria y única por instalación (la posesión de clave liga el testigo a esa instalación). |
| Inyectar secretos en el testigo | El formato prohíbe contraseña, hash, usuario, sesión, SHA o datos libres; el testigo no transporta secretos que se puedan leer en logs/estado. |
| Confundir al host para que acepte sin reautenticar | La composición obligatoria (§6) y su prueba: sin `Reauth.OK` no hay emisión; el host no recibe ningún booleano de la app que sustituta al testigo. |
| Respuesta perdida tras un consumo | No hay reintento ciego con el mismo ID/testigo; el resultado incierto se muestra como tal y se reconcilia en el host (§7.6). |

### 3.3 Amenazas y límites que este contrato **no** cubre

- **App o clave comprometidas:** un proceso que puedan leer la clave dedicada
  o controlar la app puede forjar testigos válidos. El host no puede distinguir
  «reauth real» de «app emite sin reautenticar». Esto es un riesgo residual
  aceptado de la decisión, no un fallo del formato; mitiga con permisos
  mínimos y con las guardas del host, no con el testigo.
- **Procesos con la clave por compartir grupo:** si el fichero de clave queda
  legible por el grupo general del servicio, cualquier miembro del grupo puede
  forjar testigos. De ahí la exigencia de grupo dedicado o permisos mínimos
  (§4.5).
- **Root, grupo `docker`, systemd y acceso físico:** son autoridades externas
  de confianza (ADR 0012/0021). El testigo no protege frente a ellas.
- **Navegador, sesión o contraseña comprometidos:** un atacante con sesión y
  contraseña actuales puede reautenticar y pedir la actualización; eso es
  exactamente el poder que la reautenticación concede.
- **Contenido de `main`:** el testigo no acredita autoría, firma, revisión ni
  inocuidad del código; tampoco fija el origen ni el SHA. `S` lo fija el host.
- **Identidad del host:** el testigo no demuestra que el host sea el correcto;
  lo asume la ruta local del socket y la instalación del auxiliar.
- **Confidencialidad:** el testigo es integridad, no cifrado; no debe contener
  secretos y no debe pasar por red. El canal debe ser el socket local del
  auxiliar (`0660 root:<grupo>`), nunca HTTP.
- **Durabilidad física:** `fsync` correcto no certifica hardware ni
  supervivencia a pérdida eléctrica. Los cortes de VM de
  [ops4-registro-repeticiones.md](ops4-registro-repeticiones.md#tres-cortes-abruptos-de-vm-2026-11-20)
  son evidencia acotada, no una garantía general.
- **Reloj:** el contrato tolera ±120 s, pero no demuestra reloj fiable. Reloj
  retrocedido o inválido es una pregunta abierta (§14).
- **Restauración completa de un snapshot del host:** podría resucitar marcas o
  volver a un estado anterior. El testigo solo acota la ventana a minutos; la
  política operativa queda abierta (§14).
- **Denegación de servicio:** el testigo no impide que un proceso con acceso al
  socket o a la clave consuma intentos, o que la app emita muchos testigos no
  usados. Los límites de frecuencia y el bloqueo compartido siguen siendo los
  de OPS1/OPS2/OPS3.

### 3.4 Supuestos de confianza

- El socket del auxiliar y su grupo están bajo control del operador; el
  auxiliar se ejecuta como root desde una unidad preexistente y endurecida.
- La app y el host comparten el mismo fichero de clave dedicada por un canal de
  solo lectura; no hay otro canal de red para esta operación.
- La app corre un único proceso (`uvicorn --workers 1`, CLAUDE.md §4): el
  estado en memoria de la reautenticación y su bloqueo son de ese proceso.
- `auth_mode` es `password` o `user_password`; `none` deniega la operación.
- El reloj del host se usa para `ahora`; la app usa `time.time()` para
  `creada`. Ambos deben estar razonablemente sincronizados (NTP) y la
  tolerancia acota el desfase.

## 4. Clave dedicada y provisión pendiente

### 4.1 Requisitos de la clave

1. **Dedicada y distinta de `ops.key`.** No se reutiliza la clave de
   OPS1/OPS2/OPS3 ni se deriva de ella, de `DB_PASSWORD` ni de ninguna otra
   credencial. `ops.key` es del grupo del auxiliar y su HMAC acredita
   pertenencia al grupo, **no reautenticación**; el prefijo de dominio evita
   mezclar firmas, pero no convierte una clave de grupo en prueba de reauth.
2. **32 bytes criptográficamente aleatorios** (`secrets.token_hex(32)`),
   únicos por instalación. Formato de fichero: 64 caracteres hexadecimales en
   minúsculas, con un `LF` final opcional; tamaño 64 o 65 bytes; fichero
   regular. No hay clave por defecto ni placeholder en `config.py`, `.env.example`
   ni imagen.
3. **Propietario y permisos:** `root` como propietario; grupo lo más estrecho
   posible (grupo dedicado de la app/host recomendado; como mínimo, el grupo
   del usuario de servicio); modo `0440`; directorio contenedor `0750`. El
   fichero **no** es escribible por la app ni por el grupo.
4. **Lectura segura:** la app lee el fichero con `O_RDONLY|O_NOFOLLOW` (o
   equivalente ya usado en `preparacion_solicitud._leer_clave`), comprueba
   tipo regular, tamaño exacto y decodifica hex; cualquier anomalía ⇒ no se
   emite. La lectura es E/S de bloqueo y debe ir en `asyncio.to_thread()`.
   El host (auxiliar root) lee el mismo fichero por una ruta constante de
   instalación; el verificador puro recibe los bytes, no abre ficheros.
5. **Nombre y ruta provisionales** (a fijar en el tramo de implementación):
   `ops4-autorizacion.key` dentro de la carpeta `ops` ya montada en la app
   (`<DATA_DIR>/ops`, `:ro` en el contenedor como `/run/zascarr-ops/`). La
   ruta exacta y la variable de configuración (p. ej.
   `OPS4_AUTORIZACION_KEY_FILE`) **no existen todavía**; declararlas en
   `config.py` es parte de la implementación pendiente.
6. **Nunca en observables:** la clave no se imprime, no va a logs, argv,
   entorno de la unidad, URL, estado, respuestas, tokens ni a la UI. El
   instalador no la imprime (mismo criterio que `ops.key`).

### 4.2 Provisión (pendiente, bloqueante)

La provisión **no está implementada** y bloquea la integración. Requisitos
para el tramo que la implemente:

- Crear el directorio y el fichero de forma idempotente: si el fichero ya
  existe, conservarlo (no regenerar en silencio); si no existe, crear en
  temporal con `umask 077`, `chown`/`chmod`, `mv -n` atómico y nunca imprimir
  ni copiar el contenido. Mismo patrón que `scripts/instalar_ops.sh` usa para
  `ops.key`.
- No reutilizar ni sobrescribir `ops.key`; no tocar las claves del `.env`.
- Fallar cerrado si el directorio o el fichero no tienen propietario/modo/tipo
  esperados. El instalador debe abortar antes de dejar una clave legible de
  más.
- La app debe arrancar y funcionar sin la clave **sin emitir** (la
  actualización sigue deshabilitada); si la función llegara a habilitarse,
  clave ausente o inválida ⇒ `no_disponible`, nunca emisión.
- Documentar la ruta y el procedimiento en el instalador y en el ADR al
  integrar; una prueba debe comprobar la creación, la idempotencia y los
  permisos (con usuario/directorio sintéticos, sin tocar `/var/lib` real).

### 4.3 Rotación y revocación

- Si se sospecha compromiso, se sustituye el fichero por una clave nueva
  generada igual, de forma atómica, y se reinicia la app para que la recargue
  (no hay caché de clave en la app: se lee al emitir).
- El auxiliar la lee por conexión (proceso de vida corta, `Accept=yes`), así
  que la rotación no requiere residente; una conexión en curso usa la versión
  que leyó. Los testigos antiguos dejan de verificar.
- Revocación = rotación. No hay «lista de claves válidas» ni `kid` en el
  testigo en esta versión; una transición con dos claves a la vez requiere
  decisión y cambio de formato (§14).
- El procedimiento exacto de rotación (quién la ejecuta, cómo se coordina con
  la app y el host, qué se muestra al operador) queda pendiente.

### 4.4 Separación de copia y restauración

- La clave **no** entra en el dump de PostgreSQL, ni en `copias.json`, ni en
  el flujo de restauración de OPS2. `backup.sh` solo copia la BD; una prueba o
  revisión debe confirmar que ninguna ruta de copia incluye la carpeta de
  claves.
- Restaurar una copia de la BD en otra instalación no restaura la autoridad:
  la clave nueva de esa instalación invalida los testigos antiguos. Eso es
  deliberado.
- Restaurar un snapshot **completo** del host (incluida la clave y el registro
  durable) puede resucitar marcas consumidas o borrar las nuevas. La ventana
  útil del testigo es de minutos; la política operativa ante restauración de
  host queda abierta (§14).

### 4.5 Riesgo residual de la clave

Si un proceso del grupo puede leer el fichero, puede forjar testigos. Por eso
se exige grupo dedicado o permisos mínimos y se documenta el residual: **quien
lea la clave puede iniciar la operación, aunque el host seguirá aplicando sus
guardas**. No se afirma que el grupo del socket sea una frontera contra la app
ni contra otros procesos del mismo grupo (ADR 0021).

## 5. Formato exacto del testigo

### 5.1 Serialización y dominio

```
token      = cuerpo "." firma
cuerpo     = JSON UTF-8 canónico compacto, exactamente:
             {"v":1,"accion":"actualizar","id":"<32 hex>","creada":<int>,"expira":<int>}
firma      = hex(HMAC-SHA256(clave, DOMINIO || cuerpo)), 64 hex minúsculas
DOMINIO    = b"zascarr-ops4-autorizacion-v1\n"
clave      = 32 bytes
```

- Orden de claves fijo (`v`, `accion`, `id`, `creada`, `expira`), separadores
  `,` y `:` sin espacios, sin salto de línea final, sin `\r`. Todos los valores
  son ASCII; no hay normalización Unicode.
- El HMAC se calcula **sobre el cuerpo exacto** (los mismos bytes que viajan),
  precedido del dominio; no se firma el token completo con el punto.
- La firma se compara en tiempo constante (`hmac.compare_digest`).
- El testigo **no** incluye contraseña, hash, usuario, sesión, SHA, ruta,
  nombre de clave ni texto libre. Añadir cualquiera de esos campos prohíbe
  emitir y obliga a una versión/dominio nuevos.

### 5.2 Campos

| Campo | Tipo exacto | Valor y restricciones |
|---|---|---|
| `v` | entero JSON, **no booleano** | Entero `1` exacto. Una versión nueva necesita dominio nuevo. |
| `accion` | cadena | Exactamente `"actualizar"`. Lista cerrada; cualquier otra cosa ⇒ inválida. |
| `id` | cadena | 32 hex minúsculas (`[0-9a-f]{32}`), CSPRNG, generado por la app tras `Reauth.OK`; ligado a la petición/operación (§8). |
| `creada` | entero JSON, no booleano | Instante Unix de emisión, `0 ≤ creada < 2^63`. |
| `expira` | entero JSON, no booleano | `creada + ttl`, con `1 ≤ ttl ≤ 300`; por defecto `ttl=60`. |
| firma | 64 hex | HMAC-SHA256 con dominio y clave dedicada. |

### 5.3 Límites

- `1 ≤ len(token) ≤ 2048` bytes; en la práctica el máximo del formato es muy
  inferior, pero 2048 es el tope duro de rechazo.
- Exactamente **un** punto separador; firma de exactamente 64 hex; cuerpo no
  vacío; JSON objeto; claves JSON sin duplicados.
- Conjunto de claves exactamente `{"v","accion","id","creada","expira"}`; ni
  una más ni una menos.
- `id` con `[0-9a-f]{32}`; mayúsculas, `../`, espacios o longitudes distintas
  ⇒ inválida.
- `creada`/`expira` enteros de 63 bits sin signo; `expira - creada` entre 1 y
  300; `ahora > expira` ⇒ caducada; `ahora < creada - 120` ⇒ inválida;
  `ahora` dentro de `[creada-120, expira]` ⇒ admisible en ventana.
- Rechazo de bytes extra (`\r`, `\n`, sufijos), token sobredimensionado,
  claves duplicadas, tipos erróneos y firma no hexadecimal.
- `id_esperado`: en la integración es **obligatorio** y debe ser el ID de la
  petición autenticada; si falta o no coincide ⇒ inválida y **sin consumo**.

### 5.4 Vector canónico de prueba

Con clave sintética `00 01 02 … 1f` (`bytes(range(32))`), `id` = `"a"`×32,
`creada` = 1800000000 y `ttl` = 60, el emisor produce exactamente:

```text
{"v":1,"accion":"actualizar","id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","creada":1800000000,"expira":1800000060}.287259e7d46eb92b66b513e17ca2ed2c58df21433110e210e0bc75c858aa441e
```

Longitud: 174 bytes. `verificar_autorizacion` con `ahora=1800000000`,
`id_esperado="a"×32` y un callback que reclame por primera vez debe devolver
`aceptada`; una segunda verificación debe devolver `repetida`. Este vector es
contrato: si el formato cambia, cambia versión y dominio, y el vector se
actualiza con justificación.

## 6. Composición obligatoria en la app

### 6.1 Secuencia normativa

La emisión de un testigo es **un único camino** que respeta este orden, sin
atajos y sin duplicarlo entre routers:

1. **Puerta de función.** Si la actualización no está habilitada (hoy), se
   responde `no_habilitada` **sin** reautenticar, leer la clave ni emitir. Hoy
   ni siquiera hay ruta; cuando exista, la puerta es lo primero.
2. **Validación manual del formulario.** Sesión y origen válidos; confirmación
   explícita (`entiendo is True`, nunca un GET); contraseña de tipo `str` y
   entre 1 y 512 bytes UTF-8, sin reflejarla en errores (evitar un 422 con el
   secreto). Fallo ⇒ código de validación, sin reautenticar.
3. **`auth_mode`.** `none` ⇒ `autenticacion_no_activada` (sin reautenticar).
   Solo `password` y `user_password` siguen; cualquier otro valor ⇒
   `no_disponible`.
4. **Reautenticación.** Llamar exactamente una vez a
   `services.reautenticacion.comprobar_contrasena_actual(contrasena, settings)`
   y mapear el resultado:
   - `Reauth.OK` ⇒ continuar.
   - `Reauth.INCORRECTA` ⇒ `contrasena_incorrecta`.
   - `Reauth.OCUPADA` ⇒ `ocupada`.
   - `Reauth.BLOQUEADA` ⇒ `bloqueada` (con `hasta_epoch` para el mensaje).
   - Excepción, resultado inesperado o distinto de `OK` ⇒ `no_disponible`.
   En todos los casos no-`OK`: **no se lee la clave, no se emite testigo y no
   se construye la petición**.
5. **Emisión (solo tras `OK`).** Generar el ID con CSPRNG
   (`secrets.token_hex(16)`), leer la clave dedicada (en hilo, sin seguir
   enlaces) y construir el testigo con `crear_autorizacion(clave=…, id_=…,
   ahora=int(time.time()), ttl=60)`. El mismo ID se usa en la petición v4 y en
   el testigo (§8).
6. **Envío único.** Construir una petición cerrada (sin contraseña) y enviarla
   **una vez** al host. Un fallo de transporte no autoriza reenvío con el mismo
   testigo ni emisión silenciosa de otro: se muestra resultado incierto y se
   reconcilia (§7.6).

### 6.2 Invariantes

- Sin `Reauth.OK` **nunca** hay testigo ni petición: la composición lo impone
  en un solo sitio y una prueba lo verifica con dobles para cada resultado
  (incluidas excepción y valor no esperado).
- La reautenticación fallida alimenta el contador global y el bloqueo
  compartidos de OPS3; este contrato no crea contadores paralelos ni los
  relaja.
- La contraseña se usa solo para reautenticar: no va al testigo, ni a la
  petición v4, ni a logs, estado, argv o entorno; se descarta al terminar.
- No hay emisión desde un GET, un sondeo de estado, `/estado` ni una página
  informativa. Solo un POST confirmado y reautenticado.
- El emisor puro (`crear_autorizacion`) no hace E/S ni red; la lectura de
  clave y el envío son del llamador. La prueba estática lo mantiene.
- Antes de integrar, el emisor y el futuro servicio de composición **no** se
  importan desde web, API, `main.py`, auxiliar ni instalador; la barrera de
  [test_ops4_aislamiento.py](../../tests/test_ops4_aislamiento.py) se mantiene
  y se amplía al servicio de composición cuando exista.
- Un testigo emitido y no enviado (fallo antes del envío) expira sin usarse y
  no se reutiliza; otro intento exige nueva confirmación, nueva
  reautenticación y nuevo ID.

## 7. Verificación en el host, consumo durable y namespace

### 7.1 Orden de verificación (parar en el primer fallo)

La integración futura verifica en este orden; **ningún paso posterior se
ejecuta si uno falla** y **el consumo no se toca hasta el último paso**:

1. **Puerta de función** deshabilitada ⇒ `no_habilitada`, sin consumo y sin
   efectos. Hoy es el resultado observable de cualquier intento.
2. Clave/reloj válidos ⇒ si no, `no_disponible`.
3. Tipo y tamaño del testigo (bytes, 1..2048) ⇒ `invalida`.
4. Exactamente un punto y firma de 64 hex ⇒ `invalida`.
5. HMAC con la clave dedicada y dominio, comparación en tiempo constante ⇒
   `invalida`.
6. JSON UTF-8 sin duplicados, objeto, conjunto exacto de claves ⇒ `invalida`.
7. `v`, `accion`, `id`, tipos y valores, `1 ≤ ttl ≤ 300` ⇒ `invalida`.
8. `id_esperado` obligatorio (ID de la petición autenticada) e igualdad ⇒ si
   falta o no coincide, `invalida` y **sin consumo**.
9. Ventana: `ahora > expira` ⇒ `caducada`; `ahora < creada - 120` ⇒ `invalida`.
10. **Consumo durable de un solo uso** ⇒ `aceptada` si reclama exactamente
    `True`; `repetida` si la marca ya existe o el callback no devuelve `True`;
    `no_disponible` si el callback lanza o el registro no es fiable.

Tras `aceptada`, el host **aún no ha autorizado nada por sí solo**: debe
validar instalación, rutas, cerrojo, estado y unidad y fijar `S` conforme a la
política de `main`; solo entonces ordena el efecto. La aceptación es de
admisión, no de ejecución.

### 7.2 Registro durable: requisitos

- **Ubicación persistente:** directorio propio, root:root `0700`, en el
  sistema de archivos persistente de la instalación (a fijar; **nunca**
  `/run`, que es tmpfs, ni el directorio `vistos` del auxiliar).
- **Marca:** crear `autorizacion-<id>` (o nombre con prefijo propio) con
  `O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC`, modo `0600`, contenido vacío (sin
  datos del testigo); anclar el descriptor del directorio entregado por un
  llamador de confianza; no aceptar rutas de la petición.
- **Durabilidad:** `fsync` del fichero y del directorio **antes** de devolver
  `True`. Solo entonces se considera consumido. Cualquier error ⇒ excepción
  ⇒ `no_disponible`, sin aceptar.
- **Existencia previa:** cualquier entrada con ese nombre (fichero, enlace,
  FIFO, directorio o marca incompleta) cuenta como **ya consumida** y no se
  sigue ni se borra.
- **Fallos:** no borrar una marca creada aunque falle la sincronización (su
  persistencia es incierta); no reintentar `close` tras error; no convertir un
  fallo en «libre».
- **Reapertura:** un proceso nuevo debe ver la marca y rechazar la repetición.
  Esto demuestra persistencia observable, **no** supervivencia a pérdida
  eléctrica ni a restauración de snapshot.

El registro experimental
[registro_repeticiones_ops4.py](../../deploy/ops/registro_repeticiones_ops4.py)
cubre esta mecánica (`reclamar_id`, `O_EXCL`, dos `fsync`, fallos inyectados),
pero está desconectado y **no se conecta en esta fase**. Al integrar se
extiende/adapta a este directorio y a este namespace, con pruebas de paridad.

### 7.3 Namespace distinto del registro v3

El auxiliar actual anota las peticiones v1/v2/v3 en
`/run/zascarr-ops/vistos/<id>` (`EstadoOps.marcar_visto`): tmpfs, purgado a
los 300 s por `purgar_vistos`, compartido por todas las versiones del
protocolo. Ese registro **no sirve** para la autorización:

- no es durable (un reinicio vacía `/run`),
- se purga, lo que reabriría la ventana de replay,
- y compartir el nombre permitiría que una marca de petición v3 satisficiera
  o robara el consumo de la autorización, mezclando dos autoridades distintas.

Requisitos:

1. **Directorio y función propios** para el consumo de autorizaciones; no se
   reutiliza `marcar_visto`, ni su directorio, ni su purga.
2. Aunque el valor del ID coincida con el de la petición (a propósito, §8),
   **las marcas viven en espacios distintos**: consumir en uno no crea ni
   consume en el otro, y `purgar_vistos` no toca las marcas de autorización.
3. Pruebas cruzadas: una petición v3 marcada como vista no da por consumida la
   autorización, y una autorización consumida no impide ni satisface la marca
   de la petición (ni al revés); borrar/purgar `vistos` no reabre un testigo.
4. La unidad futura que escriba este directorio debe incluir la ruta en
   `ReadWritePaths` (la unidad de actualización **no existe** hoy; el
   requisito es para cuando se cree, y no se toca ninguna unidad instalada).

### 7.4 Retención, cuota y poda

- **Por defecto, la marca es permanente** (como en el registro experimental),
  y un almacenamiento lleno **deniega** (`no_disponible`): fallar cerrado es
  preferible a reabrir replay.
- Poda solo si se decide una política y se prueba: **nunca** se poda una marca
  cuyo testigo pudiera seguir siendo aceptado. Con reloj de pared no basta:
  un reloj retrocedido podría resucitar un testigo ya caducado. Se exige un
  ancla monotónica fiable o no podar; la decisión y el margen (≥ 300 s + 2×120 s)
  están abiertos (§14).
- Debe existir una cuota/tope y un observable no sensible (recuento, no
  contenido) para que el operador sepa que el registro se llena. La
  implementación debe decidir cuota, formato y limpieza antes de conectar.

### 7.5 Antes de cualquier efecto

El consumo durable ocurre **antes** de `systemctl start`, del ejecutor o de
cualquier cambio de código, imagen, BD o estado. Si después falla otra guarda,
el intento queda consumido: no se repone el testigo ni se reintenta con el
mismo ID. Un nuevo intento exige nueva confirmación, nueva reautenticación y
nuevo ID.

### 7.6 Respuesta perdida o resultado incierto

- Si el envío pudo llegar al host y la respuesta se pierde, **no se relanza**
  ni se reenvía el testigo: el consumo pudo ocurrir y la operación pudo
  iniciarse.
- Se muestra «sin noticias»/resultado incierto y se reconcilia en el host
  (unidad, procesos, HEAD, imagen, BD) antes de permitir otro intento, según
  [ops4-especificacion-main.md](ops4-especificacion-main.md) §3, punto 8
  (observación y recuperación).
- El host no interpreta el estado informativo como autorización ni como
  ausencia de efectos.

## 8. Ligadura a ID de petición y operación

- **Un intento = un ID.** La app genera **un** identificador CSPRNG de 32 hex
  (`secrets.token_hex(16)`) **después** de `Reauth.OK`, y lo usa en la petición
  v4 y en el testigo. No se acepta un ID del formulario, de la URL, de la
  sesión ni de otro intento. No se reutiliza para otra acción ni para otro
  intento.
- **La operación va en el dominio.** `accion="actualizar"` y la versión fija,
  junto con el dominio `zascarr-ops4-autorizacion-v1`, ligan el testigo a
  esta única operación; otra acción necesita otro dominio/versión y no puede
  reutilizar esta firma.
- **El host liga contra la petición, no contra el testigo.** Al integrar,
  `verificar_autorizacion(..., id_esperado=<id de la petición parseada>)` es
  obligatorio; el ID que aparece dentro del testigo no se usa como autoridad.
  Una discrepancia se rechaza **sin consumo**.
- **Una sola petición autenticada.** El testigo debe viajar dentro de la misma
  petición cerrada que autentica el canal (HMAC con `ops.key`), parseada una
  sola vez; no se acepta un testigo por un segundo canal ni correlacionado por
  logs. El formato exacto del mensaje v4 y la retirada de la contraseña de la
  vía v3 quedan como decisión de transporte (§14), pero la regla es una sola
  petición, un solo parseo y una sola verificación.
- **Alternativa no adoptada:** un ID propio del testigo más un campo `solicitud`
  que repita el ID de la petición. Se descarta en esta versión porque exige un
  formato v2/dominio nuevo sin mejorar la ligadura real: el mismo ID ya une
  petición e intento, y el namespace separado (§7.3) impide que el consumo de
  una capa valga para la otra. Si en el futuro hace falta un `kid`, identidad de
  instalación o correlación explícita, se hará como formato v2 con su decisión
  (§14, Q-AUT-6).
- **El testigo no fija el SHA.** Autoriza «iniciar este intento», no «instalar
  este SHA». El host fija `S` tras la admisión, según la política de `main`; no
  se mezcla la autorización con la identidad del commit.
- **Instalación:** la clave única por instalación liga el testigo a esa
  instalación; si se necesita una ligadura explícita a build/identidad de
  instalación, será un formato v2 (decisión abierta, §14).

## 9. Códigos de respuesta

### 9.1 Códigos de la app (capa de composición)

Lista cerrada para el futuro servicio/endpoint; la UI futura los traducirá a
frases llanas (sin «token», códigos ni jerga; CLAUDE.md §6 y U20/A2). Mientras
la función esté deshabilitada no hay ruta que los produzca.

| Código | Cuándo | Efecto |
|---|---|---|
| `no_habilitada` | La función no está habilitada (hoy, siempre). | No reautentica, no lee clave, no emite. |
| `confirmacion_requerida` | Falta la confirmación explícita. | No reautentica, no emite. |
| `contrasena_invalida` | Tipo, longitud o UTF-8 inválidos. | No reautentica, no emite. |
| `autenticacion_no_activada` | `auth_mode=none`. | No reautentica, no emite. |
| `contrasena_incorrecta` | `Reauth.INCORRECTA`. | No emite; alimenta el bloqueo compartido. |
| `ocupada` | `Reauth.OCUPADA` (cola llena). | No emite. |
| `bloqueada` | `Reauth.BLOQUEADA` (con hora). | No emite. |
| `no_disponible` | Modo/key/reloj/reauth inesperados o fallo interno. | No emite; fallo cerrado. |
| `preparada` | Solo interno: testigo y petición listos para enviar. | No es éxito de actualización. |
| `aceptada` | El host admitió la petición (admisión, no ejecución). | Sin reintento; se sigue el estado del host. |
| `resultado_incierto` | Transporte/respuesta perdida o ambigua. | Sin reintento; reconciliación. |

Para una futura UI se propone reproducir el patrón de OPS2/OPS3: respuesta
`200` con fragmento HTML y mensaje en la zona viva; `403` para sesión/origen
inválidos; `404` si la ruta no existe (estado actual). No se usa `422`
automático con la contraseña (evita reflejar el secreto). Esto es una
recomendación para la fase de UI, no una implementación.

### 9.2 Códigos del host (lista cerrada, sin texto libre)

Se distinguen las dos capas para no confundir el rechazo de la petición con el
del testigo, sin revelar el testigo ni la clave:

| Capa | Código | Significado |
|---|---|---|
| Petición | `esquema_invalido`, `firma_invalida`, `caducada`, `repetida` | Contrato v1/v2/v3/v4 del canal; se conserva lo existente. |
| Función | `no_habilitada` | La acción `actualizar` no está habilitada; sin consumo y sin efecto. |
| Testigo | `autorizacion_invalida` | Formato, firma, dominio, campos, acción o ID no válidos. |
| Testigo | `autorizacion_caducada` | Fuera de la ventana por el lado tardío. |
| Testigo | `autorizacion_repetida` | Marca durable ya presente (consumido). |
| Testigo | `autorizacion_no_disponible` | Clave, reloj o registro no fiables; fallo cerrado. |
| Admisión | `aceptada` | Admisión correcta; **no** significa ejecutada. |
| Operación | `operacion_en_curso`, `bloqueo_temporal` | Guardas de frecuencia/cerrojo (OPS1/OPS2). |
| General | `no_disponible` | Fallo interno cerrado. |

Reglas:

- Hoy la puerta observable es el rechazo existente del auxiliar
  (`accion_no_disponible` para v1/v2 y rechazo de esquema para v3);
  `no_habilitada` es el código previsto para la ruta nueva cuando exista, no un
  cambio de la puerta actual. Mientras no se integre, la ruta nueva no existe.
- Códigos de lista cerrada; jamás texto libre, rutas, excepciones, clave,
  testigo, contraseña ni hash en la respuesta.
- El campo `id` solo se devuelve si el esquema de la petición era válido y de
  forma acotada; nunca el testigo.
- La paridad con `CODIGOS` del auxiliar y con
  [test_ops_paridad.py](../../tests/test_ops_paridad.py) se actualiza al
  integrar; v1/v2 conservan sus códigos y v3 sigue rechazado mientras no se
  retire explícitamente.
- `prueba_invalida` y `autenticacion_no_activada` **no forman parte de esta
  ruta** (el host no verifica contraseña aquí); no se añaden para «parecer
  compatible».

## 10. Criterios de aceptación verificables

Todos en entorno desechable, con observables binarios; un caso no ejecutado es
**NOT RUN**, nunca PASS. Un AC compuesto debe poder fallar por una sola causa.

| ID | Dado / Cuando / Entonces | Observable binario |
|---|---|---|
| **AC-AUT-01** | Dada la función deshabilitada, cuando se envía una petición directa o se invoca la ruta/auxiliar, entonces se rechaza con `no_habilitada`, sin consumo y sin `systemctl`. | Shim de unidad sin llamadas; registro sin marcas; UI sin acción. |
| **AC-AUT-02** | Dado cada resultado de reautenticación (`INCORRECTA`, `OCUPADA`, `BLOQUEADA`, excepción, valor no esperado) y `auth_mode=none`, cuando se intenta pedir, entonces no se emite testigo ni se lee la clave. | Emisor falso sin llamadas; lectura de clave falsa sin llamadas; código mapeado. |
| **AC-AUT-03** | Dado `Reauth.OK`, cuando se pide, entonces se emite exactamente un testigo con el vector/estructura esperada, con ID CSPRNG de 32 hex y `ttl` por defecto 60. | Testigo válido; longitud/formato; ID distinto por intento. |
| **AC-AUT-04** | Dado el vector canónico (§5.4), cuando se verifica con `id_esperado` correcto, entonces `aceptada` una vez y `repetida` la segunda. | Códigos; marca creada una vez. |
| **AC-AUT-05** | Dado cualquier testigo inválido (forma, punto, firma, dominio, acción, versión, ID, tipo booleano, campo extra, duplicado, sobredimensionado, clave distinta), cuando se verifica, entonces se rechaza y **el callback de consumo se llama cero veces**. | Contador del callback = 0; directorio de marcas sin cambios; `inválida`/`caducada`/`no_disponible` solo según la causa. |
| **AC-AUT-06** | Dado un testigo válido y N procesos/hilos (N≥2), cuando verifican a la vez con el registro real, entonces exactamente uno obtiene `aceptada` y el resto `repetida`. | `count(aceptada)==1`; marcas correctas; sin excepción. |
| **AC-AUT-07** | Dada la marca de petición v3 en `vistos/<id>` (o su purga), cuando se verifica la autorización con el mismo ID, entonces su consumo es independiente; y al revés. | Consumo cruzado no se satisface; purga de `vistos` no reabre el testigo. |
| **AC-AUT-08** | Dado un fallo de `fsync`/creación/descriptor o un almacenamiento lleno (inyectado), cuando se intenta consumir, entonces `no_disponible`, sin aceptar, sin efecto y sin borrar la marca. | Código; fichero existente/ausente esperado; sin unidad. |
| **AC-AUT-09** | Dada una marca consumida, cuando un proceso nuevo reabre el registro y verifica el mismo testigo, entonces `repetida`; y un directorio de marcas en `/run` no se usa. | Repetición tras reapertura; ruta persistente. |
| **AC-AUT-10** | Dado el testigo canónico y mutaciones de cada campo, cuando se verifica, entonces rechazo y `sin consumo`; el vector válido se acepta. | Tabla de mutaciones; callback controlado. |
| **AC-AUT-11** | Dado un testigo firmado con `ops.key` o con clave de longitud distinta, cuando se verifica, entonces `no_disponible`/`inválida`; la clave no es `ops.key`. | Rechazo; no hay lectura de `ops.key` por el emisor de autorización. |
| **AC-AUT-12** | Dado el testigo y su verificación, cuando se inspeccionan token, logs, estado y respuesta, entonces no aparecen contraseña, hash, usuario, SHA, clave ni testigo. | Búsquedas negativas en observables. |
| **AC-AUT-13** | Dado un `id_esperado` distinto o ausente en la integración, cuando se verifica, entonces `invalida` y **sin consumo**; con coincidencia, aceptación. | Código; contador del callback; marcas. |
| **AC-AUT-14** | Dado el árbol `55baba87` o posterior mientras no se habilite, cuando se inspeccionan UI/auxiliar/`main.py`/unidad/instalador, entonces no hay formulario, `hx-*`, script, onclick, ruta POST, import del emisor/verificador, `actualizar` en `UNIDADES`, unidad de actualización ni `update.sh` ejecutado. | Pruebas estáticas/HTML; `UNIDADES`; ficheros de unidad; historial de instalación. |
| **AC-AUT-15** | Dado un testigo aceptado pero con cerrojo ocupado, unidad ocupada o instalación no válida, cuando se intenta, entonces no hay efecto y el estado ajeno no se pisa; la aceptación no sustituye las guardas. | Shim de unidad; estado intacto. |
| **AC-AUT-16** | Dado un envío con respuesta perdida/ambigua, cuando la app no puede saber si llegó, entonces no reenvía el testigo ni genera otro para el mismo intento; muestra incierto. | Un solo intento emitido; estado incierto; sin segundo `start`. |
| **AC-AUT-17** | Dada una composición con dobles, cuando se prueba cada paso, entonces el orden es `puerta → validación → auth_mode → reauth → clave → emisión → envío`; ningún resultado no-OK llega a clave/emisión. | Orden de llamadas; dobles que fallan si se llaman. |
| **AC-AUT-18** | Dada una clave ausente, enlace, tamaño/modo incorrecto o directorio inseguro, cuando se intenta emitir/consumir, entonces fallo cerrado sin emisión/aceptación. | Códigos; sin ficheros creados fuera; tests con directorios sintéticos. |
| **AC-AUT-19** | Dadas respuestas y códigos del host, cuando se recorre la lista cerrada, entonces todo código pertenece a la lista, no hay texto libre y la paridad v1/v2 se conserva. | Enum/tupla cerrada; prueba de paridad. |

## 11. Requisitos de pruebas

### 11.1 Casos obligatorios

- **No llamada al callback en rechazo:** para cada causa de rechazo
  (deshabilitada, clave/reloj inválidos, forma, firma, dominio, versión,
  acción, campos, tipos, duplicados, tamaño, ID, ventana, `id_esperado`), el
  contador de consumo debe quedar a cero; el testigo inválido no crea marcas y
  no llama a `systemctl`/ejecutor.
- **No emisión sin `Reauth.OK`:** dobles para `INCORRECTA`, `OCUPADA`,
  `BLOQUEADA`, excepción, `None` y valor no esperado; la emisión/lectura de
  clave no se ejecuta. Además `auth_mode=none` no debe ni reautenticar.
- **Formato:** vector canónico, mutación de cada byte/campo, dominio ajeno,
  firma de `ops.key`, clave de 31/33 bytes, booleano donde se exige entero,
  mayúsculas/`../` en el ID, `ttl` 0/301, `creada` negativa, token 2049,
  sufijos `\r`/`\n`, claves JSON duplicadas y campos extra.
- **Consumo durable real:** directorio temporal en el **mismo filesystem que
  `/`** (basetemp del proyecto), `O_EXCL`, dos `fsync`, fallos inyectados en
  fichero/`fsync`/directorio, descriptor inválido, disco lleno simulado,
  entradas previas de tipo enlace/FIFO/directorio/marca incompleta,
  reapertura desde otro proceso y concurrencia real con **procesos**
  (`multiprocessing`), no solo hilos.
- **Namespace:** consumir autorización no crea marca en `vistos`; marcar
  `vistos` no satisface la autorización; `purgar_vistos` no toca la marca
  durable; el directorio durable no está en `/run`.
- **Composición:** orden y códigos de la app; el mismo ID en petición y
  testigo; un fallo de transporte no reemite; ninguna llamada en GET/estado.
- **Aislamiento y deshabilitación:** `test_ops4_aislamiento.py` sigue
  prohibiendo imports desde web/API/`main.py`/auxiliar/instalador; la UI de
  Estado conserva un único botón `disabled`, sin `form`, `hx-*`, `script`,
  enlace ni POST; `actualizar` sigue fuera de `UNIDADES`; no existe unidad de
  actualización; `update.sh` no se instala ni se ejecuta.
- **Paridad:** v1/v2 sin cambios; v3 sigue rechazado; los códigos nuevos no
  rompen los existentes.
- **Secretos:** búsquedas negativas de contraseña, hash, clave y testigo en
  token, logs, estado, respuestas y argv; el testigo no contiene
  `prueba`/`password`/`pbkdf2`.
- **Unidad/host:** los casos de unidad/systemd/Docker/root quedan **NOT RUN**
  hasta el arnés aislado; no se sustituyen por dobles como si fueran PASS.

### 11.2 Cómo ejecutar en este árbol (fase de implementación)

```bash
cd /mnt/Datos/Documentos/Repos/zascarr/.worktrees/ops4-443
PYTHONPATH=.:src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest \
  tests/test_ops4_autorizacion.py tests/test_ops4_aislamiento.py \
  tests/test_ops4_ui_deshabilitada.py tests/test_ops4_registro_repeticiones.py -q
/mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/ruff check \
  deploy/ops/verificador_autorizacion_ops4.py \
  src/zascarr/services/autorizacion_actualizacion.py \
  tests/test_ops4_autorizacion.py tests/test_ops4_aislamiento.py
```

El árbol declara **710 pruebas OPS4/paridad verdes** y una suite completa previa
verde; esta fase es solo documentación y no repite la suite. En la fase de
integración sí se exige la suite completa y el Ruff del cambio, además del
arnés de host aislado. No se añaden dependencias (stdlib: `hmac`, `hashlib`,
`json`, `secrets`, `os`, `stat`).

### 11.3 Fuera de pytest (NOT RUN)

Pi, Docker de producción, systemd instalado, root, socket de producción,
`update.sh`, cortes eléctricos, restauración de host y extremo a extremo. La
evidencia de [verificacion-OPS4-host-2026-11-20.md](verificacion-OPS4-host-2026-11-20.md)
y de [ops4-diseno-ejecutor-vm.md](ops4-diseno-ejecutor-vm.md) es de la puerta
actual, no de esta ruta.

## 12. UI deshabilitada, ausencia de unidad/auxiliar y puerta

### 12.1 Estado que debe conservarse

En `55baba87` y mientras no haya autorización explícita:

- **UI:** `estado.html` mantiene la sección «Actualizar ZascArr» con un único
  botón `disabled`, sin `form`, `hx-*`, `script`, enlace, `onclick` ni ruta
  POST; el texto sigue diciendo que no está disponible y que no se instalará
  nada. Lo comprueba [test_ops4_ui_deshabilitada.py](../../tests/test_ops4_ui_deshabilitada.py).
- **Auxiliar:** `UNIDADES` solo contiene `copia` y `restaurar`; `actualizar` se
  rechaza en v1/v2; v3 está rechazado; no se añade la acción.
- **Aislamiento:** emisor y verificador no se importan desde web, API,
  `main.py`, auxiliar ni `instalar_ops.sh`; el emisor no hace E/S.
- **Unidad e instalador:** no existe unidad de actualización; `update.sh` no se
  instala, no se ejecuta y no se conecta; `deploy/systemd/**` y
  `scripts/instalar_ops.sh` no cambian para esta ruta.
- **Datos reales:** no se leen `.env`, BD, backups ni biblioteca de producción;
  no se toca el socket real.

### 12.2 Qué no puede hacer esta fase

No se edita código, UI, auxiliar, unidades, instalador ni la SPEC histórica;
no se commit ni push; no se toca la Pi; no se instala ni ejecuta `update.sh`;
la función no se conecta ni se habilita.

### 12.3 Puerta de habilitación (explícita y separada)

Antes de habilitar harán falta, como mínimo, **todas** estas condiciones; no se
deducen de esta SPEC:

1. Clave dedicada provisionada, con permisos y rotación probados (§4).
2. Composición implementada y probada con reautenticación real y cada
   resultado no-OK (§6, AC-AUT-02/17).
3. Consumo durable conectado, con namespace propio, retención/cuota decididas
   y pruebas entre procesos/reinicios (§7, AC-AUT-06/07/08/09).
4. Transporte cerrado decidido (v4 o equivalente), contraseña retirada de la
   vía v3 y un solo protocolo vivo (§14); retirada/desactivación de v3 con la
   prueba de rechazo correspondiente.
5. Arnés de host aislado (root/systemd/Docker/Postgres desechables) para los
   casos que pytest no puede cubrir; nada de Pi ni producción.
6. Revisión SecOps del **SHA final** (CLAUDE.md §5.8, por tocar la exigencia de
   la contraseña actual) y revisión QA/operativa.
7. Suite completa verde, incluida paridad v1/v2 y la cobertura nueva.
8. Corrección o anotación expresa de los documentos que contradicen la
   decisión (§13), y ADR (ampliación de 0021 o nuevo).
9. Autorización explícita del PO para habilitar, separada de esta SPEC y de la
   aprobación del benchmark. Solo entonces se podría plantear UI, unidad e
   instalación.

## 13. Contradicciones documentales con la decisión vigente

Se señalan aquí y **no se editan** en esta fase (la SPEC histórica se conserva;
los documentos se corrigen en el cambio de integración).

| Documento y línea | Qué dice | Relación con la decisión |
|---|---|---|
| [especificacion-BL-OPS4.md](especificacion-BL-OPS4.md) §2.4 (línea 22) | El auxiliar hace una **segunda comprobación independiente** de la contraseña contra `auth_mode` y `auth_password_hash` con PBKDF2. | **Contradice** la decisión del 2026-11-20: en esta ruta el host **no** lee el hash ni recibe la contraseña. Queda superado; no es autoridad para OPS4. |
| [especificacion-BL-OPS4.md](especificacion-BL-OPS4.md) FR-03/FR-04 (líneas 39-40) | La petición nueva al auxiliar incluye `contraseña` firmada. | **Contradice**: la vía nueva no envía contraseña; el testigo la sustituye y v3 con contraseña no se habilita. |
| [especificacion-BL-OPS4.md](especificacion-BL-OPS4.md) AC-04/AC-05 (líneas 70-71) | Escenarios basados en rechazo por contraseña/hash y en la aprobación root `A`. | Superados por la decisión (autoridad de la app) y por la política de `main` sin aprobación por SHA. |
| [especificacion-BL-OPS4.md](especificacion-BL-OPS4.md) §§2-7 (C-12) | Aprobación root `A` por SHA, 24 h, un uso, P/allowlist, migraciones bloqueadas. | Política retirada para esta vía; se conserva como histórico. La SPEC nueva no la reintroduce. |
| [ops4-especificacion-main.md](ops4-especificacion-main.md) §3.2 (línea 22) | «Autenticación viva»: el auxiliar verifica independientemente la contraseña contra la BD; «no acepta un booleano de la app». | **Contradice** la decisión y el benchmark ya lo señaló (`:22`). Debe corregirse antes de habilitar. |
| [ops4-especificacion-main.md](ops4-especificacion-main.md) AC-03 (línea 59) | «HMAC válido sin contraseña correcta no inicia». | **Contradice**: en esta ruta el host no recibe contraseña; la prueba es el testigo. |
| [ops4-alternativa-actualizador-manual.md](ops4-alternativa-actualizador-manual.md) (línea 11) | «el auxiliar del host comprueba de nuevo la contraseña viva». | **Contradice** la decisión; descripción previa. |
| [ops4-verificacion-contrasena.md](ops4-verificacion-contrasena.md) | Límites del verificador PBKDF2 del host. | No es contradicción de formato, pero **no aplica como autoridad** a esta ruta; sí a OPS2 y a la vía v3 rechazada. |
| [ops4-matriz-evidencia.md](ops4-matriz-evidencia.md) línea 37 | Dice «33 pruebas» de autorización; la ficha y el benchmark cuentan 38 (`--collect-only`). | Dato desactualizado; corregir antes de habilitar. No invalida el contrato, pero no debe usarse como recuento. |
| [ops4-matriz-evidencia.md](ops4-matriz-evidencia.md) línea 33 y [ops4-registro-repeticiones.md](ops4-registro-repeticiones.md) | v3 con contraseña en claro por canal local. | Coherente con v3 actual, **incompatible** con esta ruta: v3 no se habilita; el transporte nuevo no lleva contraseña (§14). |
| [ops4-autorizacion-app-host.md](ops4-autorizacion-app-host.md) | Ficha de decisión; dice «probablemente nueva versión de protocolo» y deja pendientes 1-6. | No contradice; esta SPEC concreta los pendientes. El transporte sigue siendo decisión abierta. |

La SPEC histórica conserva su valor de análisis; **no** se reescribe. Los
cambios de contrato de la vía nueva deben quedar reflejados en los documentos
de política (`ops4-especificacion-main.md`) en el mismo cambio que integre y
antes de habilitar.

## 14. Riesgos abiertos y preguntas que requieren decisión

### 14.1 Riesgos abiertos

1. **Clave legible por el grupo:** si no se consigue un grupo dedicado, otros
   procesos del grupo pueden forjar testigos. Mitigación parcial: permisos
   mínimos, rotación y guardas del host; el riesgo no desaparece.
2. **App/clave comprometidas:** el testigo no distingue una emisión legítima de
   una forzada. Es el coste aceptado de confiar en la app; el host no puede
   resolverlo con este contrato.
3. **Replay tras restauración de host:** un snapshot completo puede devolver
   marcas consumidas a «no consumidas» o borrar las nuevas. La ventana es de
   minutos (TTL ≤ 300 s + tolerancia), pero no nula; la política operativa
   (prohibir restauraciones con intento vivo, época, ancla externa) está
   abierta.
4. **Reloj:** sin NTP o con reloj retrocedido, la ventana y la retención se
   degradan. `fsync` y marcas duraderas no arreglan el reloj. Se necesita
   detección de reloj inválido/retroceso y fallo cerrado.
5. **Retención/poda:** marcas permanentes pueden llenar el disco; podar por
   reloj de pared puede reabrir replay. Sin ancla monotónica no hay poda
   segura.
6. **Dos protocolos vivos:** mantener v3 con contraseña y la vía nueva a la vez
   duplica superficie y confunde autoridad; hay que retirar/desactivar v3 en
   la misma integración (no en esta fase).
7. **Durabilidad no demostrada:** no hay evidencia de pérdida eléctrica,
   hardware que mienta, ni Pi. Los tres cortes de VM son evidencia acotada.
8. **Contadores compartidos:** la reautenticación usa estado en memoria de un
   solo proceso; un reinicio lo pone a cero. No es una defensa persistente.
9. **Emisión repetida no usada:** la app puede emitir varios testigos válidos
   no consumidos (cada uno con su ID); el host los aceptaría uno a uno. Los
   límites de frecuencia del auxiliar acotan el efecto, pero la emisión no
   tiene tope propio. Decidir si hace falta.
10. **Códigos nuevos y paridad:** añadir códigos sin romper v1/v2 ni la lista
    cerrada exige actualizar paridad y pruebas; un código ambiguo puede
    filtrar información o confundir al operador.
11. **Transporte no decidido:** el mensaje que lleva el testigo no tiene forma
    congelada; si se improvisa, se pierde el binding de una sola petición.

### 14.2 Preguntas que requieren decisión (con dueño propuesto)

| # | Pregunta | Bloquea | Dueño propuesto |
|---|---|---|---|
| Q-AUT-1 | Ruta, nombre y grupo de la clave; ¿grupo dedicado? ¿Cambio de `docker-compose.yml`/volumen? ¿Quién la instala y con qué procedimiento? | Integración | PO + operación |
| Q-AUT-2 | Transporte: ¿versión v4 nueva o extensión de v3? ¿Se retira el campo `prueba`/la vía v3? ¿Se conserva v1/v2 intacto? | Integración | Arquitectura + SecOps |
| Q-AUT-3 | TTL: ¿60 s basta? ¿Se admite 300? ¿Se exige reloj fiable/NTP y qué se hace si no? | Ventana y pruebas | PO + operación |
| Q-AUT-4 | Retención/cuota/poda de marcas: ¿permanentes con cuota? ¿Ancla monotónica? ¿Qué observable de capacidad? | Consumo durable | Arquitectura + operación |
| Q-AUT-5 | ¿Se adopta época/fencing de [ops4-propuesta-epoca.md](ops4-propuesta-epoca.md) o se descarta expresamente? | Reinicio/restauración | Arquitectura |
| Q-AUT-6 | ¿Hace falta ligar el testigo a identidad de instalación/build (formato v2), o basta la clave única por instalación? | Formato | Arquitectura |
| Q-AUT-7 | ¿`id_esperado` pasa a obligatorio en la función aislada o solo en la integración? | API | Arquitectura |
| Q-AUT-8 | ¿Tope de emisiones por sesión/intento y relación con los límites de frecuencia del host? | Abuso/DoS | PO + SecOps |
| Q-AUT-9 | UX futura: confirmación, textos, qué se dice de migraciones/interrupción/sin rollback; cómo se evita el 422 con secreto. | Habilitación UI | PO + UX |
| Q-AUT-10 | ¿Quién corrige `ops4-especificacion-main.md` §3.2/AC-03, la matriz y las referencias cruzadas, y en qué cambio? | Habilitación | Documentación + PO |
| Q-AUT-11 | Arnés de host aislado (root/systemd/Docker/Postgres/VM) y ventana de pruebas; SecOps del SHA final. | Habilitación | QA + SecOps |
| Q-AUT-12 | ¿Se elimina el código v3 con contraseña o se deja rechazado para siempre? | Superficie | Arquitectura |

## 15. Evidencia, NOT RUN y vigencia

- **Base:** `55baba87` (2026-11-20). Documentos y código leídos según §1; no se
  modificó código, UI, auxiliar, unidad, instalador ni la SPEC histórica.
- **Fase:** solo documentación (esta SPEC). No se ejecutó la actualización, ni
  el auxiliar, ni el socket, ni `update.sh`; no se usó la Pi, Docker de
  producción, systemd instalado ni datos reales. No se repitió la suite
  completa: el árbol declara 710 pruebas OPS4/paridad verdes y una suite
  completa previa verde; esta fase no cambia comportamiento.
- **Vector canónico:** calculado con el entorno de pruebas del proyecto a
  partir del emisor real (`crear_autorizacion`) para que la SPEC sea
  comprobable; no acredita la integración.
- **NOT RUN:** provisión de clave, composición real, transporte, consumo
  durable conectado, namespace en producción, arnés de host, root/systemd,
  Docker/Postgres, reinicios/cortes, restauración de host, Pi y habilitación.
- **Caducidad:** 2027-01-19 (~60 días), o antes si cambia la decisión, el
  formato del testigo, la clave o el transporte. Al integrar, esta SPEC se
  actualiza con las decisiones de §14 y con la evidencia de aceptación; no se
  considera aprobada por el mero hecho de existir.
