"""Fixture sintético: paginación de un catálogo en memoria."""


def page(items, number, size):
    """Devuelve una lista con los elementos de la página solicitada."""
    if (not isinstance(number, int) or isinstance(number, bool) or number < 1
            or not isinstance(size, int) or isinstance(size, bool) or size < 1):
        raise ValueError("El número y el tamaño deben ser enteros positivos.")
    start = (number - 1) * size
    return items[start : start + size]
