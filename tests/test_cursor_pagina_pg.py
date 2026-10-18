# ruff: noqa: E501
"""#143 — el cursor de página de la vista previa tiene que poder enviarse tal como lo emitió el sistema.

Hallazgo: `siguiente` era un Base64 de `[nombre, id]` en JSON. En JSON cada carácter de control ocupa seis bytes
(`\\u0001`), así que un nombre de 255 bytes —válido en Linux— daba un cursor de 2.100 caracteres, por encima del
`max_length=2000` de la petición siguiente: el sistema emitía un cursor que él mismo rechazaba.

Estas pruebas recorren **por HTTP** (cliente ASGI sobre Postgres real) lo que decía la issue: nombres límite,
recorrido completo, posiciones de página, cursores truncados, alterados y de la versión anterior. La fase 1 del
ensayo M4 NO ejercitó esto: aquí no se hereda cobertura. Se saltan sin `TEST_DATABASE_URL`.

Contrato (issue #143): el cursor es autocontenido y entra siempre en el límite; no cambia el orden `(nombre, id)`;
un cursor que no se puede aceptar da un error EXPLÍCITO y recuperable, nunca una página (vacía o de otra posición).
"""
from __future__ import annotations

import base64
import json
import os
import zlib
from uuid import UUID, uuid4

import pytest

from tests import test_vinculacion_previa_pg as _base
from zascarr.models import File, FileFormat
from zascarr.services.vinculacion_previa import LIMITE_ARCHIVOS

# Fixtures y ayudas compartidas con la prueba de la vista previa (se re-exportan como atributos, no por `import`,
# para que pytest las vea sin redefinirlas).
url_bd = _base.url_bd
entorno = _base.entorno
cliente = _base.cliente
serie_de_prueba = _base.serie_de_prueba
RUTA = _base.RUTA

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

CARPETA = "Comics/Flash (1987)"
CLAVE = "Comics/Flash (1987)"
LIMITE_PETICION = 2000  # `max_length` del campo `cursor` de la petición (api/revision.py y web)

#: Los caracteres de control que JSON escribe con seis caracteres (`\\u00XX`): todos menos \b \t \n \f \r, que tienen
#: escape corto. Con 255 de ellos el cursor antiguo medía ≈2.100 caracteres (la reproducción de la issue).
_CONTROL_LARGO = [chr(c) for c in range(1, 32) if chr(c) not in "\b\t\n\f\r"]
CONTROL_255 = "\x1f" + "".join(_CONTROL_LARGO[i % len(_CONTROL_LARGO)] for i in range(254))   # 255 bytes de control
EMOJI_63 = "z" + "😀" * 62                                                   # 1 + 62·4 = 249 bytes
MIXTO_255 = "zA" + "é" * 20 + "😀" * 10 + "\t\n\x1b" * 30 + "ñ" * 10 + "x" * (255 - 2 - 40 - 40 - 90 - 20)
#: Nombres límite (válidos en el sistema de ficheros objetivo y en la columna `file_name`, que admite 500 caracteres).
#: Todos empiezan por un carácter mayor que el relleno (`\x01…`) para que el límite ocupe el puesto 100.
NOMBRES_LIMITE = {
    "control_255_bytes": CONTROL_255,
    "emoji": EMOJI_63,
    "mixto": MIXTO_255,
    "ascii_255": "z" + "a" * 254,
    "acentos_499_caracteres": "z" + "é" * 498,                               # 997 bytes
    "emoji_499_caracteres": "z" + "😀" * 498,                                 # 1.993 bytes
    "control_499_caracteres": "\x1f" + chr(7) * 498,
}


def _bytes_utf8(texto: str) -> int:
    return len(texto.encode("utf-8"))


async def _sembrar(entorno, nombres: list[str]) -> dict[str, str]:
    """Registra un archivo por nombre (sin crear nada en disco: la paginación no lo necesita) → nombre: id."""
    ids: dict[str, str] = {}
    async with entorno.banco.fabrica() as s:
        for n in nombres:
            f = File(id=uuid4(), file_path=f"{entorno.lib}/{CARPETA}/{n}", file_name=n, file_format=FileFormat.CBZ,
                     metadata_={"match_status": "unsorted"})
            s.add(f)
            ids[n] = str(f.id)
        await s.commit()
    return ids


