# BL-D3 (#154) — benchmark y especificación: proponer una edición mejor

> **Método:** lectura de referencias y del código vigente; **NOT RUN** sobre Sonarr/Radarr/
> Kavita/Komga/Mylar3. D2 (selector de calidad) no está implementada: esta rebanada **no inventa
> un perfil de calidad del coleccionista**; usa solo lo que consta en el archivo y en el título del
> release.

## Problema local

Ya tengo un número, pero puede llegar una edición mejor (digital frente a escaneo, más resolución).
Hoy ZascArr no compara ni propone: la ficha solo lista los archivos. D3 pide que la UI **proponga**
una mejora y que nada se sustituya sin confirmación.

## Referencias

| Referencia | Patrón útil | Límite |
|---|---|---|
| **Sonarr/Radarr** | «Cutoff»/perfil de calidad: una release mejor puede reemplazar a la actual; descarga y luego importa | Necesita un perfil de calidad que aquí no existe (D2) |
| **Kavita/Komga** | Editan metadatos, pero no proponen upgrades de archivos | No aplica |
| **Mylar3/Kapowarr** | Comparan/eligen ediciones y archivos, sin sustituir sin intervención | Modelo y criterios distintos |

**Decisiones:** adoptar la idea de **propuesta + confirmación**; descartar sustitución automática;
descartar por ahora el escaneo en segundo plano (requiere D2 y persistencia de propuestas); usar una
puntuación conservadora y explícita.

## Implementado

- **D2:** selector legible en Ajustes («solo lo mejor / equilibrado / lo que haya») que fija el
  objetivo de calidad; se guarda como override en caliente. La cadencia del escaneo también se
  elige (3/6/12/24 h o desactivado).
- `services/calidad.py`: puntuación de archivos (`source_tag`, `width_px`, `quality`) y de títulos
  de release; un candidato solo se propone si es **del mismo número y serie** y supera el objetivo
  del perfil.
- **Escaneo periódico acotado** (`services/upgrades.py` + bucle): coge un lote pequeño de números
  con archivo, respeta un cooldown de 24 h por número y guarda **propuestas** en
  `upgrade_proposals` (migración 0034). No descarga solo.
- **Biblioteca → Mejoras**: lista de propuestas; **«Descargar esta edición»** confirma el envío con
  token firmado y **«Descartar»** retira la propuesta.
- En la ficha del número sigue estando **«Buscar una edición mejor»** bajo demanda.
- No se borra, mueve ni sustituye ningún archivo: la descarga, si llega, se importa como otro
  archivo del número. La UI lo dice.

## Fuera de alcance

- Sustitución automática del archivo anterior: explícitamente fuera; el coleccionista decide qué
  archivo conservar desde la ficha.
