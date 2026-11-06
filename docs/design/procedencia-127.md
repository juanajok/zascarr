# Procedencia y protección por campo (MIT-M6-US01, #127)

> Contrato **implementado** sobre `origin/main`. Solo lectura: no añade modelo, columnas, migración,
> escritura ni consulta a fuentes. La ficha de serie muestra lo que ya consta en
> `Series.metadata_["alta"]`, `Series.metadata_source` y `Series.locked_fields`.

## 1. Campos gestionados

El bloque «De dónde sale cada dato» muestra estos campos, en este orden:

| Campo | Qué se enseña |
|---|---|
| Título | valor actual |
| Año de inicio | valor actual o «Sin dato» |
| Sinopsis | valor resumido a 160 caracteres |
| Portada | «Portada guardada» / «Sin portada»; nunca la URL |
| Números en total | valor actual o «Sin dato» |
| Identificador de la fuente | «Identificador registrado» / «Sin identificar»; nunca el id |

## 2. Reglas de origen

- **Alta manual** (`metadata_["alta"].origen == "manual"` o `metadata_source == "manual"`): los campos
  aparecen como «Introducido a mano» y con chip «Manual».
- **Alta desde una fuente**: los campos del alta (título, año, sinopsis, portada e identidad) llevan
  «Alta desde {fuente}».
- **Enriquecimiento**: si hay `metadata_source` de una fuente y el campo es de los que escribe el
  enriquecimiento (sinopsis, portada, total o identidad), lleva «Enriquecido desde {fuente}».
- **Sin evidencia**: «Origen no registrado». No se infiere manual ni se atribuye una fuente.
- `metadata_source` es de la **serie**, no una procedencia por campo: por eso título y año no se
  atribuyen al enriquecimiento, y los campos de enriquecimiento solo se atribuyen cuando tienen valor.
- La identidad se agrupa en un solo campo; sus ids internos nunca se pintan.

## 3. Protección

`locked_fields` se muestra como chip «Protegido» y con la frase «Protegido: el enriquecimiento no lo
sobrescribe.». La protección es un estado del registro; la interfaz no la decide ni ofrece acciones
para desbloquear o sobrescribir.

## 4. Observaciones y propuestas

- Se muestra la fecha del alta (en el resumen) y el último intento de enriquecimiento cuando consta.
- **No hay propuestas por campo persistidas** en el contrato actual: la vista no inventa una
  propuesta ni la presenta como aplicada. Si el enriquecimiento propone un valor para un campo
  protegido, el valor actual se conserva (lo garantiza `services/enricher.py`); la propuesta no se
  muestra porque no se guarda. Esto es un **NOT RUN de #128**, no un PASS de #127.

## 5. Criterios → pruebas

| # | Criterio | Prueba |
|---|---|---|
| 1 | Campos gestionados delimitados | `test_procedencia_serie.py::test_los_campos_son_los_del_contrato_y_en_orden`; `test_web_series.py::TestProcedenciaCamposC6` |
| 2 | Origen visible y fiel | `test_alta_desde_fuente_atribuye_solo_los_campos_del_alta`, `test_enriquecimiento_sin_alta_no_atribuye_titulo_ni_ano` |
| 3 | Origen desconocido explícito | `test_sin_procedencia_no_atribuye_nada`, web `test_sin_procedencia_lo_dice_en_vez_de_atribuir` |
| 4 | Dato manual distinguible | `test_alta_manual_es_manual_y_con_fecha` |
| 5 | Bloqueo visible | `test_campo_bloqueado_se_marca_y_no_expone_el_id`, web de la ficha |
| 6 | Protección ante enriquecimiento | Mensaje de protección; la conservación la garantiza `enricher.py` (no se ejecuta aquí) |
| 7 | Propuesta sin pérdida silenciosa | **NOT RUN**: no hay propuestas persistidas por campo; no se muestran |
| 8 | Acciones limitadas | El bloque no tiene botones; solo lectura |
| 9 | Mensajes claros | Textos del servicio y de la plantilla, sin ids internos |

## 6. NOT RUN

- Enriquecimiento real y propuesta por campo: no existe el registro; queda para #128.
- Fuentes reales, Pi y navegador real en esta revisión.
- Campos de `Issue`, `Creator` y `Character`: esta entrega se limita a la serie y a los campos del
  contrato de serie; no se amplía el alcance sin reconciliarlo con #128/#129.