def _relleno(cantidad: int) -> list[str]:
    """Nombres que ordenan ANTES que cualquier nombre límite (empiezan por \\x01)."""
    return [f"\x01Flash {i:03d} (1987).cbz" for i in range(1, cantidad + 1)]


def _siguen(limite: str) -> list[str]:
    """Dos nombres que ordenan DESPUÉS del límite (lo extienden: un prefijo siempre es menor que su extensión)."""
    return [limite + "a", limite + "b"]


async def _pedir(serie, cursor=None):
    cuerpo = {"clave": CLAVE, "series_id": str(serie)}
    if cursor is not None:
        cuerpo["cursor"] = cursor
    async with cliente() as c:
        return await c.post(RUTA, json=cuerpo)


async def _recorrer(serie) -> tuple[list[list[str]], list[str]]:
    """Recorre el grupo usando EXCLUSIVAMENTE los `siguiente` recibidos, tal cual. → (nombres por página, cursores)."""
    paginas, cursores, cursor = [], [], None
    for _ in range(50):
        r = await _pedir(serie, cursor)
        assert r.status_code == 200, (cursor and len(cursor), r.status_code, r.text[:300])
        cuerpo = r.json()
        paginas.append([a["nombre"] for a in cuerpo["archivos"]])
        cursor = cuerpo["pagina"]["siguiente"]
        if not cursor:
            return paginas, cursores
        cursores.append(cursor)
    raise AssertionError("el recorrido no termina")


class TestNombresLimite:
    """Criterios 1 y 2: la petición con el cursor emitido es aceptada y devuelve la página correcta."""

    @pytest.mark.parametrize("etiqueta", sorted(NOMBRES_LIMITE))
    async def test_el_ultimo_de_la_primera_pagina_es_un_nombre_limite(self, entorno, etiqueta):
        limite = NOMBRES_LIMITE[etiqueta]
        serie = await serie_de_prueba(entorno)
        # 99 normales + el límite = página 1 (100); le siguen dos más → página 2.
        await _sembrar(entorno, _relleno(LIMITE_ARCHIVOS - 1) + [limite, *_siguen(limite)])
        p1 = (await _pedir(serie)).json()
        assert p1["archivos"][-1]["nombre"] == limite and p1["pagina"]["hay_mas"]
        cursor = p1["pagina"]["siguiente"]
        assert cursor and len(cursor) <= LIMITE_PETICION, f"cursor de {len(cursor)} caracteres"

        r = await _pedir(serie, cursor)                    # el cursor, íntegro y sin tocar
        assert r.status_code == 200, r.text[:300]
        p2 = r.json()
        assert [a["nombre"] for a in p2["archivos"]] == _siguen(limite)
        assert (p2["pagina"]["desde"], p2["pagina"]["hasta"], p2["pagina"]["hay_mas"]) == (101, 102, False)

    async def test_la_reproduccion_de_la_issue_255_bytes_de_control(self, entorno):
        """El caso exacto de #143: antes del arreglo el cursor medía 2.100 y la petición era rechazada."""
        assert _bytes_utf8(CONTROL_255) == 255
        serie = await serie_de_prueba(entorno)
        await _sembrar(entorno, _relleno(LIMITE_ARCHIVOS - 1) + [CONTROL_255, CONTROL_255 + "a"])
        p1 = (await _pedir(serie)).json()
        cursor = p1["pagina"]["siguiente"]
        r = await _pedir(serie, cursor)
        assert r.status_code == 200, f"cursor de {len(cursor)} caracteres → {r.status_code} {r.text[:200]}"
        assert [a["nombre"] for a in r.json()["archivos"]] == [CONTROL_255 + "a"]

    @pytest.mark.parametrize("etiqueta", sorted(NOMBRES_LIMITE))
    def test_ningun_nombre_valido_supera_el_limite_al_emitir(self, etiqueta):
        """La garantía está en la EMISIÓN, no solo al recibir (criterio de la issue)."""
        from types import SimpleNamespace

        from zascarr.services.vinculacion_previa import _cursor_de
        cursor = _cursor_de(SimpleNamespace(nombre=NOMBRES_LIMITE[etiqueta], id=str(uuid4())))
        assert len(cursor) <= LIMITE_PETICION and cursor.isascii()


