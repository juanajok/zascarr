# Permisos de la biblioteca compartida

**Problema (2026-11-20).** Desde el PC, por Samba (`force user = pi`, `force group = media`), no se podían
mover ni borrar series que había creado ZascArr: carpetas `2755` y archivos `0600`, dueño `zascarr` (uid del
servicio), así que el grupo `media` solo leía. Ejemplos: Absolute Batman (2024) y Absolute Wonder Woman.

**Causa.** El contenedor corría con `umask 022`: lo que crea no tiene escritura de grupo.

**Arreglo.** `docker-entrypoint.sh` fija `umask 002` antes de ceder el proceso (`runuser` la hereda): lo
nuevo nace `2775`/`664`. `tests/test_entrypoint_umask.py` lo fija.

**Límites.**
- No cambia lo que ya existía: eso se arregla una vez con un `chmod`/`chown` acotado a las rutas afectadas.
- Un archivo creado con `tempfile.mkstemp` nace `0600` aunque la umask sea 002; quien lo cree dentro de la
  biblioteca debe copiar el modo (como hace `services/conversion.py::_copiar_permisos`). Pendiente de revisar:
  `services/exportacion_kavita.py` (cuatro `mkstemp` en carpetas que Kavita lee).
