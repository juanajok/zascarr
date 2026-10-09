# ADR 0008: Catalogación explícita, vinculación en sitio y propuestas sin ejecución silenciosa

- Estado: **Propuesto** · 2026-10-09 (documento pendiente de revisión; **no está aceptado hasta que se fusione**)
- Relacionado: ADR-0006 (asignación recuperable), ADR-0007 (vincular en su sitio), `docs/design/rebanada-2-elegir-serie-y-vincular.md`, [`inventario-entradas-heredadas-y-alias-2026-10-09.md`](../design/inventario-entradas-heredadas-y-alias-2026-10-09.md), [`cruce-tablero-prs-2026-10-09.md`](../design/cruce-tablero-prs-2026-10-09.md)
- Tarjetas del tablero que toca: #115 (M2-US01), #114 y #112-#113 (M1), #131 y #132 (M7)

## Qué está decidido, qué es papel y qué falta

| Plano | Estado |
|---|---|
| **Decisiones** de los tres apartados de abajo | Acordadas con quien revisa el proyecto el 2026-10-09 |
| **Este documento** | Propuesto: pendiente de revisión explícita antes de fusionarse |
| **Implementación** de cualquiera de ellas | **Pendiente en todos los casos.** Nada de lo descrito como «objetivo» existe todavía |

