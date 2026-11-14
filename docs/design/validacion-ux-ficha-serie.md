# Validación UX/UI — ficha de serie (2026-11-14)

> **Método:** render real de la plantilla con una serie de prueba de **200 números** (100
> presentes y 100 ausentes), CSS de producción, Chrome headless a **390×844** y **820×1400**.
> **Aviso:** las capturas usan datos sintéticos y no sustituyen a personas reales. La
> validación con 3–5 coleccionistas sigue **NOT RUN**.

Capturas:
- [Móvil 390×844](validacion-ficha-serie-movil.png)
- [Tableta 820×1400](validacion-ficha-serie-tablet.png)

## 1. Personas simuladas

### P1 · Coleccionista nuevo (móvil)

- Abre la ficha para añadir números del disco.
- Ve el título, el recuento y **«Añadir números del disco» como acción principal** en la
  primera pantalla.
- La navegación por anclas aparece al final del primer pantallazo; «Números» es visible y
  lleva directo al bloque de números.
- **Fricción:** el primer pantallazo no muestra ningún número; la portada y las acciones
  ocupan casi todo. Tras compactar la portada a 96 px, el índice completo cabe antes de la
  barra inferior; un toque en «Números» resuelve la tarea.
- **PASS** con reserva: **P2** valorar si la portada debe seguir bajando o si el recuento
  debe incluir un enlace directo «Ver números».

### P2 · Coleccionista veterano (tableta)

- Serie de 426 números; espera ver de un vistazo qué le falta y qué tiene.
- En tableta, los números aparecen en la primera pantalla tras la cabecera.
- Primero ve 30 ausentes y 30 presentes; el resto queda en «Ver los 70 números que…»,
  sin una pared de 400 chips.
- **PASS.** El umbral 30 evita el bloque masivo y conserva la lectura de los primeros
  números. Queda medir si 30 es el número adecuado con 400+.

### P3 · Lector de móvil (390 px)

- Quiere consultar un número concreto, no editar metadatos.
- La navegación envuelve en dos filas; la segunda queda cerca de la barra inferior fija.
- Los números no aparecen hasta hacer scroll o pulsar «Números».
- **PASS parcial:** sin desbordamiento horizontal y con objetivos de 40 px; **P2** la
  segunda fila del índice queda apretada contra la barra inferior en el primer pantallazo.

### P4 · Administrador de datos

- Quiere editar la ficha y revisar fuentes.
- «Editar la ficha» está en la cabecera; «Retirar de mi biblioteca» ya no compite: está
  plegado con su garantía.
- «Otras fuentes» no aparece si la serie no tiene fuente asociada; no hay botón
  deshabilitado sin salida.
- **PASS.** La acción destructiva está separada; la ficha no promete fuentes que no existen.

## 2. Comprobaciones automáticas

- Orden: `#numeros-serie` aparece antes de `#datos-serie`, `#politica-serie`,
  `#etiquetas-serie` y `#coleccion-serie`.
- Navegación: seis anclas siempre; «Archivos» solo si hay archivos.
- Serie de 200: 30 + 30 chips visibles y dos `<details>` «Ver los 70…».
- «Otras fuentes» ausente sin `comic_vine_id`/`anilist_id`/`tebeosfera_slug`/`gcd_id`.
- «Retirar» dentro de `<details class="series-retirar">` y enlace conservado.
- Sin errores de plantilla; 414 pruebas de ficha/UI/CSS en verde.

## 3. Hallazgos abiertos

| Prioridad | Hallazgo | Propuesta |
|---|---|---|
| **P2** | En 390×844 los números no están en el primer pantallazo, aunque el índice sí | Portada móvil ya a 96 px; valorar enlace «Ver números» junto al recuento |
| **P2** | La segunda fila del índice queda apretada contra la barra inferior | Reducir a 5 anclas o hacer el índice desplazable horizontalmente |
| **P2** | El umbral 30 no está validado con 400+ números | Medir con una serie real y ajustar |
| **P2** | Capturas con datos sintéticos | Validar con 3–5 coleccionistas reales en tableta y móvil |

## 4. PASS / FAIL / NOT RUN

- **PASS:** jerarquía de números, colapso, navegación, retirada plegada, fuentes ocultas,
  tableta, ausencia de overflow horizontal aparente.
- **PASS parcial (móvil):** el índice cabe completo en el primer viewport; los números
  siguen a un toque. Queda decidir si se añade un enlace directo en el recuento.
- **NOT RUN:** validación con personas, lector de pantalla, dispositivo físico y medición
  con una serie real de 426 números.
