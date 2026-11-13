"""Pool inicial de etiquetas para una instalación nueva (BL-ETQ, 2026-11-13).

No asigna nada: siembra un vocabulario curado y ofrece ideas en la ficha. Las
fuentes (AniList/ComicInfo) siguen creando sus propios tags con su procedencia.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import Tag, series_tags
from zascarr.services.etiquetas import NAMESPACE, normalize_tag

GRUPOS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Género y tono", (
        "superhéroes", "noir", "ciencia ficción", "fantasía", "terror", "misterio",
        "policíaco", "bélico", "western", "romance", "comedia", "drama",
        "aventura", "histórico", "cyberpunk", "distopía",
    )),
    ("Tema", (
        "viajes en el tiempo", "multiverso", "magia", "escuela", "instituto",
        "vigilantes", "crimen organizado", "mafia", "piratas", "vampiros",
        "zombis", "robots", "inteligencia artificial", "alienígenas", "mitología",
        "artes marciales", "deportes", "música", "cocina", "política",
        "investigación", "supervivencia", "amistad", "familia", "duelo",
        "identidad", "poderes", "corrupción",
    )),
    ("Ambientación", (
        "ciudad", "espacio", "futuro", "medieval", "victoriano", "años 20",
        "años 80", "japón", "estados unidos", "europa",
    )),
    ("Tono y estructura", (
        "thriller psicológico", "comedia negra", "coming of age", "road trip",
        "post-apocalíptico", "space opera",
    )),
)

ETIQUETAS_INICIALES: tuple[str, ...] = tuple(
    nombre for _grupo, nombres in GRUPOS for nombre in nombres)

#: Las que se enseñan como ideas; el resto queda en el autocompletado.
DESTACADAS: tuple[str, ...] = (
    "superhéroes", "noir", "ciencia ficción", "fantasía", "terror", "misterio",
    "aventura", "romance", "comedia", "viajes en el tiempo", "magia",
    "crimen organizado",
)


async def ideas_para_empezar(db: AsyncSession, series_id: UUID,
                             limite: int = 12) -> list[Tag]:
    """Tags del pool que la serie aún no tiene, en el orden curado y acotados."""
    normalizados = [normalize_tag(n) for n in DESTACADAS]
    orden = {n: i for i, n in enumerate(normalizados)}
    filas = (await db.execute(
        select(Tag)
        .where(Tag.namespace == NAMESPACE, Tag.name_norm.in_(normalizados))
        .where(Tag.id.not_in(
            select(series_tags.c.tag_id).where(
                series_tags.c.series_id == series_id,
                series_tags.c.oculta.is_(False))))
    )).scalars().all()
    filas = sorted(filas, key=lambda t: orden.get(t.name_norm or "", 999))
    return filas[:max(1, min(limite, len(DESTACADAS)))]
