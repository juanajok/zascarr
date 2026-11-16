# Plan de refinamiento de #126 (MIT-M5-US03): migración de identidad editorial

> **Estado: PROPUESTA DE REFINAMIENTO. No aprueba, no autoriza y no ejecuta ninguna migración.**
> Este documento no crea tablas, no modifica datos, no toca la Pi, no abre archivos y no lanza
> ningún censo. Solo ordena la decisión que falta y el trabajo futuro.
>
> **Base de código:** `origin/main` `19372164` (2026-11-16). **Producción:** `19372164`,
> esquema `0045`. **Fuente de evidencia:** censo de #181 ejecutado el 2026-11-04 con esquema `0020`
> (no repetido aquí) y diseño de #184. Las cifras del censo son las de esa fecha, no una medición
> del catálogo actual.

## 1. Por qué #126 no es una historia implementable hoy

#126 nació como una historia 13/XL para «migrar sin confundir recuentos». Sus dos hijas de
evidencia y diseño ya existen:

| Pieza | Estado | Qué aporta |
|---|---|---|
| #181 censo | Ejecutado, solo lectura | 443 `Issue`, 20 series; 0 colisiones, 0 recopilaciones, 0 `covered_issue_ids`; 897 archivos sin `Issue` sin caracterizar |
| #184 diseño | Documento propuesto, no aprobado | Modelo aditivo condicionado a disparadores; recomienda **no migrar ahora** |
| #182 discriminantes | Cerrado | Cómo distinguir publicaciones sin inventar datos |
| #183 elección | Cerrado | Elección manual en JSONB, sin cambiar esquema |
| #124/ADR 0003 | Cerrado con decisiones diferidas | Vocabulario y modelo mínimo; la migración no está autorizada |

El estado real del esquema lo confirma: **no hay `editions` ni `edition_id`**, `Issue.number_key`
existe como clave calculada dentro de la serie, `Issue.volume` sigue siendo legado y
`File.covered_issue_ids` se escribe vacío y nadie lo lee. No hay materia medida que exija separar
ediciones hoy.

## 2. Recomendación de recorte

**Recomendación: cerrar #126 aceptando que el entregable es censo + diseño + decisión de posponer
la migración, no una migración ejecutada.** La migración solo se reabre si se cumple un disparador
medible; no se convierte en deuda implícita ni en un «ya veremos».

Esta recomendación no cierra #108 por sí sola: #108 es la feature padre y debe registrar el mismo
recorte antes de cerrarse. Tampoco cambia el estado de #126 sin decisión del PO.

### Lo que NO se hace con este recorte

- No se crea el modelo `editions`.
- No se cambia `Issue.number_key`, `Issue.volume` ni `File.covered_issue_ids`.
- No se migran datos ni se tocan rutas, vínculos, procedencia o recuentos.
- No se caracterizan los 897 archivos sin `Issue` (queda como fase opcional F1).

## 3. Trabajo futuro troceado

| Fase | Entrega | Autoriza | Produce | No produce |
|---|---|---|---|---|
| **F0** | Decisión de recorte de #126/#108 | PO | Comentario de decisión y cierre o nueva fecha | Código, migración |
| **F1** | Caracterizar los 897 archivos sin `Issue` (opcional) | PO, con entorno y alcance explícitos | Censo de contenido **solo lectura**, anonimizado, con PASS/FAIL/NOT RUN | Cambios de esquema o archivos |
| **F2** | Revisar el diseño de #184 si F1 o un disparador lo exige | PO | Ajuste del diseño, no una migración | Migración |
| **F3** | Ensayo en copia desechable | Autorización separada | Snapshot, transformación, validación y rollback probados | Migración en producción |
| **F4** | Migración en producción | Autorización separada, con backup y ventana | Migración ejecutada y verificada | Despliegue implícito |

Cada fase tiene una puerta propia. **Aceptar F0 no autoriza F1; F1 no autoriza F3; F3 no autoriza F4.**
El diseño de #184 ya reserva las fases F3/F4 y su plan de validación; no se duplican aquí.

### F0 — decisión (esta entrega)

**Salida esperada del PO:** una de estas tres opciones, escrita en #126:

- **A. Recorte:** aceptar censo + diseño + disparadores, cerrar #126 y #108, y abrir una tarjeta
  futura solo si se cumple un disparador.
