# ruff: noqa: E501
"""BL-VINC1 — vínculos dudosos: señales puras, lotes, series mezcladas y destino (sin base de datos).

Especificación: `docs/design/especificacion-BL-VINC1.md` (aprobada el 2026-11-27). Las señales son
funciones puras sobre `Archivo` (lo que se sabe del archivo vinculado, incluido lo que el matcher de
hoy decide sobre su nombre) y `Ficha` (la serie). Nombres y catálogo sintéticos.
"""
from __future__ import annotations

import itertools

import pytest

from zascarr.services.vinculos_dudosos import Archivo, Ficha, evaluar

_ids = itertools.count(1)


def ficha(titulo: str, inicio: int | None = None, *, volumen: int | None = None,
          numeros: tuple[str, ...] = (), id: str | None = None) -> Ficha:
    return Ficha(id=id or f"s-{titulo}", titulo=titulo, inicio=inicio, volumen=volumen,
                 numeros=frozenset(numeros))


def archivo(ruta: str, serie: Ficha, numero: str, *, p_serie: str | None = None,
            p_numero: str | None = None, p_volumen: int | None = None, p_anual: bool = False,
            elegida: Ficha | None = None, candidatas: tuple[Ficha, ...] = (), clave: str = "",
            origen: str = "filename", issue: str | None = None) -> Archivo:
    n = next(_ids)
    cands = tuple(c.id for c in candidatas)
    if elegida is not None and elegida.id not in cands:
        cands = (elegida.id, *cands)
    return Archivo(id=f"f-{n}", ruta=ruta, serie_id=serie.id, issue_id=issue or f"i-{serie.id}-{numero}",
                   numero=numero, orden=float(numero) if numero.isdigit() else None, origen=origen,
                   p_serie=p_serie, p_numero=p_numero if p_numero is not None else numero,
                   p_volumen=p_volumen, p_anual=p_anual,
                   elegida=elegida.id if elegida else None, candidatas=cands, clave=clave)


def catalogo(*fichas: Ficha) -> dict[str, Ficha]:
    return {f.id: f for f in fichas}


def marcados(informe) -> dict[str, list[str]]:
    """archivo → señales del archivo (solo los que están en un lote)."""
    return {m.archivo_id: [x.senal for x in m.motivos] for lote in informe.lotes for m in lote.archivos}


def en_mezcla(informe) -> set[str]:
    return {e.archivo_id for s in informe.series_mezcladas for e in s.archivos}


# ── R2: otra serie ──

def test_otra_serie_que_encaja_mejor_marca():
    flash = ficha("Flash", 1987)
    otra = ficha("The Flash", 2011)
    a = archivo("/b/The Flash (2011)/The Flash 001.cbz", flash, "1", p_serie="The Flash", elegida=otra)
    inf = evaluar([a], catalogo(flash, otra))
    assert marcados(inf)[a.id] == ["otra_serie"]
    motivo = inf.lotes[0].archivos[0].motivos[0]
    assert "«The Flash»" in motivo.texto


@pytest.mark.parametrize("elegida", ["la_suya", None])
def test_matcher_que_coincide_o_se_abstiene_no_marca(elegida):
    flash = ficha("Flash", 1987)
    a = archivo("/b/Flash (1987)/Flash 001.cbz", flash, "1", p_serie="Flash",
                elegida=flash if elegida else None)
    assert evaluar([a], catalogo(flash)).lotes == []


def test_orden_de_lectura_no_es_un_vinculo_dudoso():
    saga = ficha("Batman R.I.P.", 2008)
    batman = ficha("Batman", 1940)
    # asignado a mano en la posición 3 de la saga; el nombre dice #676 de Batman
    a = archivo("/b/Batman R.I.P/Batman 676.cbz", saga, "3", p_serie="Batman", p_numero="676",
                elegida=batman, origen="manual")
    # el número distinto, sin otra señal, tampoco marca aunque no sea manual
    b = archivo("/b/Batman R.I.P/Batman 677.cbz", saga, "4", p_serie="Batman R.I.P.", p_numero="677")
    assert evaluar([a, b], catalogo(saga, batman)).lotes == []


