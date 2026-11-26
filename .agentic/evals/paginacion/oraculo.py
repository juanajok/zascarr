"""Pruebas independientes de la SPEC de paginación sintética."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

path = Path(sys.argv.pop(1)).resolve()
spec = importlib.util.spec_from_file_location("pagina_candidata", path)
if spec is None or spec.loader is None:
    raise RuntimeError("No se pudo cargar el candidato")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PaginationContract(unittest.TestCase):
    def test_fuera_de_rango_vacia(self) -> None:
        self.assertEqual(module.page([1, 2, 3], 3, 2), [])
        self.assertEqual(module.page([1, 2, 3], 100, 2), [])
        self.assertEqual(module.page([], 1, 2), [])

    def test_paginas_y_duplicados(self) -> None:
        items = [1, 1, 2, 3, 5]
        self.assertEqual(module.page(items, 1, 2), [1, 1])
        self.assertEqual(module.page(items, 2, 2), [2, 3])
        self.assertEqual(module.page(items, 3, 2), [5])
        self.assertEqual(items, [1, 1, 2, 3, 5])
        self.assertIsNot(module.page(items, 1, 100), items)

    def test_parametros_invalidos(self) -> None:
        for number, size in [(0, 1), (-1, 1), (1, 0), (1, -1), (True, 1),
                             (1, False), (1.0, 2), (1, "2"), (None, 1)]:
            with self.subTest(number=number, size=size), self.assertRaises(ValueError):
                module.page([1, 2], number, size)


if __name__ == "__main__":
    unittest.main()
