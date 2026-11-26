"""Fixture sintético: paginación de un catálogo en memoria."""

from __future__ import annotations


def page(items: list, number: int, size: int) -> list:
    """Devuelve una lista nueva con los elementos de la página solicitada."""
    if (
        isinstance(number, bool)
        or not isinstance(number, int)
        or number < 1
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size < 1
    ):
        raise ValueError("El número y el tamaño deben ser enteros positivos")
    start = (number - 1) * size
    return items[start : start + size]