# ── R3: año, con guarda de título (R6) ──

@pytest.mark.parametrize(("carpeta", "inicio", "marca"), [
    ("Animal Man (2012)", 1989, True),
    ("Animal Man (1990)", 1989, False),     # diferencia de 1
    ("Animal Man", 1989, False),            # la carpeta no dice año
    ("Animal Man (2012)", None, False),     # la serie no tiene año
])
def test_anio_de_carpeta_que_contradice_el_inicio(carpeta, inicio, marca):
    serie = ficha("Animal Man", inicio)
    a = archivo(f"/b/{carpeta}/Animal Man 001.cbz", serie, "1", p_serie="Animal Man")
    assert (a.id in marcados(evaluar([a], catalogo(serie)))) is marca


def test_anio_de_carpeta_de_otro_titulo_no_marca():
    jla = ficha("Justice League of America", 1960)
    a = archivo("/b/Crisis on Infinite Earths (1985)/JLA 244.cbz", jla, "244", p_serie="JLA")
    assert evaluar([a], catalogo(jla)).lotes == []


# ── R4: volumen explícito de la ficha ──

@pytest.mark.parametrize("serie", [
    ficha("Batman", 1939, volumen=1),
    ficha("Batman Vol 1", 1939),
])
def test_volumen_distinto_del_explicito_de_la_ficha_marca(serie):
    a = archivo("/b/Batman Vol. 2/Batman 001.cbz", serie, "1", p_serie="Batman")
    inf = evaluar([a], catalogo(serie))
    assert marcados(inf)[a.id] == ["volumen"]
    assert inf.lotes[0].archivos[0].motivos[0].texto == "Dice vol. 2; la serie es vol. 1"


def test_ficha_sin_volumen_explicito_no_usa_la_mayoria():
    serie = ficha("Superman", 1987)
    vol2 = [archivo(f"/b/Superman Vol. 2/Superman {n:03}.cbz", serie, str(n), p_serie="Superman") for n in range(1, 10)]
    raro = archivo("/b/Superman Vol. 3/Superman 010.cbz", serie, "10", p_serie="Superman")
    inf = evaluar([*vol2, raro], catalogo(serie))
    assert raro.id not in marcados(inf)              # R4 no usa la mayoría como identidad
    assert raro.id in en_mezcla(inf)                 # lo recoge R4b, como evidencia de la serie


def test_volumen_de_carpeta_de_otro_titulo_no_cuenta():
    jla = ficha("Justice League of America", 2006, volumen=2)
    a = archivo("/b/Forever Evil Vol. 1/Justice League of America 007.cbz", jla, "7",
                p_serie="Justice League of America")
    assert evaluar([a], catalogo(jla)).lotes == []


# ── R4b: la serie mezcla volúmenes ──

def _peacemaker(mismo_numero: bool):
    serie = ficha("Peacemaker")
    v1 = [archivo(f"/b/Peacemaker Vol. 1/Peacemaker {n:03}.cbz", serie, str(n), p_serie="Peacemaker") for n in (1, 2)]
    numeros = (1, 2) if mismo_numero else (5, 6)
    # sin carpetas por volumen: el volumen va en el nombre y todo en una carpeta
    if mismo_numero:
        v2 = [archivo(f"/b/Peacemaker/Peacemaker v2 {n:03}.cbz", serie, str(n), p_serie="Peacemaker", p_volumen=2) for n in numeros]
        v1 = [archivo(f"/b/Peacemaker/Peacemaker v1 {n:03}.cbz", serie, str(n), p_serie="Peacemaker", p_volumen=1) for n in (1, 2)]
    else:
        v2 = [archivo(f"/b/Peacemaker Vol. 2/Peacemaker {n:03}.cbz", serie, str(n), p_serie="Peacemaker") for n in numeros]
    return serie, v1, v2


