# ruff: noqa: E501, UP031
"""Siembra datos SINTÉTICOS para la línea base de la UI (V0). Se ejecuta DENTRO de la imagen:

    docker compose run --rm -T zascarr python - < docs/design/ui-baseline/sembrar.py

Nada de aquí procede de la biblioteca de nadie: títulos inventados y portadas generadas con
Pillow. Desactiva las fuentes externas de metadatos en Ajustes ANTES de que arranque la app
(el enricher llamaría a AniList, Tebeosfera y GCD, que no piden clave).
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw

from zascarr.database import async_session_factory, engine
from zascarr.models import (
    ComicTradition,
    File,
    FileFormat,
    Issue,
    IssueFormat,
    Publisher,
    Series,
    Wishlist,
    WishlistStatus,
)
from zascarr.services.library_audit import LibraryAudit
from zascarr.services.runtime_settings import RuntimeSettingsService

BIBLIOTECA = Path("/media/library")
AHORA = datetime.now(UTC)


def portada(titulo: str, color: tuple[int, int, int]) -> bytes:
    img = Image.new("RGB", (400, 600), color)
    d = ImageDraw.Draw(img)
    d.rectangle((16, 16, 384, 584), outline=(20, 20, 24), width=6)
    d.text((32, 40), titulo, fill=(20, 20, 24))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def crear_cbz(ruta: Path, titulo: str, color: tuple[int, int, int]) -> tuple[int, str]:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_STORED) as z:
        z.writestr("001.png", portada(titulo, color))
        z.writestr("002.png", portada(titulo + " (pág. 2)", color))
    datos = ruta.read_bytes()
    return len(datos), hashlib.sha256(datos).hexdigest()


async def main() -> None:
    async with async_session_factory() as db:
        # Aislamiento: nada de red hacia fuentes externas.
        await RuntimeSettingsService(db).save({
            "comicvine_enabled": False, "anilist_enabled": False,
            "tebeosfera_enabled": False, "gcd_enabled": False,
        })

        editorial = Publisher(name="Editorial de Prueba", country="España")
        db.add(editorial)
        await db.flush()

        def serie(titulo, tradicion, anio, total, descr):
            s = Series(title=titulo, tradition=tradicion, start_year=anio, total_issues=total,
                       description=descr, publisher_id=editorial.id,
                       enrichment_attempted_at=AHORA)
            db.add(s)
            return s

        guardianes = serie("Los Guardianes del Alba", ComicTradition.TEBEO, 2010, 12,
                           "Serie inventada para la línea base de la UI.")
        cobalto = serie("Mundo Cobalto", ComicTradition.AMERICAN, 2015, 24,
                        "Otra serie inventada, con duplicados en disco.")
        faro = serie("Saga del Faro", ComicTradition.MANGA, 2019, 10, "Sin ficheros todavía.")
        await db.flush()

        async def registrar(s: Series, numero: str, fmt: IssueFormat, color, con_fichero: bool):
            iss = Issue(series_id=s.id, issue_number=numero, format=fmt, sort_order=float(numero),
                        title=f"{s.title} nº {numero}", locked_fields=[])
            db.add(iss)
            await db.flush()
            if con_fichero:
                ruta = BIBLIOTECA / f"{s.title} ({s.start_year})" / f"{s.title} {numero.zfill(3)}.cbz"
                tam, h = crear_cbz(ruta, f"{s.title} #{numero}", color)
                db.add(File(issue_id=iss.id, file_path=str(ruta), file_name=ruta.name,
                            file_format=FileFormat.CBZ, file_size_bytes=tam, sha256_hash=h,
                            original_sha256=h, metadata_={"match_status": "matched"}))
            return iss

        for n in ("1", "2", "3", "4"):
            await registrar(guardianes, n, IssueFormat.SINGLE_ISSUE, (240, 197, 0), True)
        await registrar(guardianes, "5", IssueFormat.SINGLE_ISSUE, (240, 197, 0), False)
        # Número 12 como GRAPA: la prueba de colisión de ediciones (B15) intentará asignarle
        # un ómnibus con el mismo número.
        await registrar(guardianes, "12", IssueFormat.SINGLE_ISSUE, (240, 197, 0), False)
        for n in ("1", "2", "3"):
            await registrar(cobalto, n, IssueFormat.SINGLE_ISSUE, (13, 155, 214), True)
        await db.flush()

        # Duplicado exacto en disco (para el informe de «Mi biblioteca»).
        origen = BIBLIOTECA / "Mundo Cobalto (2015)" / "Mundo Cobalto 001.cbz"
        copia = BIBLIOTECA / "Mundo Cobalto (copia de seguridad)" / "Mundo Cobalto 001.cbz"
        copia.parent.mkdir(parents=True, exist_ok=True)
        copia.write_bytes(origen.read_bytes())

        # Pendientes (sin clasificar): con sugerencia, sin sugerencia, con número y sin número.
        def pendiente(nombre, color, candidato=None):
            ruta = BIBLIOTECA / "_Unsorted" / nombre
            tam, h = crear_cbz(ruta, nombre[:28], color)
            meta = {"match_status": "unsorted"}
            if candidato:
                meta["candidates"] = [{
                    "series_id": str(candidato.id), "title": candidato.title,
                    "start_year": candidato.start_year, "score": 0.88}]
            db.add(File(file_path=str(ruta), file_name=nombre, file_format=FileFormat.CBZ,
                        file_size_bytes=tam, sha256_hash=h, original_sha256=h, metadata_=meta))

        pendiente("Los Guardianes del Alba Omnigold 12 [CRG].cbz", (210, 120, 40), guardianes)
        pendiente("Los Guardianes del Alba Omnigold 13 [CRG].cbz", (210, 120, 40), guardianes)
        pendiente("Los Guardianes del Alba (21-35) Pack especial [CRG].cbz", (200, 90, 90), guardianes)
        pendiente("Mundo Cobalto - Edicion Integral 01 [Equipo X].cbz", (60, 140, 190), cobalto)
        pendiente("Saga del Faro por un autor (by Alguien) [MQ].cbz", (90, 170, 120))
        pendiente("Tomo suelto sin identificar 7.cbz", (150, 150, 160))

        # Deseados: estados variados y duplicados.
        db.add_all([
            Wishlist(series_id=faro.id, status=WishlistStatus.WANTED, priority=3),
            Wishlist(series_id=faro.id, status=WishlistStatus.WANTED, priority=3),
            Wishlist(series_id=guardianes.id, status=WishlistStatus.SEARCHING, priority=5,
                     last_searched_at=AHORA),
            Wishlist(series_id=cobalto.id, status=WishlistStatus.FAILED, priority=5,
                     last_error="Prowlarr no está configurado."),
            Wishlist(series_id=cobalto.id, status=WishlistStatus.DOWNLOADING, priority=5,
                     download_ref="abc123", download_backend="transmission"),
        ])
        await db.commit()

    async with async_session_factory() as db:
        await LibraryAudit(db).run()
        await db.commit()
    await engine.dispose()
    print("sembrado")


asyncio.run(main())
