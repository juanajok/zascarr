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

## Rebanada implementada

- `services/calidad.py`: puntuación de archivos (`source_tag`, `width_px`, `quality`) y de títulos
  de release; un candidato solo se propone si es **del mismo número y serie** y su puntuación es
  **estrictamente mayor**.
- En la ficha del número, **«Buscar una edición mejor»**: consulta Prowlarr (misma puerta legal),
  muestra la calidad actual y los candidatos; **«Descargar esta edición»** confirma un token firmado.
- No se borra, mueve ni sustituye ningún archivo: la descarga, si llega, se importa como otro
  archivo del número. La UI lo dice.
- Sin migración.

## Pendiente / no incluido

- Perfil de calidad del coleccionista (D2) y **escaneo periódico** que ofrezca mejoras sin que el
  usuario abra el número. Esta rebanada es bajo demanda.
- Sustitución automática del archivo anterior: explícitamente fuera de alcance.