@pytest.mark.parametrize("mismo_numero", [True, False], ids=["mismo_numero", "una_carpeta_por_volumen"])
def test_ficha_que_mezcla_volumenes_marca_los_dos_lados(mismo_numero):
    serie, v1, v2 = _peacemaker(mismo_numero)
    inf = evaluar([*v1, *v2], catalogo(serie))
    assert en_mezcla(inf) == {a.id for a in (*v1, *v2)}


@pytest.mark.parametrize("caso", ["tomos_continuos", "un_volumen_por_archivo"])
def test_volumenes_que_son_tomos_no_marcan(caso):
    serie = ficha("Saga de prueba")
    if caso == "tomos_continuos":
        fs = [archivo(f"/b/Saga de prueba/Saga de prueba Vol 1 #{n}.cbz", serie, str(n), p_serie="Saga de prueba", p_volumen=1) for n in range(1, 4)]
        fs += [archivo(f"/b/Saga de prueba/Saga de prueba Vol 2 #{n}.cbz", serie, str(n), p_serie="Saga de prueba", p_volumen=2) for n in range(4, 7)]
    else:
        fs = [archivo(f"/b/Saga de prueba/Saga de prueba v{n:02}.cbz", serie, str(n), p_serie="Saga de prueba", p_volumen=n) for n in range(1, 6)]
    inf = evaluar(fs, catalogo(serie))
    assert inf.series_mezcladas == [] and inf.lotes == []


def test_mezcla_de_volumenes_es_un_grupo_por_serie():
    gl = ficha("Green Lantern", 2005)
    glc = ficha("Green Lantern Corps Vol. 3", 2011, volumen=3)
    v5 = [archivo(f"/b/Green Lantern Vol. 5/Green Lantern {n:03}.cbz", gl, str(n), p_serie="Green Lantern", clave="green lantern") for n in (1, 2, 3)]
    corps = archivo("/b/Green Lantern Corps Vol. 3/Green Lantern Corps 001.cbz", gl, "1", p_serie="Green Lantern Corps",
                    elegida=glc, clave="green lantern corps", issue=v5[0].issue_id)
    inf = evaluar([*v5, corps], catalogo(gl, glc))
    assert len(inf.series_mezcladas) == 1
    grupo = inf.series_mezcladas[0]
    assert grupo.serie_id == gl.id
    assert {(vol, n) for vol, _carpeta, n in grupo.desglose} == {(5, 3), (3, 1)}
    assert {e.archivo_id for e in grupo.archivos} == {a.id for a in (*v5, corps)}
    # los que solo tienen R4b no forman lote; el que tiene señal propia, sí, con el chip de contexto
    assert set(marcados(inf)) == {corps.id}
    assert inf.lotes[0].archivos[0].serie_mezcla is True


# ── R5: otro título en el número ──

def test_otro_titulo_en_el_numero_marca_solo_el_que_sobra():
    gl = ficha("Green Lantern", 2005)
    buenos = [archivo(f"/b/Green Lantern/Green Lantern {n:03}.cbz", gl, str(n), p_serie="Green Lantern", clave="green lantern") for n in (1, 2, 3)]
    intruso = archivo("/b/Green Lantern/Green Lantern - Recopilatorio 001.cbz", gl, "1", p_serie="Green Lantern",
                      clave="green lantern recopilatorio", issue=buenos[0].issue_id)
    inf = evaluar([*buenos, intruso], catalogo(gl))
    assert marcados(inf) == {intruso.id: ["otro_titulo"]}
    assert inf.lotes[0].archivos[0].motivos[0].texto == "Comparte el #1 con tebeos de otro título"


# ── C12: los casos conocidos de §1, sintéticos ──

