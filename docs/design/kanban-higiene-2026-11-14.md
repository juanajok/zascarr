# Higiene del Kanban — 2026-11-14

Revisión de las **32 tarjetas activas** del Project 1 (todo lo que no está en
«Hecha»), cruzadas con issues abiertos/cerrados, PRs fusionados y código de
`main` (commit `c3817fc`).

## Resumen

| Estado | Tarjetas |
|---|---:|
| Backlog | 21 |
| En refinamiento | 5 |
| Lista para desarrollar | 5 |
| En curso | 1 |
| **Total activo** | **32** |

## Reconciliadas ahora

| Issue | Qué pasaba | Acción |
|---|---|---|
| [#705](https://github.com/juanajok/zascarr/issues/705) | SCR4 fusionada en #783/#785 y desplegada en la Pi, pero el issue seguía abierto. | **Cerrada** con comentario; la tarjeta ya estaba en Hecha. |
| [#789](https://github.com/juanajok/zascarr/issues/789) | Issue cerrada por #791, pero la tarjeta seguía en «Fusionado — pendiente de despliegue». | Tarjeta movida a **Hecha**. |

## Candidatas claras a retirar del tablero

### #161 — BL-C7: fichero de estado por carpeta

- Issue **cerrada como `not_planned`** el 2026-11-14: no hay estándar ni
  consumidor claro para `series.json`; duplicaría `ComicInfo.xml`/B20 y
  escribiría en la biblioteca canónica.
- La tarjeta sigue en **En refinamiento**.
- **Acción recomendada:** quitar la tarjeta del Project (o archivar el issue
  como no procedente). No se implementa.

### #111 — MIT-M8: contrato operativo de fuentes

- Feature **padre** de #133, #134 y #135.
- Las tres hijas están **cerradas**.
- No queda trabajo activo conocido; el contrato se ejerció en las historias.
- **Acción recomendada:** revisar el DoD de la feature y cerrarla como
  completada, o dejar una nota de qué evidencia falta. No abrir trabajo nuevo
  sin una hija concreta.

### #125 — MIT-M5-US02: elegir una publicación identificada

- Historia **paraguas** de #182 (discriminantes) y #183 (elección).
- #182 y #183 están **cerradas**; el flujo de elección existe en la UI.
- **Acción recomendada:** cerrar #125 como cubierta por sus hijas y dejar #108
  (M5) abierta solo por #126. Antes de cerrar, comprobar que no queda ninguna
  casilla de aceptación sin evidencia.

## Activas que siguen teniendo sentido

| Issue | Motivo para no retirarla |
|---|---|
| [#443](https://github.com/juanajok/zascarr/issues/443) BL-OPS1 | Implementación por bloques; PR #685 sigue abierto y hay trabajo de actualización/copia/restauración pendiente. |
| [#360](https://github.com/juanajok/zascarr/issues/360) BL-A11Y | La segunda ronda (#727) mejoró foco y regiones, pero siguen los avisos duplicados y el título del resultado; no está cubierta entera. |
| [#107](https://github.com/juanajok/zascarr/issues/107) MIT-M4 | Su hija #122 sigue abierta; es aceptación, no código ya hecho. |
| [#108](https://github.com/juanajok/zascarr/issues/108) MIT-M5 | Sigue abierta por #126 (migrar sin confundir recuentos), no por #125. |
| [#126](https://github.com/juanajok/zascarr/issues/126) MIT-M5-US03 | No consta implementación equivalente en `main`. |
| [#205](https://github.com/juanajok/zascarr/issues/205) BL-U18 | Bloqueada por el glosario U7; #789 cerró solo las erratas independientes. |
| [#382](https://github.com/juanajok/zascarr/issues/382) | La marca «Sugerida para esta serie» en carpetas mixtas sigue sin corregir. |
| [#423](https://github.com/juanajok/zascarr/issues/423) BL-C6-O1 | La duplicación ficha/enricher sigue siendo deuda real. |
| [#529](https://github.com/juanajok/zascarr/issues/529) BL-PORT6b | Quedan huecos de tests/documentación de portadas. |
| [#593](https://github.com/juanajok/zascarr/issues/593) BL-INF7 | La tira de números en tarjetas de Biblioteca no está implementada. |
| [#367](https://github.com/juanajok/zascarr/issues/367), [#369](https://github.com/juanajok/zascarr/issues/369), [#372](https://github.com/juanajok/zascarr/issues/372), [#363](https://github.com/juanajok/zascarr/issues/363) | Deuda de seguridad/logs/backup con decisiones o pruebas pendientes. |
| [#157](https://github.com/juanajok/zascarr/issues/157) BL-A7 | `bootstrap.sh` sigue sin preguntar el usuario de servicio; no está hecho. |
| [#338](https://github.com/juanajok/zascarr/issues/338), [#339](https://github.com/juanajok/zascarr/issues/339), [#706](https://github.com/juanajok/zascarr/issues/706), [#736](https://github.com/juanajok/zascarr/issues/736), [#793](https://github.com/juanajok/zascarr/issues/793) | Producto/fuentes/glosario: siguen siendo trabajo futuro, no duplicados. |
| [#148](https://github.com/juanajok/zascarr/issues/148), [#262](https://github.com/juanajok/zascarr/issues/262), [#159](https://github.com/juanajok/zascarr/issues/159), [#265](https://github.com/juanajok/zascarr/issues/265), [#266](https://github.com/juanajok/zascarr/issues/266) | Paraguas o refinamientos de duplicados; no son implementaciones cerradas. |
| [#162](https://github.com/juanajok/zascarr/issues/162), [#163](https://github.com/juanajok/zascarr/issues/163), [#164](https://github.com/juanajok/zascarr/issues/164), [#156](https://github.com/juanajok/zascarr/issues/156) | Backlog de producto aún no cubierto por `main`. |

## Recomendación operativa

1. **Quitar #161** del tablero: está cerrada como no procedente.
2. **Cerrar #111 y #125** solo después de una comprobación rápida de su DoD;
   no son código pendiente, son padres sin hijas abiertas.
3. **Mantener #443 y #360** activas: tienen trabajo real, aunque #360 deba
   actualizar su alcance tras #727.
4. **No tocar** los paraguas #148/#262 ni las historias de producto sin
   evidencia de implementación.

## Lo que no se ha hecho

- No se ha cerrado #111 ni #125: requieren decisión de producto/DoD.
- No se ha borrado la tarjeta #161: es reversible y conviene dejar rastro;
  la acción recomendada es retirarla del tablero, no borrar el issue.
- No se ha revisado el contenido funcional de cada issue de producto; el
  cruce se basa en estado, PRs fusionados, hijos y referencias de código.
