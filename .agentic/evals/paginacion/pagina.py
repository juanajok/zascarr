"""Fixture sintético: paginación de un catálogo en memoria."""


def page(items, number, size):
    """Devuelve una lista con los elementos de la página solicitada."""
    start = (number - 1) * size
    if start >= len(items):
        start = max(0, len(items) - size)
    return items[start : start + size]