def _casos_conocidos():
    gl = ficha("Green Lantern", 2005, numeros=tuple(str(n) for n in range(1, 30)))
    glc3 = ficha("Green Lantern Corps Vol. 3", 2011, volumen=3)
    glc_anual = ficha("Green Lantern Corps Annual", 2013)
    animal89 = ficha("ANIMAL MAN", 1989, numeros=("1", "2", "3"))
    superman = ficha("Superman", 1987)
    batman1 = ficha("Batman Vol 1", 1939)
    batman_anual = ficha("Batman Annual", 1961)
    peace = ficha("Peacemaker")
    rip = ficha("Batman R.I.P.", 2008)
    batman = ficha("Batman", 1940)
    cat = catalogo(gl, glc3, glc_anual, animal89, superman, batman1, batman_anual, peace, rip, batman)
    casos: dict[str, list[Archivo]] = {}
    glv = [archivo(f"/b/Green Lantern (2005)/Green Lantern {n:03}.cbz", gl, str(n), p_serie="Green Lantern", clave="green lantern") for n in (1, 2, 3)]
    casos["green_lantern_corps"] = [
        archivo(f"/b/Green Lantern Corps Vol. 3/Green Lantern Corps {n:03}.cbz", gl, str(n), p_serie="Green Lantern Corps",
                elegida=glc3, candidatas=(glc_anual,), clave="green lantern corps", issue=glv[n - 1].issue_id)
        for n in (1, 2, 3)]
    casos["green_lantern_vol5"] = [archivo(f"/b/Green Lantern Vol. 5/Green Lantern {n:03}.cbz", gl, str(n + 10), p_serie="Green Lantern", clave="green lantern") for n in (1, 2)]
    casos["lemire"] = [archivo(f"/b/Animal Man (2012)/Animal Man {n:03}.cbz", animal89, str(n), p_serie="Animal Man") for n in (1, 2, 3)]
    sup2 = [archivo(f"/b/Superman Vol. 2/Superman {n:03}.cbz", superman, str(n), p_serie="Superman") for n in (1, 2, 3)]
    casos["superman_vol3"] = [archivo(f"/b/Superman Vol. 3/Superman {n:03}.cbz", superman, str(n), p_serie="Superman") for n in (1, 2)]
    casos["batman_vol2"] = [archivo(f"/b/Batman Vol. 2/Batman {n:03}.cbz", batman1, str(n), p_serie="Batman") for n in (1, 2)]
    an1 = [archivo("/b/Batman Vol. 1/Batman Annual 001.cbz", batman_anual, "1", p_serie="Batman Annual", p_anual=True)]
    casos["batman_anuales"] = [archivo("/b/Batman Vol. 2/Batman Annual 001.cbz", batman_anual, "1", p_serie="Batman Annual", p_anual=True, issue=an1[0].issue_id)]
    casos["peacemaker"] = [archivo(f"/b/Peacemaker Vol. {v}/Peacemaker 001.cbz", peace, "1", p_serie="Peacemaker", issue="i-pm-1") for v in (1, 2)]
    lectura = [archivo(f"/b/Batman R.I.P/Batman {n}.cbz", rip, str(i), p_serie="Batman", p_numero=str(n), elegida=batman, origen="manual")
               for i, n in enumerate((676, 677, 678), 1)]
    todos = [*glv, *sup2, *an1, *lectura, *itertools.chain.from_iterable(casos.values())]
    return evaluar(todos, cat), casos, lectura, glc3


@pytest.mark.parametrize("caso", ["green_lantern_corps", "green_lantern_vol5", "lemire", "superman_vol3",
                                  "batman_vol2", "batman_anuales", "peacemaker"])
