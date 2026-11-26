# Clasificación de riesgo (aprobada el 2026-11-26)

Clasifica cada cambio **antes** de ejecutarlo. El diff puede elevar el nivel; nunca reducirlo. Si el ámbito afectado es alto, el nivel es alto aunque el cambio parezca pequeño.

## Niveles

| Nivel | Cuándo aplica | Artefactos exigidos | Quién aprueba |
|---|---|---|---|
| `trivial` | Solo texto, comentarios, formato o documentación sin efecto ejecutable, con diff verificable | Descripción del cambio y comprobación de que no altera comportamiento | Quien tenga permiso de fusión |
| `bajo` | Corrección contra un requisito vigente, con prueba de regresión; sin cambios de contrato | Requisito referenciado, prueba que falla antes y pasa después | Revisión de código del área |
| `medio` | Comportamiento nuevo o modificado; interfaz, importador, catálogo o metadatos | Contrato aprobado antes de programar, prueba nombrada por criterio, revisión independiente | Contrato por el mantenedor; revisión independiente del candidato |
| `alto` | Datos, migraciones, ficheros, seguridad, credenciales, permisos, restauración, gates o incompatibilidad contractual | Todo lo de `medio` más análisis de amenazas, plan de reversión y revisión de seguridad **del SHA final** | Mantenedor y revisión de seguridad del SHA que se fusiona |

## Elevadores automáticos

Cualquiera de estos hechos eleva a `alto` sin discusión:

- Modificar `services/seguridad.py`, `web/ajustes.py` o `services/reautenticacion.py`.
- Tocar migraciones aplicadas o el esquema de datos.
- Cambiar el contrato de una API pública, del importador o de la organización de ficheros.
- Alterar CI, estructura de permisos, gates o políticas de revisión.
- Introducir una dependencia nueva de runtime.

## Excepciones

Una excepción urgente registra causa, alcance, riesgo, mitigaciones, responsable, caducidad con fecha y seguimiento. **No** exime de los controles de seguridad del nivel alcanzado ni de la aprobación de fusión, y no certifica la discrepancia que la motivó.

## Límites

- Esta clasificación no crea gates ni cambia CI: la activación de checks obligatorios es una decisión aparte.
- Los niveles son los propuestos y aprobados con la especificación T1.3; si el mantenedor los cambia, este fichero se actualiza primero.