Lo que sí existe en `main` (#97, #101, #103) son los servicios de alta, vista previa y vinculación
en sitio, sin interfaz. El estado exacto de cada entrada está en el inventario, anclado a un SHA.

## Contexto

El ADR 0007 separó «vincular en su sitio» de «organizar» y dejó dicho que el botón de «Por revisar»
tenía que cambiar. Tras implementar el alta, la vista previa y la vinculación, el cruce del tablero
(#136) y el inventario de este mismo cambio muestran tres hechos que no estaban decididos:

1. **Los tokens de candidata y alta tienen un límite sin calcular.** `api/revision.py` limita a 8.000
   caracteres el campo `candidata` y el `token` de alta. El de vinculación sí tiene un máximo
   calculado en el peor caso (`MAX_TOKEN_VINCULACION`, #103). Se ha estimado que un texto largo con
   caracteres de 4 bytes podría superar los 8.000 siendo legítimo, **pero esa estimación no está
   acreditada**: no se recalculó con el serializador y el firmador reales ni la cubre ninguna
   prueba, y no debe usarse para fijar ningún límite (ver «Estimaciones anteriores»).
2. **Dos entradas heredadas no pasan por los servicios nuevos** (inventario E1-E3, C1-C3):
   el botón de «Por revisar» llama a `AsignacionService.asignar`, que mueve y renombra, y
   «Crear serie» de Descubrir crea la serie con datos aportados por el cliente, sin las garantías del
   alta. Una tercera, `POST /api/series` (C3), no se había contado.
3. **El alias local (B13) se aprende y se aplica sin preguntar.** Se aprende al confirmar una
   asignación desde «Por revisar» (A1) y lo aplican, sin intervención, el importador (A3) y el
   filtro de candidatos del orquestador (A4). La vinculación en sitio no lo aprende y hay pruebas que
   lo fijan (A5).

## Decisión

**Política común:** *catalogación explícita, vinculación en sitio y reutilización de propuestas sin
ejecución silenciosa.* Reutilizar lo ya probado; separar un defecto nuevo del trabajo cerrado; que
ninguna acción de catalogar mueva archivos ni asigne sin que la persona lo haya visto y confirmado.

### 1. Tokens de candidata y alta

- **#115 queda acotada a la vinculación** («cubierta para vinculación»). No se amplía ni se cierra
  como garantía de todos los tokens.
- El desajuste se corrige **por separado**, en una PR propia que requiere su propia autorización.
- Los máximos se **calcularán**, no se elegirán: con `crear_token`, los esquemas Pydantic y la
  codificación reales (JSON con `ensure_ascii=False`, base64 URL-safe, firma `.hex` de HMAC-SHA256),
  distinguiendo cuatro magnitudes: longitud de los campos originales, del JSON serializado, del token
  firmado y del cuerpo HTTP. Se calcularán límites independientes para candidata y alta.
- **Contrato:** toda candidata o alta válida que el productor pueda emitir debe poder recorrer su
  cadena de consumidores sin ser rechazada únicamente por un límite de tamaño incompatible.
- **No se cambia** el formato, la firma ni el máximo del token de vinculación.
- Criterios de aceptación de esa corrección (aún sin escribir): ASCII máximo y Unicode con expansión
  máxima admitida; comillas, barras y escapes; campos opcionales y contexto en sus máximos; recorrido
  simulado descubrimiento → candidata → vista previa de alta → token de alta → confirmación; máximo
  válido aceptado y exceso rechazado **sin efectos**; firma, propósito, caducidad y validación
  conservados. No exige consultas a fuentes reales.
- **Prioridad:** corregirla o justificar los límites **antes de aceptar** el asistente completo (2e);
  no impide diseñar su interfaz.

### 2. Entradas heredadas

- **«Añadir al catálogo» / «Crear serie»** crea o reutiliza mediante el **contrato del alta** (vista
  previa y confirmación). Se adapta la entrada de Descubrir (C1); no se renombra como «Organizar»,
  porque no mueve nada: el defecto es que evita las garantías del servicio.
- **«Vincular»** relaciona el archivo con el catálogo **sin moverlo ni renombrarlo**, con el servicio
  de #103. Sustituye a la asignación que mueve en el recorrido normal de «Por revisar» (E1-E3).
- **«Organizar»** es una operación física distinta, con alcance y consentimiento propios. Sigue fuera
  de esta entrega y no se mezcla con el recorrido de adopción en sitio.
- La separación debe existir **en el texto de la interfaz y en la ejecución**: una confirmación debe
  mostrar los efectos de la operación que se autoriza, y no dar a entender que se cataloga cuando se
  moverían archivos.
- **Qué no se decide aquí:** retirar `AsignacionService` (sigue siendo «Organizar», ADR 0007),
  retirar `ReviewService.assign_to_series` (sin llamadores en `src/`), ni qué hacer con
  `POST /api/series` (C3). Cualquier retirada espera al inventario completo.
- **Mientras dure la transición:** no anunciar como segura una acción que aún mueve archivos; no
  añadir rutas nuevas que eludan los servicios aprobados; documentar cada excepción heredada.

### 3. Alias

- **En el flujo nuevo, un alias o regla aporta *evidencia* para una propuesta, no *permiso* para
  ejecutar.** Una coincidencia puede explicar una candidata, pero no puede marcar archivos, confirmar
  una serie, vincular ni mover contenido por sí sola.
- La propuesta debe mostrar la publicación sugerida, la regla que la produjo, su alcance y las
  señales contradictorias. La persona selecciona y confirma.
- **Confirmar una vinculación no crea un alias** y el asistente no aprende reglas automáticas sin un
  consentimiento específico. (Hoy ya se cumple para la vinculación; ver A5.)
- **No se modifica B13 globalmente** en esta entrega: el importador (A3) y el orquestador (A4) siguen
  igual. Los alias existentes no se borran, no se reinterpretan, no amplían su alcance y no provocan
  reclasificación retrospectiva de archivos.
- La gestión completa (listar, delimitar, desactivar, y habilitar explícitamente reglas
  automáticas) pertenece a M7 y no se implementa aquí.

## Alternativas consideradas

| Alternativa | Por qué no |
|---|---|
| Ampliar #115 a todos los tokens | Mezcla una garantía ya implementada y probada con un defecto de otros productores y consumidores |
| Subir 8.000 a un número «grande» | Un número sin cálculo repite el defecto; el máximo debe salir del esquema real |
| Renombrar ambas entradas heredadas como «Organizar» | La creación desde Descubrir no mueve archivos: el problema es otro |
| Borrar `AsignacionService` y sus rutas ya | Hay consumidores no inventariados (p. ej. la medición, E8) y «Organizar» lo necesita |
| Que el alias ejecute en el flujo nuevo | Reutilizaría un consentimiento anterior para una operación distinta |
| Modificar B13 de golpe | Alteraría importaciones existentes sin medir el efecto |

## Consecuencias

- **Positivas:** el asistente no ofrece una candidata legítima para fallar después por un límite; no
  se mueven archivos adoptados sin pedirlo; cada alta pasa por un único contrato con comprobante y
  deshacer.
- **Coste, anotado a propósito:** si «Por revisar» deja de asignar con `AsignacionService`, **ningún
  camino de usuario aprenderá alias nuevos** (el único productor es A1). Los existentes siguen
  funcionando, pero el «arranque en frío» que describe el orquestador deja de tener productor hasta
  que M7-US02 declare reglas explícitas. Esto no es una regresión que esta entrega introduzca (no
  implementa nada), pero **debe decidirse cuándo se sustituya el botón**.
- La paridad entre lo que muestra la vista previa y lo que ejecuta la confirmación pasa a ser un
  criterio de aceptación de la interfaz, no solo del servicio.
- M1-US01 y M1-US02 seguirán «parciales» hasta aportar evidencia desde las entradas reales del
  navegador (nombre, ruta y contenido conservados; colisiones mostradas, no resueltas en silencio;
  ausencia de una alternativa visible que las eluda).

## Dependencias

- La corrección de tokens y el contrato de 2e requieren **autorizaciones separadas**.
- La interfaz (2e) depende de la corrección de tokens para *aceptarse*, no para diseñarse.
- M7 (gestión de reglas) depende de decidir qué sustituye a A1 como productor de alias.

## Exclusiones

Esta propuesta **no** autoriza ni describe como hecho: código, pruebas nuevas, migraciones ni cambios
de configuración; 2e; aplicar 0018/0019 en producción; consultas a fuentes reales; despliegue;
cambios de parser; organizar/reubicar; cambios en el tablero o en las issues; cerrar #115-#117.

## Estimaciones anteriores no acreditadas

Las cifras **4.625 / 5.889** (ASCII máximo) y **14.625 / 15.889** (caracteres de 4 bytes) citadas
para los tokens de candidata y alta salen de un análisis previo que **no se recalculó** con
`crear_token` ni está cubierto por ninguna prueba del repositorio. Se conservan aquí solo para
identificarlas; **no son máximos demostrados** ni deben usarse para fijar límites nuevos. Este ADR
establece *cómo* se calcularán, no su resultado.
