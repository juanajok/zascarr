from zascarr.services.asociacion_automatica import (
    editorial_compatible, normalizar_titulo, puntuar,
)


def test_normaliza_titulo_articulos_volumen_y_edicion():
    assert normalizar_titulo("The Flash Annual") == "flash annual"
    assert normalizar_titulo("Action Comics Vol. 2") == "action comics"
    assert normalizar_titulo("100 Bullets Integral") == normalizar_titulo("100 Bullets")
    assert normalizar_titulo("ESPADA DEL INMORTAL, LA") == normalizar_titulo("LA ESPADA DEL INMORTAL")


def test_editorial_por_contencion():
    assert editorial_compatible("Image Comics", "Image")
    assert editorial_compatible("DC", "DC Comics")
    assert not editorial_compatible("Cross Cult", "Image")
    assert editorial_compatible(None, "DC Comics")


def test_numero_como_subconjunto_no_penaliza():
    p = puntuar(titulo_local="Action Comics Vol. 2", anio_local=2011, numeros_local=30,
                editorial_local="DC Comics", titulo_fuente="Action Comics", anio_fuente=2011,
                numeros_fuente=57, editorial_fuente="DC Comics")
    assert p.numeros == 1.0
    assert p.nivel == "aplicable"


def test_edicion_recopilatoria_no_penaliza_titulo():
    p = puntuar(titulo_local="100 Bullets Integral", anio_local=None, numeros_local=4,
                editorial_local=None, titulo_fuente="100 Bullets", anio_fuente=1999,
                numeros_fuente=100, editorial_fuente="DC Comics",
                archivos=["100 Bullets Integral - Tomo 1 (1999).cbz"])
    assert p.titulo == 1.0
    assert p.anio == 1.0
    assert p.nivel != "descartar"


def test_anio_distinto_y_titulo_parecido_no_bastan():
    p = puntuar(titulo_local="Batgirl", anio_local=2011, numeros_local=30,
                editorial_local="DC Comics", titulo_fuente="Batgirl", anio_fuente=2025,
                numeros_fuente=25, editorial_fuente="DC Comics")
    assert p.nivel != "aplicable"
    assert any("año" in m for m in p.motivos)


def test_titulo_generico_con_anio_y_numeros_iguales():
    p = puntuar(titulo_local="Batman: Odyssey", anio_local=2010, numeros_local=7,
                editorial_local="DC Comics", titulo_fuente="Batman: Odyssey", anio_fuente=2010,
                numeros_fuente=6, editorial_fuente="DC Comics")
    assert p.total >= 0.95 and p.nivel == "aplicable"
