# Reglas de interfaz y diseño

**Estado: migración en curso.** Reglas trasladadas desde la guía vigente (`CLAUDE.md`, sección 6). La copia de la guía se conserva; trasladar no retira la norma. La referencia de diseño sigue siendo [el sistema de diseño](../docs/design/sistema-de-diseno-zascarr.md).

## PRE-33 — Lenguaje, estado y tolerancia al fallo

### PRE-33-1 — Español llano y errores con causa y acción

Todo va en español llano. Un error técnico se traduce a causa y acción para el coleccionista (historia A2); «exit code 1» está prohibido en superficie.

### PRE-33-2 — Semáforos con texto y servicio desactivado

Semáforos visibles con texto concreto sobre qué falló y qué hacer. Un servicio desactivado en Ajustes no es un fallo: `/api/health` lo da como `disabled`, no lo sondea y la pantalla lo pinta «Desactivado» en gris.

### PRE-33-3 — Sin diálogos nativos ni confirmaciones invisibles

`hx-confirm` no lo resuelve la automatización del navegador; la limitación se documenta como aceptada y no se oculta.

### PRE-33-4 — Tarjetas tolerantes al fallo

Portada rota muestra un marcador (`ui.portada`, sin `onerror=`), nunca una imagen rota; campo ausente, icono claro.

### PRE-33-5 — Texto informativo de 14 px con su única excepción

El texto informativo no baja de 14 px. La única excepción declarada y probada es la etiqueta de la barra inferior móvil; no se acorta la etiqueta para cumplir el umbral.

## PRE-34 — Tipografía, cifras, iconos y marca

### PRE-34-1 — Dos familias libres, servidas por la aplicación

Dos familias libres, servidas desde `static/vendor/fonts`, nunca desde un CDN. Ni fuentes comerciales ni una tercera familia de rotulación de cómic.

### PRE-34-2 — Anton para titulares, Archivo para leer

Anton solo en mayúsculas para titulares y rótulos; las frases y todo lo que se lee van en Archivo; los chips fijan su fuente en vez de heredarla.

### PRE-34-3 — Cifras comparables en tabular

Las cifras que se comparan (contadores, números de grapa, métricas) usan cifras tabulares.

### PRE-34-4 — Iconos SVG, nunca caracteres

Iconos SVG de trazo de Lucide con su aviso de licencia en el módulo; nunca caracteres de texto, que cada sistema dibuja distinto.

### PRE-34-5 — Marca con variantes por tamaño

La marca tiene variantes por tamaño y sus reglas en el README de `static/brand`; la trama y las líneas de impacto solo en el icono grande.

## PRE-35 — Tramas, botones y títulos

### PRE-35-1 — Trama donde no hay texto y apagado por preferencias

La trama va donde no hay nada que leer encima, con porcentajes máximos, y se apaga con preferencias de contraste o colores forzados. Una prueba exige que cada trama nueva esté en ese bloque.

### PRE-35-2 — Desalineamiento solo en el rótulo de error

El desalineamiento de planchas se usa únicamente en el rótulo de la página de error: en texto pequeño se lee borroso.

### PRE-35-3 — Un único botón principal por pantalla

El botón que hace avanzar la tarea se marca como principal; el resto son neutros. Excepción con significado propio: el verde de aceptación.

### PRE-35-4 — Un aviso no parece un botón

Los avisos y pies de texto van sin la sombra dura desplazada, con canto de panel.

### PRE-35-5 — Títulos que son frases, en Archivo

Cualquier título de más de tres palabras o que muestre una ruta va en Archivo; los `h1` de pantalla siguen siendo rótulos en Anton.

## Límites

Estas reglas no sustituyen al sistema de diseño publicado ni a las pruebas de contraste y accesibilidad existentes. No autorizan rediseños.

## PRE-36 — Presupuesto de texto

Los umbrales son provisionales hasta validarlos con uso real.

### PRE-36-2 — Frase de entrada y palabras antes de la primera acción

Una frase de entrada por pantalla, de 20 palabras como máximo, que diga qué se hace aquí. No más de 50 palabras visibles antes de la primera acción; el resto va en un desplegable («¿De dónde salen estos datos?», «Avanzado»).

### PRE-36-3 — La garantía va junto a la acción

La garantía («no se mueve ni se renombra nada») se coloca junto a la acción con efecto y en su confirmación, no en la cabecera de pantallas que no cambian nada.

### PRE-36-4 — Resumen antes que listado

Primero el resumen, después el listado. Las mayúsculas se reservan a rótulos de tres palabras o menos.

### PRE-36-5 — Los textos explican la tarea, no el contrato

Nada de «token», «lote» ni códigos internos en superficie: se explica lo que la persona tiene que hacer (A2, U20).

### PRE-36-6 — Umbrales provisionales

Estos umbrales son provisionales hasta validarlos con uso real; no se presentan como medidos.