- **B. Más evidencia:** mantener #126 abierta y autorizar F1 (censo de contenido) sin migración.
- **C. Espera:** mantener abierta con una fecha de revisión; no autoriza nada más.

Sin una de estas opciones, #126 no está Ready y no se implementa.

### F1 — censo de contenido (solo si se autoriza)

Objetivo: saber si los 897 archivos sin `Issue` son packs, tomos, vinculaciones incompletas u otra
cosa, sin abrir la biblioteca en escritura.

Condiciones mínimas antes de ejecutar:

- entorno y base autorizados por el PO;
- versión de esquema y SHA del procedimiento anotados;
- transacción `READ ONLY`, sin descarga ni escritura;
- salida agregada y muestra seudonimizada, sin rutas ni títulos reales;
- distinguir dato ausente, ambigüedad, fallo y consulta no ejecutada;
- **NOT RUN** explícito si no hay acceso.

No se reutiliza el censo de #181 como si midiera contenido: no abrió archivos.

### F2 — diseño condicionado

Solo se revisa si un disparador o F1 lo justifica. El diseño de #184 ya define entidades,
compatibilidad, backfill, validación y rollback; esta fase no lo reescribe, lo actualiza contra la
evidencia nueva y lo somete a aprobación. Sigue sin autorizar migración.

## 4. Disparadores para reabrir

Cualquiera de estos hechos abre una revisión (no una migración automática):

1. Aparece un `format` distinto de `single_issue` en el catálogo.
2. `grupos_con_multiples` o `colisiones_null` dejan de ser 0.
3. `covered_issue_ids` deja de ser 0.
4. El censo de los 897 archivos los identifica como packs o tomos que cubren publicaciones.
5. El PO aprueba una necesidad de producto nueva que exija ediciones separadas.

Hoy, con la evidencia de #181, **ninguno de los cuatro primeros está acreditado**.

## 5. Criterios de aceptación del refinamiento

- [ ] #126 tiene una decisión explícita A/B/C, no un cierre por inferencia.
- [ ] Si A: #108 registra el mismo recorte y no se presenta la migración como hecha.
- [ ] Si B: F1 tiene entorno, alcance, solo lectura y salida anonimizada definidos antes de ejecutar.
- [ ] En ningún caso se afirma que el diseño autoriza la migración.
- [ ] PASS, FAIL y NOT RUN quedan separados.

## 6. PASS / FAIL / NOT RUN

**PASS**

- ADR 0003 aporta vocabulario y modelo mínimo aceptados con decisiones diferidas.
- #181 ejecutó un censo real, solo lectura, con evidencia conservada.
- #184 entregó un diseño condicionado, no ejecutado.
- #182/#183 resolvieron discriminantes y elección manual sin cambiar esquema.
- El esquema actual confirma que no hay `editions` ni migración de identidad ejecutada.

**FAIL**

- La decisión de recorte de #126 no está tomada; por eso #126 y #108 siguen abiertas.
- No hay evidencia de contenido de los 897 archivos sin `Issue`; no se puede afirmar que no haya
  packs o tomos relevantes.

**NOT RUN**

- Censo de contenido F1.
- Ensayo F3 en copia desechable.
- Migración F4, pruebas de migración, producción y Pi.
- Cualquier cambio de modelo, código o datos.

## 7. Riesgos y límites

- **Migrar por inercia:** crear `editions` sin evidencia añade complejidad y riesgo de recuentos.
- **Cerrar por inferencia:** dar #126 por hecha porque existe un diseño contradice su propio estado.
- **Censo obsoleto:** el de #181 es de esquema `0020`; sigue siendo válido como evidencia de
  ausencia de ediciones, pero no sustituye una medición futura si se reabre.
- **Archivos sin caracterizar:** los 897 pueden cambiar la conclusión; por eso F1 es la única
  evidencia que falta y no se presupone.
- **Privacidad:** cualquier censo futuro debe ser agregado y seudonimizado; no se publican rutas.

## 8. Decisión solicitada

Elegir **A, B o C** en #126. Recomendación: **A**, con una tarjeta futura que solo se active por
disparador. Si se elige B, autorizar F1 de forma separada; si se elige C, fijar fecha de revisión.

Este documento no cambia el estado de ninguna tarjeta, no fusiona código y no despliega nada.
