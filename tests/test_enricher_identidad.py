"""#565 AC-22: campos de identidad estructurada en las respuestas de CV y AniList."""
from __future__ import annotations

from zascarr.services.anilist import _parse_media
from zascarr.services.comic_vine import ComicVineClient, _parse_issue


def test_cv_issue_lee_personajes_y_sagas_de_la_misma_respuesta():
    issue = _parse_issue({
        "id": 1, "issue_number": "1", "name": "Uno",
        "character_credits": [{"id": 10, "name": "Barry Allen"}, {"id": 11, "name": "Iris West"}],
        "story_arc_credits": [{"id": 20, "name": "Flashpoint"}],
    })
    assert issue.characters == ["Barry Allen", "Iris West"]
    assert issue.story_arcs == ["Flashpoint"]


def test_cv_issue_sin_campos_no_inventa():
    issue = _parse_issue({"id": 2, "issue_number": "2"})
    assert issue.characters == [] and issue.story_arcs == []


def test_anilist_lee_generos_de_la_misma_peticion():
    media = _parse_media({
        "id": 3, "title": {"romaji": "Berserk"}, "genres": ["Action", "Horror"],
    })
    assert media.genres == ["Action", "Horror"]


def test_anilist_sin_campos_no_inventa():
    media = _parse_media({"id": 4, "title": {"romaji": "X"}})
    assert media.genres == []


class _CVFalso(ComicVineClient):
    def __init__(self):
        self.llamadas: list[tuple[str, dict]] = []

    async def _get(self, endpoint: str, params: dict) -> dict:
        self.llamadas.append((endpoint, params))
        if endpoint == "/issues/":
            return {"results": [{"id": 9, "issue_number": "1",
                                 "character_credits": [{"name": "Barry Allen"}],
                                 "story_arc_credits": [{"name": "Flashpoint"}]}]}
        return {"results": [{"id": 5, "name": "Flash"}]}


async def test_cv_pide_personajes_y_sagas_pero_no_genres():
    cliente = _CVFalso()
    await cliente.search_series("Flash")
    await cliente.find_issue(1, "1")
    serie = cliente.llamadas[0][1]["field_list"]
    numero = cliente.llamadas[1][1]["field_list"]
    assert "genres" not in serie
    assert "character_credits" in numero and "story_arc_credits" in numero
    assert "genres" not in numero
