# ruff: noqa: E501, F401, F811
"""Límite del token de vinculación, de extremo a extremo (Postgres real y ficheros reales en `tmp`). Ver
`test_tokens_vinculacion_limite.py` para el cálculo.

Tres clases de evidencia, que no se mezclan (como en #138):
1. **Recorrido completo** (una OBSERVACIÓN, no una garantía): un grupo real cuya clave sale de `/carpetas` (carpetas con
   controles en su nombre, sin depurar), 100 archivos reales, números que escribe la persona → vista previa → token
   emitido por el servidor → `POST /api/revision/vinculacion`. **En los recorridos ensayados el token quedó por debajo
   del límite anterior (56.029) y la confirmación funcionó también con el código anterior**: no se observó el fallo. Esto
   no demuestra que ningún entorno pase de ahí (la clave puede llegar a ≈ 970 caracteres, `st_mtime_ns` a 28 dígitos...).
   Una variante usa un archivo cuyo `mtime_ns` supera 2**63 - 1, que `stat` devuelve de verdad.
2. **Frontera HTTP**: un token FIRMADO de la longitud exacta del máximo se acepta y se procesa; un carácter más se
   rechaza sin efectos; la firma se exige con la longitud exacta; el propósito y la caducidad, con un token a ≤ 4
   caracteres del máximo (el propósito «alta» tiene 4 letras menos que «vincular»; una `exp` ya pasada tiene un dígito
   menos que la del peor caso, así que el exacto no puede estar caducado); repetir devuelve el informe persistido.
3. **Sin efectos colaterales**: nada se mueve ni se renombra, no se aprende ningún alias.
Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import os
import time
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.test_tokens_vinculacion_limite import (
    CONTROLES_PESADOS,
    FORMATO,
    LIMITE_ANTERIOR,
    numero_pesado,
    token,
)
from tests.test_vinculacion_pg import (  # noqa: F401  (fixtures y ayudas compartidas)
    RUTA,
    confirmar,
    ent,
    estado_de_archivos,
    firmar,
    informes,
    numero_de,
    post,
    token_de,
)
from tests.test_vinculacion_previa_pg import (  # noqa: F401
    SECRETO,
    archivos,
    cliente,
    entorno,
    huella_disco,
    instantanea,
    previsualizar,
    serie_de_prueba,
    url_bd,
)
from zascarr.services.tokens_revision import (
    CARACTER_MAS_PESADO_DE_UNA_CLAVE,
    CODIGOS_DE_SENAL,
    EPOCA_DEL_PEOR_CASO,
    MAX_CLAVE_GRUPO,
    MAX_MTIME_NS_STAT,
    MAX_TAMANO_STAT,
    MAX_TOKEN_VINCULACION,
    PROPOSITO_ALTA,
    TTL_SEGUNDOS,
    ArchivoFirmado,
    VinculacionFirmada,
    crear_token,
    crear_token_vinculacion,
    verificar_token,
)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

NOMBRES = [f"Flash {i:03d} (1987).cbz" for i in range(1, 101)]


def carpeta_de_controles(biblioteca) -> str:
    """La carpeta de controles más larga que cabe: `files.file_path` es `String(1000)`, la ruta es
    `{biblioteca}/{carpeta}/{nombre}` y un componente de ruta no pasa de 255 bytes (por eso va en varios)."""
    nombre = max(len(n) for n in NOMBRES)
    libre = 1000 - len(f"{biblioteca}/") - len(f"/{'x' * nombre}") - len("Comics/")
    trozos = []
    while libre > 0:
        largo = min(200, libre - (1 if libre > 200 else 0))
        trozos.append(CARACTER_MAS_PESADO_DE_UNA_CLAVE * largo)
        libre -= largo + 1
    return "Comics/" + "/".join(trozos)


async def clave_del_grupo(carpeta: str) -> str:
    """La `clave` que da la superficie de revisión (se lee de `/carpetas`, no se construye a mano ni se depura)."""
    async with cliente() as c:
        r = await c.get("/api/revision/carpetas")
    claves = [g["clave"] for g in r.json()["grupos"] if g["clave"] == carpeta]
    assert len(claves) == 1, [len(g["clave"]) for g in r.json()["grupos"]]
    return claves[0]


async def preparar_grupo(ent):
    carpeta = carpeta_de_controles(ent.lib)
    ids = await archivos(ent, *NOMBRES, carpeta=carpeta)
    clave = await clave_del_grupo(carpeta)
    serie = await serie_de_prueba(ent)
    return clave, ids, serie


async def sin_efectos(ent) -> dict:
    return {"tablas": await instantanea(ent.banco), "informes": await informes(ent.banco),
            "estado": await estado_de_archivos(ent.banco)}


# ── 1. Recorrido completo ─────────────────────────────────────────────────────────────────────────

class TestRecorridoCompleto:
    """LO QUE SE OBSERVA en los recorridos ensayados, no una garantía: con el código anterior (límite 56.029) estos
    recorridos TAMPOCO fallaron. El token que emitió la vista previa quedó por debajo de ese límite porque el cálculo
    del máximo junta cosas que estos recorridos no juntan: `tamano` y `mtime_ns` del máximo en los 100 archivos, los 8
    códigos de conflicto en cada uno (en las combinaciones examinadas un archivo da 3) y una clave de 1000 caracteres (la
    de estos recorridos mide ≈ 910). No se afirma que ningún entorno pase de ahí. Es un defecto de la COTA (su derivación
    no era una cota superior demostrada), no un fallo observado."""

    async def test_clave_real_de_controles_numeros_de_controles_y_conflictos_vista_previa_token_y_confirmacion(self, ent):
        carpeta = carpeta_de_controles(ent.lib)
        ids = await archivos(ent, *NOMBRES, carpeta=carpeta)
        clave = await clave_del_grupo(carpeta)
        serie = await serie_de_prueba(ent, "Batman", 1940)        # contradice la carpeta: conflictos en TODOS los archivos
        assert set(clave.replace("Comics/", "").replace("/", "")) == {"\x01"} and 800 < len(clave) < MAX_CLAVE_GRUPO
        numeros = {fid: numero_pesado(i) for i, fid in enumerate(ids.values())}          # los escribe la persona
        antes_disco, antes_estado = huella_disco(ent.lib), await estado_de_archivos(ent.banco)

        r = await previsualizar(serie, clave=clave, marcados=list(ids.values()), numeros=numeros)
        assert r.status_code == 200, r.text
        t = r.json()["token"]
        assert all(a["numero"] in numeros.values() for a in r.json()["archivos"])           # números sin tocar
        assert len(t) <= MAX_TOKEN_VINCULACION
        assert len(t) < LIMITE_ANTERIOR, (len(t), "el recorrido real ya no queda por debajo del límite anterior")

        c = await confirmar(t)
        assert c.status_code == 200, c.text[:300]
        cuerpo = c.json()
        assert cuerpo["repetida"] is False and cuerpo["resultado"]["global"] == "vinculados_todos"
        assert cuerpo["resultado"]["totales"]["vinculados"] == 100 and cuerpo["resultado"]["totales"]["con_conflicto_incluidos"] == 100

        # Sin movimientos, renombrados ni aprendizaje de alias; los números se conservan tal cual
        assert huella_disco(ent.lib) == antes_disco
        despues = await estado_de_archivos(ent.banco)
        assert {n: v[2] for n, v in despues.items()} == {n: v[2] for n, v in antes_estado.items()}      # rutas intactas
        assert all(v[0] and v[1] == "manual" for v in despues.values())
        assert await numero_de("local_aliases", ent.banco) == 0 and await numero_de("asignacion_operaciones", ent.banco) == 0
        async with ent.banco.fabrica() as s:
            guardados = {n for (n,) in (await s.execute(text("SELECT issue_number FROM issues"))).all()}
        assert guardados == set(numeros.values())

        # El informe persistido y la repetición
        guardado = await informes(ent.banco)
        assert len(guardado) == 1
        otra = await confirmar(t)
        assert otra.status_code == 200 and otra.json()["repetida"] is True
        assert otra.json()["resultado"] == cuerpo["resultado"]
        assert await informes(ent.banco) == guardado

    async def test_la_clave_de_controles_sola_tampoco_alcanza_el_limite_anterior(self, ent):
        clave, ids, serie = await preparar_grupo(ent)
        numeros = {fid: str(i + 1) for i, fid in enumerate(ids.values())}
        r = await previsualizar(serie, clave=clave, marcados=list(ids.values()), numeros=numeros)
        assert r.status_code == 200, r.text
        t = r.json()["token"]
        assert len(t) < LIMITE_ANTERIOR, len(t)
        c = await confirmar(t)
        assert c.status_code == 200 and c.json()["resultado"]["totales"]["vinculados"] == 100


    async def test_un_archivo_con_mtime_por_encima_de_2_63_se_vincula_y_el_token_cabe(self, ent):
        """`stat` devuelve de verdad `st_mtime_ns` de 20 dígitos (aquí 10**19, año 2286): entra en el token tal cual y la
        confirmación lo reverifica contra el disco. Mide el entorno donde se ejecuta."""
        import os
        clave, ids, serie = await preparar_grupo(ent)
        rutas = sorted(p for p in ent.lib.rglob("*.cbz"))
        assert len(rutas) == 100
        for ruta in rutas:
            os.utime(ruta, ns=(10**19, 10**19))
        assert all(r.stat().st_mtime_ns == 10**19 for r in rutas), "el sistema de archivos no conserva la fecha de 20 dígitos"
        numeros = {fid: numero_pesado(i) for i, fid in enumerate(ids.values())}
        r = await previsualizar(serie, clave=clave, marcados=list(ids.values()), numeros=numeros)
        assert r.status_code == 200, r.text
        t = r.json()["token"]
        assert len(t) <= MAX_TOKEN_VINCULACION
        c = await confirmar(t)
        assert c.status_code == 200 and c.json()["resultado"]["totales"]["vinculados"] == 100, c.text[:300]
        assert (await estado_de_archivos(ent.banco)).keys() == set(NOMBRES)


# ── 2. Frontera HTTP con tokens firmados ──────────────────────────────────────────────────────────

def token_maximo(clave: str, serie) -> str:
    """El token firmado del peor caso (100 archivos que no existen en la base) sobre una serie que SÍ existe."""
    return token(clave, numero_pesado, serie=str(serie))


class TestFronteraHTTP:

    async def test_un_token_firmado_de_la_longitud_exacta_se_acepta_y_se_procesa(self, ent):
        clave = CARACTER_MAS_PESADO_DE_UNA_CLAVE * MAX_CLAVE_GRUPO
        t = token_maximo(clave, await serie_de_prueba(ent))
        assert len(t) == MAX_TOKEN_VINCULACION, "ya no es la frontera: el máximo y esta prueba han dejado de coincidir"
        antes = await sin_efectos(ent)
        c = await confirmar(t)
        assert c.status_code == 200, c.text[:300]        # pasa el esquema, la firma y la verificación
        assert c.json()["resultado"]["global"] == "nada_vinculado"              # los archivos del token no existen
        assert (await instantanea(ent.banco)) == antes["tablas"]               # no escribió filas ajenas al informe
        assert len(await informes(ent.banco)) == 1

    async def test_repetir_el_token_de_la_frontera_devuelve_el_informe_guardado(self, ent):
        t = token_maximo(CARACTER_MAS_PESADO_DE_UNA_CLAVE * MAX_CLAVE_GRUPO, await serie_de_prueba(ent))
        primera = await confirmar(t)
        guardado = await informes(ent.banco)
        segunda = await confirmar(t)
        assert primera.status_code == segunda.status_code == 200
        assert primera.json()["repetida"] is False and segunda.json()["repetida"] is True
        assert segunda.json()["resultado"] == primera.json()["resultado"] and await informes(ent.banco) == guardado

    async def test_un_caracter_mas_del_maximo_se_rechaza_en_la_validacion_sin_efectos(self, ent):
        antes = await sin_efectos(ent)
        r = await confirmar("a" * (MAX_TOKEN_VINCULACION + 1))
        assert r.status_code == 422 and isinstance(r.json()["detail"], list)
        assert await sin_efectos(ent) == antes

    async def test_el_limite_es_inclusivo(self, ent):
        """Un cuerpo de exactamente el máximo llega al servicio (no es un token: lo rechaza como inválido)."""
        antes = await sin_efectos(ent)
        r = await confirmar("a" * MAX_TOKEN_VINCULACION)
        assert r.status_code == 422 and isinstance(r.json()["detail"], dict)
        assert await sin_efectos(ent) == antes

    async def test_la_firma_se_exige_con_la_longitud_exacta_y_el_proposito_a_cuatro_caracteres(self, ent):
        clave = CARACTER_MAS_PESADO_DE_UNA_CLAVE * MAX_CLAVE_GRUPO
        serie = await serie_de_prueba(ent)
        t = token_maximo(clave, serie)
        assert len(t) == MAX_TOKEN_VINCULACION
        antes = await sin_efectos(ent)

        manipulado = t[:-1] + ("0" if t[-1] != "0" else "1")                                    # firma, longitud exacta
        r = await confirmar(manipulado)
        assert len(manipulado) == MAX_TOKEN_VINCULACION
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "token_invalido", r.text[:200]

        # propósito: los MISMOS datos del peor caso firmados como un token de alta. «alta» tiene 4 caracteres menos que
        # «vincular», así que mide hasta 4 menos que el máximo (no puede ser exacto sin inventar un propósito).
        datos = verificar_token(t, "vincular", clave, SECRETO, ahora=EPOCA_DEL_PEOR_CASO)
        como_alta = crear_token(PROPOSITO_ALTA, clave, datos, SECRETO, ahora=EPOCA_DEL_PEOR_CASO)
        assert MAX_TOKEN_VINCULACION - 4 <= len(como_alta) <= MAX_TOKEN_VINCULACION
        r = await confirmar(como_alta)
        assert r.status_code == 422 and r.json()["detail"]["codigo"] == "token_invalido"
        assert await sin_efectos(ent) == antes

    async def test_la_caducidad_se_exige_con_un_token_a_cuatro_caracteres_del_maximo(self, ent):
        """No puede ser EXACTAMENTE el máximo: una `exp` pasada tiene un dígito menos que la del peor caso (11 dígitos)."""
        clave = CARACTER_MAS_PESADO_DE_UNA_CLAVE * MAX_CLAVE_GRUPO
        serie = await serie_de_prueba(ent)
        antes = await sin_efectos(ent)
        caducado = crear_token_vinculacion(VinculacionFirmada(
            clave, str(serie), str(uuid4()), tuple(ArchivoFirmado(
                f"{i:08d}-0000-4000-8000-000000000000", numero_pesado(i), FORMATO, MAX_TAMANO_STAT, MAX_MTIME_NS_STAT,
                CODIGOS_DE_SENAL) for i in range(100))), SECRETO, ahora=time.time() - TTL_SEGUNDOS - 60)
        assert MAX_TOKEN_VINCULACION - 4 <= len(caducado) <= MAX_TOKEN_VINCULACION
        r = await confirmar(caducado)
        assert r.status_code == 410, r.text[:200]
        assert await sin_efectos(ent) == antes
