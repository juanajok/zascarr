"""D5 track español: parseo de Norma y Panini (sin red)."""
from __future__ import annotations

from datetime import date

from zascarr.services.novedades_es import parsear_norma, parsear_panini

NORMA = '''
<section class="plan-editorial">
<div class="item"><div class="container"><h3>A LA VENTA EL 20 DE NOVIEMBRE</h3>
<div class="col-12 ul-alone"><ul>
<li><span>Blade Runner 2019 [Ed. Integral]</span></li>
<li><span>NO/ONE</span></li>
</ul></div></div></div>
<div class="item"><div class="container"><h3>YA A LA VENTA</h3>
<ul><li>Esto no debe salir</li></ul></div></div>
</section>
'''

PANINI = '''
<ol class="products list items product-items">
<li class="item product product-item">
  <div class="product-item-info" id="product-item-info_1">
    <a href="https://www.panini.es/shp_esp_es/biblioteca-conan-24.html"
       class="product link product-item-link"><span class="product-image-container">img</span></a>
    <h3 class="product name product-item-name">
      <a class="product-item-link" href="https://www.panini.es/shp_esp_es/biblioteca-conan-24.html">
        Biblioteca Conan 24</a>
    </h3>
    <div class="product attribute type product-item-attribute-release-date">
      <small>26/11/26</small>
    </div>
  </div>
</li>
<li class="item product product-item">
  <div class="product-item-info">
    <a href="https://www.panini.es/shp_esp_es/otro.html"
       class="product link product-item-link"><span class="product-image-container">img</span></a>
    <h3 class="product name product-item-name">
      <a class="product-item-link" href="https://www.panini.es/shp_esp_es/otro.html">
        Otro</a>
    </h3>
    <div class="product attribute type product-item-attribute-release-date">
      <small>03/12/26</small>
    </div>
  </div>
</li>
</ol>
'''


def test_norma_parsea_fecha_y_titulos():
    filas = parsear_norma(NORMA, hoy=date(2026, 11, 16))
    assert [(f.titulo, f.fecha) for f in filas] == [
        ("Blade Runner 2019 [Ed. Integral]", date(2026, 11, 20)),
        ("NO/ONE", date(2026, 11, 20)),
    ]
    assert all(f.fuente == "Norma" and f.editorial == "Norma Editorial" for f in filas)


def test_norma_pasa_diciembre_a_enero():
    html = NORMA.replace("20 DE NOVIEMBRE", "5 DE ENERO")
    filas = parsear_norma(html, hoy=date(2026, 12, 20))
    assert filas[0].fecha == date(2027, 1, 5)


def test_panini_parsea_fecha_yy_titulo():
    filas = parsear_panini(PANINI, hoy=date(2026, 11, 16))
    assert [(f.titulo, f.fecha) for f in filas] == [
        ("Biblioteca Conan 24", date(2026, 11, 26)),
        ("Otro", date(2026, 12, 3)),
    ]
    assert filas[0].fuente == "Panini" and filas[0].url.endswith(".html")
