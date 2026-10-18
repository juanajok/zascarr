# ruff: noqa: E501
"""La regla ÚNICA de «esta contraseña no vale», como tabla de casos que comparten sus tres implementaciones.

Bash (`scripts/_credenciales.sh`), Python (`zascarr/utils/credenciales.py`) y el servicio `credenciales` de
`docker-compose.yml` tienen que dar la misma respuesta para el mismo valor. Una lista común de nombres no basta: los
tres normalizaban distinto (el servicio de Compose borraba los espacios y las comillas INTERIORES, así que la
contraseña personal `change me` se clasificaba como `changeme`, y las otras dos la dejaban pasar).

La regla: 1) se recortan los espacios en blanco de los extremos (espacio, tabulador, CR, LF); 2) si el valor empieza y
acaba por la misma comilla (`'` o `"`), se quita ese par; 3) se recortan otra vez los extremos; 4) se pasa a
minúsculas; 5) no vale si queda vacío o es EXACTAMENTE uno de los valores conocidos. Nunca se borra nada interior.
"""
from __future__ import annotations

#: (valor, no_vale)
TABLA: list[tuple[str, bool]] = [
    ("", True), ("   ", True), ("\t", True), ('""', True), ("''", True), ("' '", True),
    ("cambia_esto_ahora", True), ("CAMBIA_ESTO_AHORA", True), ("  changeme  ", True), ("\tchangeme\t", True),
    ("ChangeMe", True), ("SuperSecretPassword123", True), ("supersecretpassword123", True),
    ('"changeme"', True), ("'changeme'", True), ('"cambia_esto_ahora"', True), (" 'ChangeMe' ", True),
    # No son valores conocidos: se ven parecidos, pero NO se borra nada interior para que lo parezcan.
    ("change me", False), ("chan geme", False), ("chan'geme", False), ('ch"angeme', False),
    ('"change me"', False), ("cambia esto ahora", False), ("cambia_esto_ahora_no", False),
    ("changeme1", False), ("xchangeme", False),
    # Una comilla sin pareja no se quita: es parte del valor.
    ('"changeme', False), ("changeme'", False), ("'", False), ('"', False),
    # Comillas anidadas: se quita UN par, lo que queda ya no es un valor conocido.
    ("\"'changeme'\"", False),
    ("Sint3tica-Tabla-0001", False), ("a" * 48, False),
]
