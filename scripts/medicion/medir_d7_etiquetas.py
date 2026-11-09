#!/usr/bin/env python3
"""Medición D-7 (#402): uso real de etiquetas y CBZ con <Tags>/<Genre> (solo lectura).

Ejecutar DENTRO del contenedor de la app (tiene BD y biblioteca montadas):

    docker compose exec -T zascarr python - < scripts/medicion/medir_d7_etiquetas.py

o desde el host con `scripts/medicion/medir_d7_etiquetas.sh` (hace lo mismo).

No escribe nada: ni en la base de datos ni en disco. Los CBZ se abren en modo
lectura y solo se lee `ComicInfo.xml` (≤ 1 MiB, el mismo tope que el triaje);
los `.cbr` (RAR) se cuentan aparte y **no se leen** aquí. Los topes de
`<Tags>`/`<Genre>` son los de ETQ2 (`_leer_lista`), para que la medición mida
exactamente lo que el importador aplicaría.

Salida: resumen legible; con `--json`, un JSON para pegar en la incidencia.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

from zascarr.config import get_settings
from zascarr.core.comicinfo_write import MAX_COMICINFO_BYTES
from zascarr.core.importer_triage import (
    MAX_TOKENS_TOTAL,
    _leer_lista,
)

#: Cuántos ficheros se recuerdan para el resumen de errores (sin rutas completas: solo nombre).
_MAX_EJEMPLOS = 5


@dataclass
class Medicion:
    biblioteca: str = ""
    cbz: int = 0
    cbr: int = 0
    con_comicinfo: int = 0
    con_tags: int = 0
    con_genero: int = 0
    con_ambos: int = 0
    valores_tags: int = 0
    valores_genero: int = 0
    sin_comicinfo: int = 0
    xml_roto: int = 0
    no_zip: int = 0
    comicinfo_grande: int = 0
    ejemplos_error: list[str] = field(default_factory=list)
    tags_totales: int = 0
    asignaciones: int = 0
    visibles: int = 0
    ocultas: int = 0
    series_con_etiquetas: int = 0
    etiquetas_en_uso: int = 0
    por_fuente: dict[str, int] = field(default_factory=dict)
    top: list[tuple[str, int]] = field(default_factory=list)
    series_con_generos: int = 0
    generos_asignados: int = 0
    personajes_asignados: int = 0

    def a_dict(self) -> dict:
        return {
            "biblioteca": self.biblioteca,
            "cbz": self.cbz, "cbr": self.cbr,
            "comicinfo": {
                "presente": self.con_comicinfo,
                "con_tags": self.con_tags,
                "con_genero": self.con_genero,
                "con_ambos": self.con_ambos,
                "valores_tags": self.valores_tags,
                "valores_genero": self.valores_genero,
            },
            "errores": {
                "sin_comicinfo": self.sin_comicinfo, "xml_roto": self.xml_roto,
                "no_zip": self.no_zip, "comicinfo_grande": self.comicinfo_grande,
                "ejemplos": self.ejemplos_error,
            },
            "etiquetas": {
                "tags_totales": self.tags_totales,
                "asignaciones": self.asignaciones,
                "visibles": self.visibles, "ocultas": self.ocultas,
                "series_con_etiquetas": self.series_con_etiquetas,
                "etiquetas_en_uso": self.etiquetas_en_uso,
                "por_fuente": self.por_fuente,
                "top": self.top,
            },
            "identidad_estructurada": {
                "series_con_generos": self.series_con_generos,
                "generos_asignados": self.generos_asignados,
                "personajes_asignados": self.personajes_asignados,
            },
        }


def _comicinfo_de(ruta: Path) -> tuple[bytes | None, str]:
    """`ComicInfo.xml` de un CBZ, o (None, causa). Solo lectura, con el tope del triaje."""
    try:
        with zipfile.ZipFile(ruta) as z:
            for nombre in z.namelist():
                if nombre.lower() == "comicinfo.xml":
                    info = z.getinfo(nombre)
                    if info.file_size > MAX_COMICINFO_BYTES:
                        return None, "grande"
                    return z.read(nombre), "ok"
            return None, "sin_comicinfo"
    except zipfile.BadZipFile:
        return None, "no_zip"
    except (OSError, RuntimeError):
        return None, "ilegible"


def _valores(root: ElementTree.Element) -> tuple[list[str], list[str]]:
    tags = _leer_lista(root, "Tags", avisos=[], restantes=MAX_TOKENS_TOTAL)
    genero = _leer_lista(root, "Genre", avisos=[], restantes=MAX_TOKENS_TOTAL - len(tags))
    return tags, genero


def medir_biblioteca(m: Medicion, raiz: Path) -> None:
    m.biblioteca = str(raiz)
    if not raiz.is_dir():
        print(f"No existe la biblioteca {raiz}; se omite la parte de ficheros.", file=sys.stderr)
        return
    vistos = 0
    for carpeta, _sub, nombres in os.walk(raiz):
        for nombre in nombres:
            ext = os.path.splitext(nombre)[1].lower()
            if ext == ".cbr":
                m.cbr += 1
                continue
            if ext != ".cbz":
                continue
            m.cbz += 1
            vistos += 1
            if vistos % 500 == 0:
                print(f"  … {vistos} CBZ mirados", file=sys.stderr)
            datos, causa = _comicinfo_de(Path(carpeta) / nombre)
            if causa == "sin_comicinfo":
                m.sin_comicinfo += 1
                continue
            if causa != "ok":
                campo = {"grande": "comicinfo_grande", "no_zip": "no_zip"}.get(causa, "xml_roto")
                setattr(m, campo, getattr(m, campo) + 1)
                if len(m.ejemplos_error) < _MAX_EJEMPLOS:
                    m.ejemplos_error.append(f"{nombre}: {causa}")
                continue
            try:
                root = ElementTree.fromstring(datos)
            except ElementTree.ParseError:
                m.xml_roto += 1
                if len(m.ejemplos_error) < _MAX_EJEMPLOS:
                    m.ejemplos_error.append(f"{nombre}: XML roto")
                continue
            tags, genero = _valores(root)
            m.con_comicinfo += 1
            if tags:
                m.con_tags += 1
                m.valores_tags += len(tags)
            if genero:
                m.con_genero += 1
                m.valores_genero += len(genero)
            if tags and genero:
                m.con_ambos += 1


async def medir_bd(m: Medicion) -> None:
    from sqlalchemy import text

    from zascarr.database import async_session_factory
    async with async_session_factory() as s:
        async def uno(sql: str) -> int:
            return int((await s.execute(text(sql))).scalar() or 0)

        m.tags_totales = await uno("SELECT count(*) FROM tags WHERE namespace = 'etiqueta'")
        m.asignaciones = await uno("SELECT count(*) FROM series_tags")
        m.visibles = await uno("SELECT count(*) FROM series_tags WHERE oculta = false")
        m.ocultas = await uno("SELECT count(*) FROM series_tags WHERE oculta = true")
        m.series_con_etiquetas = await uno(
            "SELECT count(DISTINCT series_id) FROM series_tags WHERE oculta = false")
        m.etiquetas_en_uso = await uno(
            "SELECT count(DISTINCT tag_id) FROM series_tags WHERE oculta = false")
        m.por_fuente = {
            str(fuente): int(total) for fuente, total in (await s.execute(text(
                "SELECT source, count(*) FROM series_tags WHERE oculta = false GROUP BY source"
            ))).all()
        }
        m.top = [
            (str(nombre), int(total)) for nombre, total in (await s.execute(text(
                "SELECT t.name, count(*) AS total FROM series_tags st "
                "JOIN tags t ON t.id = st.tag_id "
                "WHERE st.oculta = false GROUP BY t.id, t.name "
                "ORDER BY total DESC, t.name LIMIT 10"
            ))).all()
        ]
        m.series_con_generos = await uno(
            "SELECT count(DISTINCT series_id) FROM series_genres")
        m.generos_asignados = await uno("SELECT count(*) FROM series_genres")
        m.personajes_asignados = await uno("SELECT count(*) FROM issue_characters")


def imprimir(m: Medicion) -> None:
    total_cbz = m.cbz
    pct = (m.con_comicinfo * 100 // total_cbz) if total_cbz else 0
    print("=== D-7: uso real de etiquetas (lectura) ===")
    print(f"Biblioteca: {m.biblioteca or '(no medida en esta ejecución)'}")
    print(f"CBZ (ZIP): {m.cbz} · CBR (RAR, no leídos aquí): {m.cbr}")
    print(f"ComicInfo.xml presente: {m.con_comicinfo} ({pct}%)")
    print(f"  con <Tags>: {m.con_tags} · con <Genre>: {m.con_genero} · con ambos: {m.con_ambos}")
    print(f"  valores: <Tags> {m.valores_tags} · <Genre> {m.valores_genero}")
    print(f"  sin ComicInfo: {m.sin_comicinfo} · XML roto: {m.xml_roto} · "
          f"no es ZIP: {m.no_zip} · ComicInfo > 1 MiB: {m.comicinfo_grande}")
    if m.ejemplos_error:
        print(f"  ejemplos: {', '.join(m.ejemplos_error)}")
    print("=== Etiquetas en la base de datos ===")
    print(f"Etiquetas (espacio «etiqueta»): {m.tags_totales}")
    print(f"Asignaciones: {m.asignaciones} (visibles {m.visibles}, ocultas {m.ocultas})")
    print(f"Series con al menos una etiqueta: {m.series_con_etiquetas} · "
          f"etiquetas distintas en uso: {m.etiquetas_en_uso}")
    if m.por_fuente:
        print("Por fuente (visibles): " + ", ".join(
            f"{fuente}={total}" for fuente, total in m.por_fuente.items()))
    if m.top:
        print("Top: " + ", ".join(f"{nombre} ({total})" for nombre, total in m.top))
    print("=== Identidad estructurada (ETQ3) ===")
    print(f"Series con géneros: {m.series_con_generos} · asignaciones de género: "
          f"{m.generos_asignados} · personajes de número: {m.personajes_asignados}")
    print("=== Lectura para D-7 ===")
    print(f"- Etiquetas usadas de verdad: {m.series_con_etiquetas} series con "
          f"{m.etiquetas_en_uso} etiquetas distintas ({m.asignaciones} asignaciones).")
    con_listas = m.con_tags + m.con_genero - m.con_ambos
    porcentaje = (con_listas * 100 // total_cbz) if total_cbz else 0
    print(f"- CBZ con <Tags>/<Genre>: {con_listas} de {total_cbz} ({porcentaje}%).")
    print("- Criterio D-7: si hay datos que leer (CBZ con <Tags>) y uso real, ETQ3 se abre;"
          " si no, el MVP se puede cerrar con 1a+1b+ETQ2.")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Medición D-7 (#402), solo lectura.")
    parser.add_argument("--json", action="store_true", help="salida JSON")
    parser.add_argument("--solo-ficheros", action="store_true", help="solo el disco")
    parser.add_argument("--solo-bd", action="store_true", help="solo la base de datos")
    parser.add_argument("--biblioteca", type=Path, help="ruta de la biblioteca (defecto: settings)")
    args = parser.parse_args()

    m = Medicion()
    if not args.solo_bd:
        raiz = args.biblioteca or get_settings().library_path
        print("Midiendo CBZ/CBR (solo lectura)…", file=sys.stderr)
        medir_biblioteca(m, Path(raiz))
    if not args.solo_ficheros:
        await medir_bd(m)
    elif not m.biblioteca:
        m.biblioteca = "(no medida: --solo-ficheros)"
    if args.json:
        print(json.dumps(m.a_dict(), ensure_ascii=False, indent=2))
    else:
        imprimir(m)


if __name__ == "__main__":
    asyncio.run(main())
