# Permisos de la biblioteca compartida

**Problema (2026-11-20).** Desde el PC, por Samba (`force user = pi`, `force group = media`), no se podían
mover ni borrar series que había creado ZascArr: carpetas `2755` y archivos `0600`, dueño `zascarr` (uid del
servicio), así que el grupo `media` solo leía. Ejemplos: Absolute Batman (2024) y Absolute Wonder Woman.

**Causa.** Dos cosas: el contenedor corría con `umask 022`, y la ruta de asignar (`utils/fs.py`, único
camino de `POST /ui/pendientes/{id}/asignar`) crea con modos EXPLÍCITOS (`mkdir 0o755`, `open 0o600`) que
ninguna umask cambia. Lo vio SecOps al revisar la primera versión de #1156 (F-1): la umask sola no arreglaba nada.

**Arreglo.**
- `utils/fs.py`: carpetas nuevas `0o775` (conservando el setgid heredado, `_crear_carpeta`) y archivos `0o664`
  con `fchmod` DESPUÉS de verificar tamaño y sha256 y ANTES de publicarlos; el temporal sigue naciendo `0600`.
  Vale con cualquier umask.
- `docker-entrypoint.sh` fija `umask 002` antes de ceder el proceso (`runuser` la hereda): el resto de lo que crea
  el contenedor (portadas, huellas, carpetas auxiliares) nace `2775`/`664`.
- `tests/test_entrypoint_umask.py` fija ambos.

**Decisión (PO, 2026-11-20).** Escritura de grupo fija, sin variable `UMASK`. Coste aceptado (dictamen de SecOps):
el grupo `media` (Transmission, Sonarr, Prowlarr, Kavita, Samba) puede alterar un CBZ que luego abre ZascArr
(`zipfile`/`unar`, ADR 0015); no contradice CLAUDE.md §5, SECURITY.md ni ADR 0012. Si alguien necesita más
estricto, se añade una variable `UMASK` con 022 por defecto.

**Límites.**
- No cambia lo que ya existía: eso se arregla una vez con un `chmod`/`chown` acotado a las rutas afectadas.
- Un archivo creado con `tempfile.mkstemp` nace `0600` aunque la umask sea 002; quien lo cree dentro de la
  biblioteca debe copiar el modo (como hace `services/conversion.py::_copiar_permisos`). Pendiente de revisar,
  fuera de #1156: `services/exportacion_kavita.py` (cuatro `mkstemp` en carpetas que Kavita lee) y
  `utils/cbz.py` (`mkstemp` + `os.replace` sin copiar el modo).
- La rama de `safe_move_en_raiz` que enlaza en el mismo dispositivo (`os.link`) conserva el modo del origen.