def test_casos_conocidos_salen_marcados(caso):
    inf, casos, lectura, glc3 = _casos_conocidos()
    salen = set(marcados(inf)) | en_mezcla(inf)
    assert {a.id for a in casos[caso]} <= salen
    assert not ({a.id for a in lectura} & set(marcados(inf)))
    if caso == "green_lantern_corps":
        lote = inf.lotes[0]
        assert {m.archivo_id for m in lote.archivos} == {a.id for a in casos[caso]}
        assert all(sorted(x.senal for x in m.motivos) == ["otra_serie", "otro_titulo"] and m.serie_mezcla
                   for m in lote.archivos)
        assert lote.destino_id == glc3.id


# ── R7: orden y destino ──

def test_orden_por_motivos_y_tamano_del_grupo():
    flash = ficha("Flash", 1987, volumen=1)
    otra = ficha("The Flash", 2011)
    zeta = ficha("Zeta", 1990)
    peace = ficha("Peacemaker")
    # dos señales en un archivo
    doble = archivo("/b/Flash Vol. 2/The Flash 001.cbz", flash, "1", p_serie="The Flash", elegida=otra)
    # una señal, pero tres archivos
    tres = [archivo(f"/b/Flash Vol. 3/Flash {n:03}.cbz", flash, str(n), p_serie="Flash") for n in (2, 3, 4)]
    # una señal, un archivo, título que va antes
    uno = archivo("/b/Zeta (2020)/Zeta 001.cbz", zeta, "1", p_serie="Zeta")
    mezcla = [archivo(f"/b/Peacemaker Vol. {v}/Peacemaker 001.cbz", peace, "1", p_serie="Peacemaker", issue="i-p") for v in (1, 2)]
    inf = evaluar([uno, *tres, doble, *mezcla], catalogo(flash, otra, zeta, peace))
    orden = [(x.carpeta.rsplit("/", 1)[-1], len(x.archivos)) for x in inf.lotes]
    assert orden == [("Flash Vol. 2", 1), ("Flash Vol. 3", 3), ("Zeta (2020)", 1)]
    assert [s.serie_id for s in inf.series_mezcladas] == [peace.id]    # va aparte, detrás


def _lote_corps(*candidatas: Ficha, elegida: Ficha | None = None, volumen_carpeta: int | None = 3):
    gl = ficha("Green Lantern", 2005)
    carpeta = f"Green Lantern Corps Vol. {volumen_carpeta}" if volumen_carpeta else "Green Lantern Corps"
    fs = [archivo(f"/b/{carpeta}/Green Lantern Corps {n:03}.cbz", gl, str(n), p_serie="Green Lantern Corps",
                  elegida=elegida, candidatas=candidatas) for n in (1, 2)]
    return gl, fs


@pytest.mark.parametrize("caso", ["una", "dos", "cero"])
def test_destino_solo_si_es_compatible_con_todo_el_grupo(caso):
    glc3 = ficha("Green Lantern Corps Vol. 3", 2011, volumen=3)
    glc3b = ficha("Green Lantern Corps Vol. 3", 2011, volumen=3, id="s-otra-glc3")
    cands = {"una": (glc3,), "dos": (glc3, glc3b), "cero": ()}[caso]
    gl, fs = _lote_corps(*cands, elegida=ficha("Green Lantern Corps", 1990, id="s-glc-1990") if caso == "cero" else glc3)
    inf = evaluar(fs, catalogo(gl, glc3, glc3b, ficha("Green Lantern Corps", 1990, id="s-glc-1990")))
    lote = inf.lotes[0]
    if caso == "una":
        assert lote.destino_id == glc3.id and lote.destino_sin_numeros is True
    else:
        assert lote.destino_id is None


