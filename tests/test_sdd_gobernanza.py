"""Comprueba la estructura y los enlaces de la gobernanza SDD (T1.1).

Verifica lo que la especificación T1.1-C05 y T1.1-C06 pueden comprobar sin
juicio semántico: que existan los documentos, que sus enlaces relativos
resuelvan, que el mapa de reglas no repita orígenes y que ningún documento
afirme una carga efectiva de instrucciones que no se ha verificado.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOVERNANCE = ROOT / "governance"
AGENTS = ROOT / "AGENTS.md"
GUIDE = ROOT / "CLAUDE.md"

REQUIRED = ("constitution.md", "product-vision.md", "glossary.md", "mapa-reglas.md")
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
RULE_ROW = re.compile(r"^\|\s*(PRE-[A-Z0-9]+)\s*\|", re.MULTILINE)
SECTION = re.compile(r"^## (\d+)\.", re.MULTILINE)
CONCEPTS_BLOCK = re.compile(r"^### 14\.1.*?$(.*?)^### 14\.2", re.MULTILINE | re.DOTALL)
CONCEPT_ROW = re.compile(r"^\| \*\*(.+?)\*\* \|", re.MULTILINE)
SPEC = ROOT / "docs" / "design" / "especificacion-SDD-T1.1-gobierno.md"
EVIDENCIA = ROOT / "docs" / "design" / "t1.1-evidencia.md"
CRITERION = re.compile(r"T1\.1-C\d{2}")
EVIDENCE_STATES = ("HECHO", "PARCIAL", "PENDIENTE", "NOT RUN")
EVIDENCE_ROW = re.compile(r"^\|\s*(T1\.1-C\d{2})\s*\|\s*([A-Z ]+?)\s*\|", re.MULTILINE)
# Afirmaciones que solo serían válidas con una prueba de carga efectiva (T0.4).
FORBIDDEN = re.compile(
    r"carga efectiva verificada|instrucciones cargadas correctamente|"
    r"verificado en claude code|verificado en codex|verificado en opencode",
    re.IGNORECASE,
)
BREAKDOWN = re.compile(r"^### Desglose de (PRE-\d{2})\s*$", re.MULTILINE)
SUB_RULE = re.compile(r"^\|\s*(PRE-\d{2}-\d+)\s*\|", re.MULTILINE)
RULE_STATUS = re.compile(r"^\|\s*PRE-[A-Z0-9]+\s*\|.*\|\s*([^|]+?)\s*\|\s*$", re.MULTILINE)
ALLOWED_STATUS = ("sin migrar", "migrada")
# Frases que declararían una autoridad nueva sin aprobación del traslado.
FORBIDDEN_AUTHORITY = re.compile(
    r"(sustituye|deroga|reemplaza)\s+(a\s+)?(la\s+)?gu[ií]a|"
    r"CLAUDE\.md\s+(ya\s+)?no\s+(es|est[aá])\s+vigente",
    re.IGNORECASE,
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def markdown_files() -> list[Path]:
    paths = [AGENTS, *(GOVERNANCE / name for name in REQUIRED)]
    return [path for path in paths if path.is_file()]


def relative_links(text: str) -> list[str]:
    targets = []
    for target in LINK.findall(text):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        targets.append(target.split("#", 1)[0])
    return [target for target in targets if target]


class GobernanzaTest(unittest.TestCase):
    def test_documentos_requeridos_existen_y_no_estan_vacios(self) -> None:
        self.assertTrue(GUIDE.is_file(), "falta la guía vigente")
        self.assertTrue(AGENTS.is_file(), "falta el índice AGENTS.md")
        for name in REQUIRED:
            with self.subTest(documento=name):
                path = GOVERNANCE / name
                self.assertTrue(path.is_file(), f"falta governance/{name}")
                self.assertTrue(read(path).strip(), f"governance/{name} está vacío")

    def test_indice_declara_la_autoridad_vigente(self) -> None:
        text = read(AGENTS)
        self.assertIn("CLAUDE.md", text)
        self.assertRegex(text, r"(?i)vigente")

    def test_enlaces_relativos_resuelven(self) -> None:
        for path in markdown_files():
            for target in relative_links(read(path)):
                with self.subTest(origen=path.name, destino=target):
                    self.assertTrue(
                        (path.parent / target).resolve().exists(),
                        f"{path.name} enlaza a {target}, que no existe",
                    )

    def test_mapa_de_reglas_no_repite_origenes(self) -> None:
        text = read(GOVERNANCE / "mapa-reglas.md")
        origins = RULE_ROW.findall(text)
        self.assertTrue(origins, "el mapa de reglas no tiene filas PRE-*")
        self.assertEqual(
            len(origins), len(set(origins)), "hay orígenes repetidos en el mapa"
        )

    def test_mapa_de_reglas_no_tiene_huecos(self) -> None:
        text = read(GOVERNANCE / "mapa-reglas.md")
        numbers = sorted(int(rule.split("-", 1)[1]) for rule in RULE_ROW.findall(text))
        self.assertTrue(numbers, "el mapa de reglas no tiene filas PRE-*")
        expected = list(range(numbers[0], numbers[-1] + 1))
        self.assertEqual(numbers, expected, "faltan IDs intermedios en el mapa")

    def test_mapa_cubre_todas_las_secciones_de_la_guia(self) -> None:
        # Piso de cobertura, no prueba de cobertura: si la guía gana una
        # sección y el mapa no la menciona, hay una omisión silenciosa.
        sections = SECTION.findall(read(GUIDE))
        self.assertTrue(sections, "no se encontraron secciones en la guía")
        mapa = read(GOVERNANCE / "mapa-reglas.md")
        missing = [
            section
            for section in sections
            if not re.search(rf"§{section}(?!\d)", mapa)
        ]
        self.assertEqual(missing, [], f"secciones sin fila en el mapa: {missing}")

    def test_glosario_indexa_todos_los_conceptos_de_la_guia(self) -> None:
        # Índice de nombres, no copia de definiciones: la fuente sigue siendo
        # la guía hasta que se apruebe el traslado (T1.1-C04).
        block = CONCEPTS_BLOCK.search(read(GUIDE))
        self.assertIsNotNone(block, "no se encontró la sección de conceptos de la guía")
        esperados = set(CONCEPT_ROW.findall(block.group(1)))
        self.assertTrue(esperados, "la guía no define conceptos")
        indexados = CONCEPT_ROW.findall(read(GOVERNANCE / "glossary.md"))
        self.assertEqual(
            len(indexados), len(set(indexados)), "hay conceptos repetidos en el índice"
        )
        self.assertEqual(
            set(indexados), esperados, "el índice del glosario no coincide con la guía"
        )

    def test_evidencia_cubre_todos_los_criterios(self) -> None:
        # La evidencia no puede omitir un criterio ni inventar estados.
        criterios = sorted(set(CRITERION.findall(read(SPEC))))
        self.assertTrue(criterios, "la especificación no declara criterios T1.1-Cxx")
        self.assertTrue(EVIDENCIA.is_file(), "falta el registro de evidencia de T1.1")
        evidencia = read(EVIDENCIA)
        filas = {
            match.group(1): match.group(2).strip()
            for match in EVIDENCE_ROW.finditer(evidencia)
        }
        self.assertEqual(
            sorted(filas), criterios, "la evidencia y la especificación no coinciden"
        )
        for criterio, estado in filas.items():
            with self.subTest(criterio=criterio):
                self.assertIn(estado, EVIDENCE_STATES, f"estado no admitido: {estado}")

    def test_desgloses_apuntan_a_filas_existentes_y_sin_saltos(self) -> None:
        text = read(GOVERNANCE / "mapa-reglas.md")
        principales = set(RULE_ROW.findall(text))
        bloques = BREAKDOWN.findall(text)
        self.assertTrue(bloques, "no hay bloques de desglose")
        for padre in bloques:
            with self.subTest(desglose=padre):
                self.assertIn(padre, principales, f"{padre} no tiene fila principal")
        sub = SUB_RULE.findall(text)
        self.assertEqual(len(sub), len(set(sub)), "hay sub-reglas repetidas")
        por_padre: dict[str, list[int]] = {}
        for ident in sub:
            padre, numero = ident.rsplit("-", 1)
            por_padre.setdefault(padre, []).append(int(numero))
        for padre, numeros in por_padre.items():
            with self.subTest(padre=padre):
                self.assertEqual(sorted(numeros), list(range(1, len(numeros) + 1)))

    def test_estados_del_mapa_son_de_lista_cerrada(self) -> None:
        text = read(GOVERNANCE / "mapa-reglas.md")
        estados = [estado for estado in RULE_STATUS.findall(text)]
        self.assertTrue(estados, "el mapa no declara estados")
        for estado in estados:
            with self.subTest(estado=estado):
                self.assertIn(estado, ALLOWED_STATUS, f"estado no admitido: {estado}")

    def test_ningun_documento_deroga_la_guia(self) -> None:
        for path in markdown_files():
            with self.subTest(documento=path.name):
                self.assertIsNone(
                    FORBIDDEN_AUTHORITY.search(read(path)),
                    f"{path.name} declara una autoridad no aprobada",
                )

    def test_ningun_documento_afirma_carga_no_verificada(self) -> None:
        for path in markdown_files():
            with self.subTest(documento=path.name):
                self.assertIsNone(
                    FORBIDDEN.search(read(path)),
                    f"{path.name} afirma una carga efectiva de instrucciones no verificada",
                )


if __name__ == "__main__":
    unittest.main()
