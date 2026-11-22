# UATP-09 · Simulación con 5 personas-agente

**Fecha:** 2026-11-22  
**Naturaleza:** **SIMULACIÓN HEURÍSTICA**. No hubo personas reales, consentimiento, móvil físico, lector de pantalla ni sesión moderada. **No es evidencia humana y no cierra UATP-09.**  
**Base:** `origin/main` `3ce1bd5e`, worktree `.worktrees/uatp09`.

## Personas y recorridos

| Persona | Perfil | Resultado general |
|---|---|---|
| P1 María | No técnica, móvil 320, primera vez | Parcial: lector y búsqueda con fricción; aviso legal sin confirmación ni reintento |
| P2 Javier | Solo teclado, escritorio | Parcial: continuidad y previa correctas; segundo salto ficha→número pierde contexto; lector pierde flechas tras Tab |
| P3 Carmen | Lector de pantalla (simulado) | Parcial: aviso legal y ficha probables; previa del número no es consultable; lector con ruido de región viva y sin H1 |
| P4 Lucía | Administradora de recuperación | Éxito: entiende UAT-31 (3/2/2 → 2/2/2, fuera 1); detalle de fallo confunde comprobación con error |
| P5 Pablo | Baja visión, zoom 200 %/720 | Parcial: filtros con altura insuficiente y títulos truncados; sin scroll horizontal |

## Hallazgos consolidados

### P1 · Aviso legal: no se retoma la acción ni se confirma el retorno
Tras aceptar, se vuelve a la página de origen sin mensaje; la acción protegida no se reintenta por diseño. La persona puede creer que la búsqueda ya está lanzada. Además, los tres `required` hacen que el mensaje `falta` del servidor no sea la experiencia normal.  
Evidencia: `web/legal.py`, `legal_wizard.html`, `docs/design/uatp01-retorno-legal.md` (D-1).

### P1 · La continuidad se rompe en ficha → número → ficha
El chip del número no arrastra `volver`; la ficha del número vuelve a `/ui/series/<id>` sin contexto. UATP-02 lo declara fuera de alcance, pero el recorrido real de lectura pasa por ahí.  
Evidencia: `series_detail.html`, `issue_detail.html`, `series.py`.

### P1 · El asa del lector no es descubrible y su barra ocupa demasiado a 320
La única pista es un icono de 44×44 con `aria-label`; la ayuda está dentro de la barra oculta. A 320×320 la barra abierta ocupa ~62 % del alto. Es una decisión de UATP-03, pero no validada con personas.  
Evidencia: `lector.html`, `web.css`, `uatp03-controles-lector.md`.

### P1 · Vista previa: un lector de pantalla no puede consultarla
La tarjeta es `aria-hidden="true"`, imagen `alt=""` y el botón escribe en ese contenedor; no se anuncia al enfocar, abrir ni cerrar. Si UAT-05 exige consulta con lector, no puede ser PASS.  
Evidencia: `series_detail.html`, `_previa_numero.html`, `test_web_portada_numero.py`, `uatp05-previa-teclado.md` D-5.

### P1 · Filtros de Biblioteca sin altura útil a 320/zoom
`max-height: 40dvh` deja el panel en ~124 px con 16 campos y el pie sticky tapa el primer `input`; filtrar exige buscar dentro de una ventanita.  
Evidencia: `web.css:2581-2582`, `_rejilla_biblioteca.html`.

### P2 · Títulos de tarjeta truncados a una línea
A 360 px el título largo se recorta y el `title` solo resuelve con ratón; en táctil/zoom se pierde información.  
Evidencia: `_rejilla_biblioteca.html:166`, `web.css:943-945`.

### P2 · Detalle de fallo de restauración mal etiquetado
El resumen pinta `error={{ comprobacion }}`; la persona técnica lee `error=sha256_copia` en vez del código real `copia_no_valida`.  
Evidencia: `restauracion_resumen.html:66`, `ops_host.VistaRestaurar`.

### P2 · Resumen de recuperación: ceros y límites
Se pinta «Quedan fuera 0 series…» cuando no hay diferencias; el caption «no dicen qué fila cambió» es honesto pero deja UAT-31 a medias si se exige identidad.  
Evidencia: `restauracion_resumen.html:37-42`, evidencia UAT-31 3c.

### P2/P3 accesibilidad
- Tercera casilla legal con hash de 16 hex en el nombre accesible; casillas sin `fieldset`/`legend`.
- Lector sin H1 y `output` de zoom con `aria-live` reescrito en cada página (doble anuncio).
- `h3` de «Archivos por número» absorbe los nombres de sus controles; anclas de sección sin `tabindex="-1"`.
- Enlaces de copia «Restaurar…» sin fecha; `sin_datos` con H2 en vez de H1.

## Lectura para el equipo

- **No hay ningún NO de producto en los recorridos principales**, pero sí **dos grietas de continuidad** (aviso legal y segundo salto) y **dos de accesibilidad** (previa del lector y foco/ruido del lector) que conviene corregir antes de gastar sesiones humanas.
- Los hallazgos de 320/zoom son de layout: un `40dvh` y un truncado de una línea; no requieren rediseño.
- La recuperación (UAT-31) se entiende por el resumen; el defecto es de etiqueta técnica y de ceros, no de concepto.

## Qué NO acredita

- 3–5 participantes reales, móvil físico, NVDA/Orca/VoiceOver, Firefox/Safari, Pi (frío/caliente, red lenta, p50/p95): **NOT RUN**.
- Las personas-agente leyeron plantillas/CSS/pruebas y algunos ejecutaron TestClient/Node; **no** son personas ni sustituyen una sesión moderada.
- UATP-09 sigue **EN CURSO**; la épica #1141 no se cierra con este documento.
