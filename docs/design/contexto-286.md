# Inspeccionar una ficha y volver sin perder el contexto (BL-IT03, #286)

> Contrato implementado sobre `origin/main`. Sin historial paralelo, sin estado global y sin JavaScript nuevo:
> la URL es la fuente de contexto. Una entrega vertical Biblioteca → ficha → Biblioteca.

## 1. Contrato

- La tarjeta de Biblioteca enlaza a `/ui/series/{id}?volver=<url-codificada>`.
- La URL de `volver` es la **URL canónica de la Biblioteca** que se está viendo, con su consulta, filtros y
  `page`, más el ancla `#serie-{id}` de la propia tarjeta.
- La ficha lee `volver`, lo valida y solo entonces lo usa como enlace «← Volver a la biblioteca».
- Sin `volver` válido, la ficha ofrece **«← Biblioteca»** sin inventar una búsqueda; también es el destino ante
  cualquier valor ausente, externo o manipulado.
- La tarjeta tiene `id="serie-{id}"`; el ancla permite que el navegador vuelva a su altura y, al ser un enlace,
  reciba el foco al regresar. `scroll-margin-block-start` evita que quede pegada al borde superior.

## 2. Límites del valor de vuelta

Solo se acepta:

- ruta local exacta `/ui/biblioteca`;
- query de la Biblioteca (`q`, `tradition`, `publisher_id`, `character_id`, `story_arc_id`, `page`);
- ancla `serie-<uuid>` o ninguna;
- sin esquema, host, `//`, credenciales ni caracteres de control;
- longitud máxima 2000.

Se rechazan `https://…`, `//host`, `javascript:`, rutas ajenas, parámetros desconocidos y anclas que no sean la
tarjeta. La Biblioteca vuelve a validar sus propios parámetros al abrirse; el retorno no relaja esa validación.

## 3. Comportamientos

| Caso | Comportamiento |
|---|---|
| Lista estable | Vuelve a la misma consulta, filtros y página; foco en la tarjeta de origen |
| Enlace Volver | Navegación normal al destino validado |
| Atrás/recarga | El historial del navegador conserva la URL; no hay estado global ni mutaciones |
| Dos pestañas | Cada tarjeta codifica la URL de su pestaña; no se comparte estado |
| Acceso directo | «← Biblioteca», sin búsqueda inventada |
| Valor externo/manipulado | Se descarta y se usa «← Biblioteca»; nunca redirección externa |
| Página fuera de rango | La Biblioteca aplica su política existente y explica el ajuste |
| Lista vacía/error | Sin tarjetas no hay retorno inventado; los errores siguen el contrato de Biblioteca |

## 4. Verificación

- `tests/test_web_retorno.py`: contrato del valor de vuelta (válidos y rechazos).
- `tests/test_web_library.py::TestContextoDeRetorno`: la tarjeta lleva `volver` y el ancla correctos.
- `tests/test_web_series.py::TestVolverALaBiblioteca`: contexto válido, directo, manipulado y dos contextos
  independientes.
- **Navegador real** (Chrome 156, app + PostgreSQL 15, 30 series): desde `?page=2` se abrió la ficha, el enlace
  «Volver a la biblioteca» devolvió a `?page=2#serie-{id}`, el foco quedó en `A#serie-{id}` y `scrollY` ≈ 298.
- **NOT RUN:** lector de pantalla real, móvil físico, zoom 200 % y Pi. La estructura usa enlaces nativos y un
  ancla, sin JS; el foco se comprobó en Chrome.