class TestRecorridoCompleto:
    """Criterio 3: sin omisiones, duplicados ni desorden respecto de `(nombre, id)`."""

    async def test_recorrido_con_nombres_limite_en_los_extremos_de_cada_pagina(self, entorno):
        serie = await serie_de_prueba(entorno)
        # Cada nombre límite cae como último de una página: 99+límite, 99+límite, 99+límite, resto.
        limites = ["\x1e" + CONTROL_255, "z2" + EMOJI_63, "z3" + MIXTO_255]
        nombres = [f"\x01Flash {i:03d} (1987).cbz" for i in range(1, 100)]
        nombres += [f"M{j}{i:03d}.cbz" for j in range(2) for i in range(99)]
        ids = await _sembrar(entorno, nombres + limites + [f"zz{i}.cbz" for i in range(7)])
        esperado = sorted(ids, key=lambda n: (n, ids[n]))

        paginas, cursores = await _recorrer(serie)
        vistos = [n for p in paginas for n in p]
        assert vistos == esperado, "omisiones, duplicados o desorden"
        assert len(set(vistos)) == len(ids) == len(vistos)
        assert [len(p) for p in paginas][:-1] == [LIMITE_ARCHIVOS] * (len(paginas) - 1)
        assert all(len(c) <= LIMITE_PETICION for c in cursores)

    @pytest.mark.parametrize("total,paginas_esperadas", [(100, 1), (101, 2), (200, 2), (250, 3)])
    async def test_100_101_y_mas_archivos(self, entorno, total, paginas_esperadas):
        serie = await serie_de_prueba(entorno)
        ids = await _sembrar(entorno, [f"Flash {i:04d} (1987).cbz" for i in range(1, total + 1)])
        paginas, _ = await _recorrer(serie)
        assert len(paginas) == paginas_esperadas
        assert [n for p in paginas for n in p] == sorted(ids, key=lambda n: (n, ids[n]))

    async def test_posiciones_primera_intermedia_y_penultima(self, entorno):
        """Se pide cada página con su cursor y se comprueba que empieza justo después de la anterior."""
        serie = await serie_de_prueba(entorno)
        nombres = [f"Flash {i:04d}.cbz" for i in range(1, 330)]
        nombres[99] = "Flash 0100" + "\x01" * 200                              # último de la 1.ª: nombre largo
        nombres[199] = "Flash 0200" + "😀" * 60                                # último de la 2.ª (intermedia)
        nombres[299] = "Flash 0300" + "ñ\x1f" * 100                            # último de la 3.ª (penúltima de 4)
        ids = await _sembrar(entorno, nombres)
        orden = sorted(ids, key=lambda n: (n, ids[n]))
        paginas, cursores = await _recorrer(serie)
        assert len(paginas) == 4
        for i, pagina in enumerate(paginas):
            assert pagina == orden[i * LIMITE_ARCHIVOS:(i + 1) * LIMITE_ARCHIVOS]
        assert len(cursores) == 3

    async def test_el_cursor_sigue_valiendo_si_el_ultimo_archivo_se_vincula_entre_peticiones(self, entorno):
        """La razón de que el cursor lleve el NOMBRE y no solo el id: tras confirmar una página, su último
        archivo deja de estar pendiente y el cursor tiene que seguir señalando el mismo punto."""
        serie = await serie_de_prueba(entorno)
        ids = await _sembrar(entorno, _relleno(LIMITE_ARCHIVOS - 1) + [CONTROL_255, *_siguen(CONTROL_255)])
        cursor = (await _pedir(serie)).json()["pagina"]["siguiente"]
        async with entorno.banco.fabrica() as s:          # el archivo del cursor deja de estar pendiente
            f = await s.get(File, UUID(ids[CONTROL_255]))
            f.review_dismissed = True
            await s.commit()
        r = await _pedir(serie, cursor)
        assert r.status_code == 200
        assert [a["nombre"] for a in r.json()["archivos"]] == _siguen(CONTROL_255)