@pytest.mark.parametrize("contradice", ["volumen", "anio", "anual", "numero"])
def test_candidata_incompatible_con_un_archivo_no_es_destino(contradice):
    gl = ficha("Green Lantern", 2005)
    cand = {
        "volumen": ficha("Green Lantern Corps Vol. 2", 1987, volumen=2),
        "anio": ficha("Green Lantern Corps", 1990),
        "anual": ficha("Green Lantern Corps Annual", 2011, volumen=3),
        "numero": ficha("Green Lantern Corps", 2011, volumen=3, numeros=("7", "8")),
    }[contradice]
    carpeta = "Green Lantern Corps (2011)" if contradice == "anio" else "Green Lantern Corps Vol. 3"
    fs = [archivo(f"/b/{carpeta}/Green Lantern Corps {n:03}.cbz", gl, str(n), p_serie="Green Lantern Corps",
                  elegida=cand) for n in (1, 2)]
    lote = evaluar(fs, catalogo(gl, cand)).lotes[0]
    assert lote.destino_id is None


def test_mezcla_de_volumenes_no_propone_destino():
    superman = ficha("Superman", 1987)
    novela = ficha("SUPERMAN")
    fs = [archivo(f"/b/Superman Vol. {v}/Superman 001.cbz", superman, "1", p_serie="Superman",
                  candidatas=(novela,), issue="i-s1") for v in (2, 3)]
    inf = evaluar(fs, catalogo(superman, novela))
    assert inf.lotes == []
    assert not hasattr(inf.series_mezcladas[0], "destino_id")


def test_homonima_vacia_no_es_destino():
    gl = ficha("Green Lantern", 2005)
    vacia = ficha("Green Lantern Corps")              # sin año, sin volumen y sin números
    gl, fs = _lote_corps(elegida=vacia)
    lote = evaluar(fs, catalogo(gl, vacia)).lotes[0]
    assert lote.destino_id is None


def test_titulo_y_volumen_explicitos_bastan_sin_numeros():
    glc3 = ficha("Green Lantern Corps Vol. 3", 2011, volumen=3)
    gl, fs = _lote_corps(elegida=glc3)
    lote = evaluar(fs, catalogo(gl, glc3)).lotes[0]
    assert lote.destino_id == glc3.id
    assert lote.destino_titulo == "Green Lantern Corps Vol. 3"
    assert lote.destino_sin_numeros is True


@pytest.mark.parametrize(("cand", "carpeta", "destino"), [
    (ficha("Green Lantern Corps", numeros=("1", "2")), "Green Lantern Corps", False),          # solo título y número
    (ficha("Green Lantern Corps Vol. 3", volumen=3), "Green Lantern Corps Vol. 3", True),     # título y volumen
    (ficha("Green Lantern Corps", 2011), "Green Lantern Corps (2011)", True),                 # título y año
    (ficha("Green Lantern Corps", 2012), "Green Lantern Corps (2011)", True),                 # año a ±1
    (ficha("Green Lantern Corps Quarterly", 2011), "Green Lantern Corps (2011)", False),      # prefijo no es igual
], ids=["titulo_y_numero", "titulo_y_volumen", "titulo_y_anio", "anio_a_uno", "prefijo"])
def test_identidad_editorial_positiva(cand, carpeta, destino):
    gl = ficha("Green Lantern", 2005)
    fs = [archivo(f"/b/{carpeta}/Green Lantern Corps {n:03}.cbz", gl, str(n), p_serie="Green Lantern Corps",
                  elegida=cand) for n in (1, 2)]
    lote = evaluar(fs, catalogo(gl, cand)).lotes[0]
    assert (lote.destino_id == cand.id) is destino


# ── C21: la carpeta no es un veto ──

def test_anual_en_la_carpeta_de_su_serie_madre_no_marca():
    batman = ficha("Batman", 1940)
    anual = ficha("Batman Annual", 1961)
    madre = [archivo(f"/b/Batman/Batman {n:03}.cbz", batman, str(n), p_serie="Batman") for n in (1, 2, 3)]
    a = archivo("/b/Batman/Batman Annual 001.cbz", anual, "1", p_serie="Batman Annual", p_anual=True, elegida=anual)
    assert evaluar([*madre, a], catalogo(batman, anual)).lotes == []
