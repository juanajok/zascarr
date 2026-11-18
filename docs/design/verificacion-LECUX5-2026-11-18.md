# Verificación BL-LECUX5 — accesibilidad del lector

- **Historia:** [#1072](https://github.com/juanajok/zascarr/issues/1072); épica #1067.
- **Código verificado:** Pi en `78c86b3`; Chrome 156 headless con sesión real.
- **Alcance:** teclado, DOM, foco, roles y objetivos; **lector de pantalla real: NOT RUN**.

## PASS (teclado y DOM)

| Comprobación | Evidencia |
|---|---|
| Contador | `aria-live="polite"` en `#lector-contador`. |
| Menú | Botón «Opciones» con `aria-controls="lector-menu"`; al abrirlo `aria-expanded="true"`; al cerrarlo vuelve a `false`. |
| Barra | `role="group"` y nombre accesible. |
| Flechas | Dos `<button>` con `aria-label` «Página anterior»/«Página siguiente»; 48 px. |
| Orden de foco | Salto de contenido → Volver al número → Opciones → tarjeta de fin; el foco no queda atrapado. |
| Foco y auto-ocultado | Con el foco dentro de la barra, el chrome **no** se oculta tras 3 s; `focusout` lo reprograma. |
| Aviso legal | Enlace `/legal` dentro de Opciones. |
| Errores | `#lector-error` con `role="alert"`; la espera usa `role="status"`. |
| `forced-colors` | Regla de foco visible con `CanvasText` para flechas, botones y controles de imagen. |
| `prefers-reduced-motion` | Sin transición en barra/flechas (regla estática). |

## NOT RUN

- **Lector de pantalla real (NVDA/Orca/VoiceOver): NOT RUN.** No hay uno disponible en el
  entorno; no se declara PASS ni se cierra la historia como verificada.
- **Chrome/Safari en dispositivo táctil físico y zoom real:** NOT RUN.
- **`forced-colors` y `prefers-reduced-motion` en navegador real:** solo comprobación estática;
  no se convierten en PASS.
- **Arrastre/selección táctil con hardware:** NOT RUN.

## Consecuencia

El defecto de foco que podía ocultar el chrome con el foco dentro está corregido y cubierto por
pruebas. La primera pasada dejó pendiente la prueba con lector de pantalla.

## Segunda pasada con Chrome y Orca

- **Entorno:** Chrome 156.0.8078.47, Orca 50.2 y AT-SPI2 2.60.4 en Linux/Xvfb.
  Se sirvieron las plantillas, los recursos y las rutas reales de ZascArr con un CBZ
  de tres páginas generado para la prueba. La sesión de base de datos, las escrituras
  y el resultado de extracción del CBR se sustituyeron por datos controlados.
- **Método:** recorrido de teclado en Chrome, comprobación de foco y estilos computados,
  y registro de voz `SPEECH OUTPUT` de Orca a través de Speech Dispatcher. Los eventos
  controlados de navegador permitieron aislar los anuncios y contarlos.
- **Referencias:** [benchmark de lectores](benchmark-BL-LEC-mercado-lectores-2026.md)
  y [preparación de CBR](verificacion-LECUX4-2026-11-18.md).

### PASS

| Comprobación | Evidencia |
|---|---|
| Teclado | A 375, 768 y 1280 px, Espacio abre Opciones y Tab entra en el primer modo. Las flechas ajustan el brillo sin pasar página. Escape devuelve el foco a Opciones. Se puede llegar al lienzo y a la tarjeta de fin. |
| Orca, contador | La secuencia 1 → 2 → 1 → 3 produjo «Página 2 de 3», «Página 1 de 3» y «Página 3 de 3», una vez cada uno. Repetir Fin en la última página no repitió el anuncio. |
| Orca, opciones y guardado | Orca anunció el menú expandido, confirmó ambos sentidos y leyó «Guardado: Leído.» y «Guardado: En lectura.». El foco quedó en Deshacer al marcar y en Marcar como leído al deshacer. |
| Orca, CBR | El error simulado del sondeo se leyó una vez. Al reintentar, el foco siguió en Reintentar y el error permaneció al repetirse la respuesta. La vista de un error conocido al entrar ofreció las dos acciones de recuperación. |
| Zoom y tacto emulado | Zoom nativo de Chrome al 200 % (1050 → 525 px CSS) con el brillo enfocado y visible. A 375 px emulados, deslizar avanzó, tocar el centro abrió Opciones y las flechas quedaron ocultas. |
| Contraste oscuro | Contador 15,84:1, texto de botones secundarios 8,95:1, anillo de foco sobre fondo 9,37:1 y enlace legal 12,88:1. Texto de Opciones de al menos 14 px y objetivos de 44 px, incluidas las etiquetas activables de las casillas. |
| Preferencias del navegador | La emulación de `forced-colors` dejó un anillo visible. Con `prefers-reduced-motion` los cambios de visibilidad de la barra y las flechas fueron inmediatos. |

### FAIL iniciales, corregidos

- Al sustituir el fragmento de fin se perdían el foco y el anuncio. Los eventos de HTMX 4
  restauran el foco y permiten confirmar la escritura.
- Orca omitía el guardado del sentido con el rol de estado implícito. La región persistente
  usa un anuncio cortés explícito y nombra el sentido guardado.
- El reintento durante la espera podía dejar programado el sondeo anterior. Un error
  conocido al entrar mostraba una vista sin salida. Hay pruebas para los dos recorridos
  y para los siete motivos de CBR de la historia.

### NOT RUN

- Táctil físico, otros lectores de pantalla y otros navegadores.
- Extracción de un CBR dañado en el navegador. Se usaron estados controlados de caché,
  además de las pruebas automatizadas del lector RAR.