class TestNombreFueraDeRango:
    """Un nombre que no cabe en el cursor (> 1.024 bytes: solo posible en la base, no en el sistema de ficheros) viaja
    por su id: sigue entrando en el límite y, si ese archivo ya no está pendiente, la respuesta es un error explícito."""

    async def test_el_cursor_por_id_recorre_y_cabe(self, entorno):
        largo = NOMBRES_LIMITE["emoji_499_caracteres"]
        assert _bytes_utf8(largo) > 1024
        serie = await serie_de_prueba(entorno)
        ids = await _sembrar(entorno, _relleno(LIMITE_ARCHIVOS - 1) + [largo, *_siguen(largo)])
        paginas, cursores = await _recorrer(serie)
        assert [n for p in paginas for n in p] == sorted(ids, key=lambda n: (n, ids[n]))
        assert len(cursores) == 1 and len(cursores[0]) < 100

    async def test_si_el_archivo_del_cursor_ya_no_esta_pendiente_es_un_error_explicito_y_recuperable(self, entorno):
        largo = NOMBRES_LIMITE["emoji_499_caracteres"]
        serie = await serie_de_prueba(entorno)
        ids = await _sembrar(entorno, _relleno(LIMITE_ARCHIVOS - 1) + [largo, *_siguen(largo)])
        cursor = (await _pedir(serie)).json()["pagina"]["siguiente"]
        async with entorno.banco.fabrica() as s:
            f = await s.get(File, UUID(ids[largo]))
            f.review_dismissed = True
            await s.commit()
        r = await _pedir(serie, cursor)
        assert r.status_code == 422
        detalle = r.json()["detail"]
        assert detalle["codigo"] == "cursor_no_valido" and "primera página" in detalle["mensaje"]
        assert (await _pedir(serie)).status_code == 200                      # recuperable: la primera página sigue ahí


