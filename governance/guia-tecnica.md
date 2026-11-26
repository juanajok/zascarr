# Guía técnica

**Estado: migración en curso.** Reglas trasladadas desde la guía vigente (`CLAUDE.md`, secciones 2 y 4). La copia de la guía se conserva.

## PRE-29 — Nada bloqueante en handlers asíncronos

La entrada/salida síncrona (lectura de ZIP, procesado de imagen, disco) se ejecuta dentro de `asyncio.to_thread()`, nunca en el bucle de eventos. Las descargas externas de portadas usan un semáforo que limita la concurrencia para no atacar al servidor remoto.

## PRE-42 — Convenciones de código

- PEP 8 y PEP 257 para nombres y docstrings: los identificadores van en inglés, los comentarios y los textos de usuario en español. El español es «de cara al coleccionista»; el inglés, «de cara al código».
- Type hints obligatorios, con `from __future__ import annotations` en la cabecera.
- Imports explícitos del paquete raíz (`from zascarr.models import X`), nunca relativos profundos ni ajustes de `sys.path`.

**Ambigüedad pendiente de decisión:** el ejemplo de la guía (`def asignar(...)`) usa un identificador en español mientras la regla pide inglés para el código. No se resuelve por inferencia: se mantiene la regla escrita y el ejemplo se aclara cuando el mantenedor decida cuál manda.

## PRE-43 — Dependencias y constantes del dominio

- Cada dependencia nueva se justifica: es memoria en la Raspberry Pi y superficie de vulnerabilidad. Antes de añadirla se pregunta si se resuelve con la biblioteca estándar.
- Los enums del dominio viven en `models/__init__.py` (`ComicTradition`, `WishlistStatus`, `MetadataSource`, `AgeRating`…); no hay cadenas mágicas repartidas por el código.

## Límites

Esta guía no sustituye a las pruebas ni al sistema de diseño. No autoriza añadir dependencias ni cambiar el estilo de un módulo sin motivo.
