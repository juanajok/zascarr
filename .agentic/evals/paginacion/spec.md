# Evaluación sintética: paginación

Contrato fijado antes de las dos implementaciones. No representa un defecto observado en ZascArr.

- R1: `page(items, number, size)` acepta `items` como lista y `number` y `size` como enteros positivos, distintos de booleanos; devuelve una lista nueva con la página de numeración desde 1, conservando orden y duplicados.
- R2: una página que empieza en o después del final devuelve `[]`, incluso con lista vacía. La última página incompleta devuelve sus elementos restantes, sin repetir la página anterior.
- R3: número o tamaño no enteros, booleanos o menores que 1 producen `ValueError`. La lista de entrada no se modifica.
- R4: conservar nombre, firma y ausencia de dependencias externas. El único archivo editable es `pagina.py`.

Los dos brazos reciben el código base y estos mismos criterios. La prueba pública RED y la batería de aceptación independiente se congelan antes de solicitar soluciones. Las pruebas son datos de confianza del operador y no se entregan a los implementadores; sus resultados finales son comunes a ambos brazos. Los revisores solo reciben la SPEC y el candidato.
