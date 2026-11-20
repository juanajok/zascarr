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
- `safe_move_en_raiz` (lo usa el importador) enlaza en el mismo dispositivo SOLO si el archivo es del proceso (o root): tras el `os.link` se le da `0664` antes de borrar el origen. Si es de otro usuario (p. ej. Transmission) no se puede cambiar su modo, así que se copia y la copia nace con el modo de la biblioteca (cuesta espacio y tiempo extra en ese caso).
- Con origen de otro usuario que el grupo no puede leer (p. ej. `0600` de Transmission), antes se enlazaba sin leer el
  contenido; ahora se intenta copiar y falla con un mensaje de permisos (ya no habla de symlink). Las descargas
  suelen ser legibles por el grupo.
- Si el grupo del proceso no es el del directorio, `fchmod` quita el setgid de la carpeta nueva (775): no aplica con el
  `PGID` del grupo compartido (`media`) que configura el instalador.
- El modo del enlace se fija por descriptor (`os.fchmod(src_fd)`), no por nombre: la carpeta es escribible por el grupo
  y un nombre sustituido por un symlink haría `chmod` sobre otro archivo (SecOps, F-2).
