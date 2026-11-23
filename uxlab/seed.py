"""Semilla sintética para una BD dedicada. NUNCA ejecutar contra producción."""
import asyncio
import io
import json
import os
import struct
import uuid
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from zascarr.database import async_session_factory
from zascarr.models import (
    Character, ComicTradition, Creator, File, FileFormat,
    Genre, Issue, IssueCreator, Publisher, ReadingProgress,
    ReadingStatus, Series, Tag, issue_characters, series_genres,
    series_tags,
)

CATALOG = Path("/uxlab/catalog.json")
LIBRARY = Path("/media/library")
PREFIX = "UXLAB-"

def png(rgb):
    # PNG RGB de 24 x 32 px, generado solo con la librería estándar.
    w, h = 24, 32
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))

def write_cbz(path, ix):
    palette = [(35, 77, 155), (193, 96, 43), (92, 139, 87), (136, 76, 158)]
    color = palette[ix % len(palette)]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for page in range(1, 7):
            archive.writestr(f"{page:03d}.png", png(color))

async def main():
    # Cerrojazo: las semillas exigen base local llamada exactamente zascarr
    # y nombre de host postgres (no URLs externas ni servidores ajenos).
    if os.environ.get("LIBRARY_PATH") != str(LIBRARY):
        raise RuntimeError("UXLab solo admite LIBRARY_PATH=/media/library")
    if os.environ.get("DATABASE_URL"):
        raise RuntimeError("No pasar DATABASE_URL al sembrador UXLab")
    if not os.environ.get("ZASCARR_DB_PASSWORD"):
        raise RuntimeError("Falta contraseña de BD aislada")
    LIBRARY.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    async with async_session_factory() as session:
        already = await session.scalar(
            select(Series.id).where(Series.title == PREFIX + "Nebulosa de Papel")
        )
        if already:
            raise RuntimeError("BD no vacía: detener en vez de reutilizar estado anterior")
        for ix, item in enumerate(catalog["series"]):
            pub = Publisher(name=PREFIX + item["publisher"] + "-" + item["key"])
            genre = Genre(name=PREFIX + item["genre"] + "-" + item["key"])
            tag = Tag(name=item["tag"], namespace="etiqueta")
            author = Creator(name=item["creator"])
            character = Character(name=item["character"])
            session.add_all([pub, genre, tag, author, character])
            await session.flush()
            serie = Series(
                title=PREFIX + item["title"],
                tradition=ComicTradition(item["tradition"]),
                publisher_id=pub.id,
                start_year=2026,
                total_issues=1,
                favorite=False,
            )
            session.add(serie)
            await session.flush()
            issue = Issue(series_id=serie.id, issue_number="1", volume=1, page_count=6)
            session.add(issue)
            await session.flush()
            path = LIBRARY / f"{item['key']}-001.cbz"
            write_cbz(path, ix)
            file = File(
                issue_id=issue.id, file_path=str(path), file_name=path.name,
                file_format=FileFormat.CBZ, is_missing=False,
                file_size_bytes=path.stat().st_size,
            )
            session.add(file)
            await session.flush()
            await session.execute(series_genres.insert().values(
                series_id=serie.id, genre_id=genre.id))
            await session.execute(series_tags.insert().values(
                series_id=serie.id, tag_id=tag.id, source="manual"))
            await session.execute(issue_characters.insert().values(
                issue_id=issue.id, character_id=character.id, is_main=True))
            session.add(IssueCreator(issue_id=issue.id, creator_id=author.id, role="writer"))
            if item["reading_page"]:
                session.add(ReadingProgress(
                    issue_id=issue.id, file_id=file.id, status=ReadingStatus.READING,
                    current_page=item["reading_page"],
                    started_at=datetime.now(timezone.utc),
                    last_read_at=datetime.now(timezone.utc),
                ))
        await session.commit()
    print(f"UXLab fixture: {len(catalog['series'])} series, CBZ locales y progreso generado")

if __name__ == "__main__":
    asyncio.run(main())