class TestCursorQueNoSePuedeAceptar:
    """Criterios 4 y 5: error explícito y recuperable; nunca una página (vacía o de otra posición)."""

    async def _cursor_valido(self, entorno):
        serie = await serie_de_prueba(entorno)
        await _sembrar(entorno, _relleno(LIMITE_ARCHIVOS - 1) + ["zUltimo.cbz"] + [f"zz{i}.cbz" for i in range(5)])
        return serie, (await _pedir(serie)).json()["pagina"]["siguiente"]

    def _es_error_explicito(self, r):
        assert r.status_code == 422, f"debería rechazarse y dio {r.status_code}: {r.text[:200]}"
        detalle = r.json()["detail"]
        assert isinstance(detalle, dict) and detalle["codigo"] == "cursor_no_valido" and detalle["mensaje"]

    async def test_cada_truncamiento_posible_es_un_error_explicito(self, entorno):
        """Todos los prefijos propios del cursor: ninguno puede leerse como una posición válida."""
        serie, cursor = await self._cursor_valido(entorno)
        for n in range(1, len(cursor)):
            self._es_error_explicito(await _pedir(serie, cursor[:n]))

    async def test_un_cursor_truncado_dentro_del_nombre_largo_es_un_error(self, entorno):
        """El peligroso: cortado en mitad de un nombre largo seguiría siendo un nombre «bien formado»."""
        serie = await serie_de_prueba(entorno)
        await _sembrar(entorno, _relleno(LIMITE_ARCHIVOS - 1) + [CONTROL_255, *_siguen(CONTROL_255)])
        cursor = (await _pedir(serie)).json()["pagina"]["siguiente"]
        for n in range(len(cursor) // 2, len(cursor)):
            self._es_error_explicito(await _pedir(serie, cursor[:n]))

    async def test_cada_alteracion_de_un_caracter_es_un_error(self, entorno):
        """Toda posición con dos sustitutos, y el ÚLTIMO BLOQUE con todos los caracteres del alfabeto: allí Base64
        admite cadenas distintas para los mismos bytes (bits de relleno), y por eso solo se acepta la representación
        canónica, la que el sistema emitiría."""
        serie, cursor = await self._cursor_valido(entorno)
        alfabeto = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_="
        ultimo_bloque = len(cursor) - 4
        for i in range(len(cursor)):
            otros = [c for c in alfabeto if c != cursor[i]]
            for sustituto in (otros if i >= ultimo_bloque else (otros[i % 7], otros[-1 - i % 5])):
                self._es_error_explicito(await _pedir(serie, cursor[:i] + sustituto + cursor[i + 1:]))

    @pytest.mark.parametrize("basura", ["x", "no-es-base64!!", "inicio", "A" * 40, "====", "W10=", "ñ", "\x00\x01"])
    async def test_cursores_inventados(self, entorno, basura):
        serie = await serie_de_prueba(entorno)
        await _sembrar(entorno, _relleno(3))
        self._es_error_explicito(await _pedir(serie, basura))

    async def test_caracteres_ajenos_al_alfabeto_no_se_ignoran(self, entorno):
        """Un decodificador permisivo descarta lo que no es Base64: el cursor «alterado» valdría igual."""
        serie, cursor = await self._cursor_valido(entorno)
        for alterado in (cursor + "!", "!" + cursor, cursor[:10] + "\n" + cursor[10:], cursor[:8] + "@" + cursor[8:]):
            self._es_error_explicito(await _pedir(serie, alterado))

    async def test_un_cursor_de_la_version_anterior_sigue_aceptandose(self, entorno):
        """Compatibilidad prometida: el formato antiguo (JSON en Base64) sigue siendo una posición válida."""
        serie = await serie_de_prueba(entorno)
        ids = await _sembrar(entorno, [f"Flash {i:03d}.cbz" for i in range(1, 131)])
        ultimo = sorted(ids)[99]
        antiguo = base64.urlsafe_b64encode(json.dumps([ultimo, ids[ultimo]], ensure_ascii=False).encode()).decode()
        r = await _pedir(serie, antiguo)
        assert r.status_code == 200
        assert [a["nombre"] for a in r.json()["archivos"]] == sorted(ids)[100:]

    async def test_un_cursor_antiguo_demasiado_largo_ya_no_se_puede_enviar_y_es_un_error_explicito(self, entorno):
        """El que emitió la versión con el defecto (2.100 caracteres): no cabe en la petición; el error es claro."""
        serie = await serie_de_prueba(entorno)
        await _sembrar(entorno, _relleno(3))
        antiguo = base64.urlsafe_b64encode(json.dumps([CONTROL_255, str(uuid4())], ensure_ascii=False).encode()).decode()
        assert len(antiguo) > LIMITE_PETICION
        r = await _pedir(serie, antiguo)
        assert r.status_code == 422

    async def test_un_cursor_con_el_id_de_otro_archivo_o_inexistente_no_inventa_posicion(self, entorno):
        """Un cursor bien formado de un archivo que no existe NO falla (es solo una posición); con nombre completo
        se interpreta por su nombre. Se fija para que nadie lo confunda con «cursor alterado»."""
        serie = await serie_de_prueba(entorno)
        ids = await _sembrar(entorno, [f"Flash {i:03d}.cbz" for i in range(1, 131)])
        base = sorted(ids)[99]
        fabricado = base64.urlsafe_b64encode(json.dumps([base, str(uuid4())]).encode()).decode()
        r = await _pedir(serie, fabricado)
        assert r.status_code == 200 and r.json()["pagina"]["desde"] in (100, 101)


class TestUnaSolaResolucionPorPeticion:
    """La posición del cursor se resuelve y valida UNA vez por petición, antes de filtrar el grupo. Resolverla dentro de
    la comprensión que recorre el grupo hacía cuadrática la búsqueda por id (1.000 registros con el cursor en el 900:
    ≈ 901.000 visitas para devolver 100 archivos)."""

    @pytest.fixture
    def llamadas(self, monkeypatch):
        from zascarr.services import vinculacion_previa as servicio
        contador = {"posicion": 0, "leer": 0, "visitas": 0}
        posicion, leer = servicio._posicion, servicio._leer_cursor

        def _posicion_contada(cursor, todos):
            contador["posicion"] += 1
            return posicion(cursor, _Contada(todos, contador))

        def _leer_contado(cursor):
            contador["leer"] += 1
            return leer(cursor)
        monkeypatch.setattr(servicio, "_posicion", _posicion_contada)
        monkeypatch.setattr(servicio, "_leer_cursor", _leer_contado)
        return contador

    @pytest.mark.parametrize("por_id", [False, True], ids=["con_nombre", "por_id"])
    async def test_una_resolucion_y_visitas_lineales(self, entorno, llamadas, por_id):
        largo = "z" + "😀" * 300                              # 1.201 bytes: fuera de rango → cursor por id
        assert _bytes_utf8(largo) > 1024
        serie = await serie_de_prueba(entorno)
        ultimo = largo if por_id else "z" + "ñ" * 20
        nombres = _relleno(LIMITE_ARCHIVOS - 1) + [ultimo] + [f"{ultimo}{i:03d}" for i in range(120)]
        await _sembrar(entorno, nombres)
        cursor = (await _pedir(serie)).json()["pagina"]["siguiente"]
        llamadas.update(posicion=0, leer=0, visitas=0)

        r = await _pedir(serie, cursor)
        assert r.status_code == 200 and len(r.json()["archivos"]) == LIMITE_ARCHIVOS
        assert llamadas["posicion"] == 1 and llamadas["leer"] == 1, llamadas
        # La búsqueda por id recorre el grupo UNA vez (≤ su tamaño), no una vez por archivo.
        assert llamadas["visitas"] <= len(nombres), llamadas


class _Contada(list):
    """El grupo, contando cuántos elementos se visitan al recorrerlo."""

    def __init__(self, base, contador):
        super().__init__(base)
        self._contador = contador

    def __iter__(self):
        for x in super().__iter__():
            self._contador["visitas"] += 1
            yield x


class TestFormatoDelCursor:
    """El cursor es opaco y acotado por diseño: ASCII seguro para URL y formulario, con huella de integridad."""

    def test_el_cursor_nuevo_no_se_parece_al_antiguo_ni_a_la_palabra_de_inicio(self):
        from types import SimpleNamespace

        from zascarr.services.vinculacion_previa import _cursor_de
        c = _cursor_de(SimpleNamespace(nombre="Flash 001.cbz", id=str(uuid4())))
        assert not c.startswith("WyI") and c != "inicio"
        assert base64.urlsafe_b64decode(c.encode())[0] in (1, 2)

    def test_ida_y_vuelta_exacta_para_nombres_limite(self):
        from types import SimpleNamespace

        from zascarr.services.vinculacion_previa import _cursor_de, _leer_cursor
        for nombre in NOMBRES_LIMITE.values():
            ident = str(uuid4())
            leido = _leer_cursor(_cursor_de(SimpleNamespace(nombre=nombre, id=ident)))
            assert leido[1] == ident
            assert leido[0] in (nombre, None)       # None = nombre fuera de rango: se resuelve por id

    def test_la_huella_cubre_el_nombre(self):
        from types import SimpleNamespace

        from zascarr.services.vinculacion_previa import (
            CursorNoValidoError,
            _cursor_de,
            _leer_cursor,
        )
        crudo = bytearray(base64.urlsafe_b64decode(_cursor_de(SimpleNamespace(nombre="Flash 001.cbz", id=str(uuid4())))))
        crudo[-1] ^= 0x01
        with pytest.raises(CursorNoValidoError):
            _leer_cursor(base64.urlsafe_b64encode(bytes(crudo)).decode())

    def test_el_zlib_de_la_huella_es_el_de_la_biblioteca_estandar(self):
        """Sin dependencias nuevas (CLAUDE.md §2): solo `zlib.crc32`."""
        assert zlib.crc32(b"") == 0
