# ruff: noqa: E501
"""`scripts/medicion/banco_cobertura.py` (#135): arnés en seco, fail-closed y métricas.

Sin Postgres y sin red: el modo seco usa fixtures saneados; el modo real sin autorización no
construye clientes. Ningún test lanza cobertura real (PR-3, con permiso separado).
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.medicion import banco_cobertura as banco


def _corpus() -> dict:
    return json.loads(banco.CORPUS_DEFECTO.read_text(encoding="utf-8"))


class TestCorpus:
    def test_el_corpus_v1_tiene_30_casos_12_acreditados_y_su_sha_coincide(self):
        corpus, sha = banco.cargar_corpus(banco.CORPUS_DEFECTO)
        assert len(corpus["casos"]) == 30
        assert corpus["tamano_objetivo"] == 30
        assert sha == banco.sha256_archivo(banco.CORPUS_DEFECTO)
        # El piloto se acreditó el 2026-11-06; el resto sigue en borrador y no suma.
        acreditados = [c for c in corpus["casos"] if c["identidad_acreditada"]]
        assert len(acreditados) == 12
        assert all(c["acreditacion"] == "verificada" for c in acreditados)
        assert all(c["acreditacion"] == "borrador"
                   for c in corpus["casos"] if not c["identidad_acreditada"])
        sin_identidad = [c for c in corpus["casos"]
                         if c["estado_identidad"] == "sin_identidad_acreditada"]
        assert len(sin_identidad) == 2
        estratos = {c["estrato"] for c in corpus["casos"]}
        assert estratos == {"serie", "edicion_publicacion", "numero_formato", "campo"}

    @pytest.mark.parametrize("mutacion,error", [
        (lambda c: c.pop("tamano_objetivo"), "tamano_objetivo"),
        (lambda c: c.__setitem__("tamano_objetivo", 99), "tamano_objetivo"),
        (lambda c: (c["casos"].append(copy.deepcopy(c["casos"][0])),
                    c.__setitem__("tamano_objetivo", 31)), "duplicado"),
        (lambda c: c["casos"][0].pop("caso_id"), "caso_id"),
        (lambda c: c["casos"][0].update({"procedencia": "inventada"}), "procedencia"),
        (lambda c: c["casos"][0].update({"consulta": "https://ejemplo.invalid/x"}), "URL"),
    ])
    def test_un_corpus_invalido_se_rechaza(self, mutacion, error):
        datos = _corpus()
        mutacion(datos)
        with pytest.raises(banco.ErrorBanco) as exc:
            banco.validar_corpus(datos)
        assert error in str(exc.value)

    def test_una_etiqueta_no_puede_ser_verificada_en_borrador(self):
        datos = _corpus()
        borrador = next(c for c in datos["casos"] if c["acreditacion"] == "borrador")
        borrador["identidad_acreditada"] = True   # sin acreditacion=verificada
        with pytest.raises(banco.ErrorBanco):
            banco.validar_corpus(datos)


class TestFixtures:
    def test_las_fixtures_saneadas_ejercitan_los_estados(self):
        corpus = _corpus()
        fixtures = banco.cargar_fixtures(banco.FIXTURES_DEFECTO, corpus)
        estados = {e["estado_tecnico"] for e in fixtures["ensayos"]}
        assert {"ok", "sin_resultados", "fallo_transitorio", "limite_de_cortesia",
                "no_ejecutado"} <= estados
        assert all("http" not in json.dumps(e).lower() for e in fixtures["ensayos"])

    def test_una_fixture_con_url_se_rechaza(self):
        corpus = _corpus()
        datos = json.loads(banco.FIXTURES_DEFECTO.read_text(encoding="utf-8"))
        datos["ensayos"][0]["candidatos"][0]["etiqueta_propuesta"] = "https://ejemplo.invalid"
        with pytest.raises(banco.ErrorBanco):
            banco.validar_fixtures(datos, corpus)


class TestSeсoDePuntaAPunta:
    def test_el_seco_valida_el_arnes_y_declara_cobertura_not_run(self, tmp_path, capsys):
        rc = banco.main(["--seco", "--salida", str(tmp_path)])
        assert rc == 0
        informe = json.loads((tmp_path / "informe.json").read_text(encoding="utf-8"))
        assert informe["cobertura"] == "NOT RUN"
        assert informe["meta"]["modo"] == "seco"
        assert informe["pass_fail_not_run"]["PASS"]
        assert "NOT RUN" in informe["pass_fail_not_run"]
        filas = [json.loads(linea) for linea in
                 (tmp_path / "registro.jsonl").read_text(encoding="utf-8").splitlines()]
        assert len(filas) == 8
        assert all(f["peticiones"] == 0 and f["modo"] == "seco" for f in filas)
        assert all(f["resultado_editorial"] is None for f in filas)
        informe_md = (tmp_path / "informe.md").read_text(encoding="utf-8")
        assert "PASS" in informe_md and "NOT RUN" in informe_md
        assert "evaluables:" in informe_md and "## Campos" in informe_md
        assert "30 casos" in informe_md and "8 registros" in informe_md
        assert "NOT RUN" in capsys.readouterr().out

    def test_el_seco_no_importa_ni_construye_clientes_de_red(self, tmp_path, monkeypatch):
        def _no_debe_llamarse(*_a, **_k):
            raise AssertionError("el modo seco no puede tocar la red")

        import zascarr.utils.peticiones as peticiones
        monkeypatch.setattr(peticiones, "pedir_con_cortesia", _no_debe_llamarse)
        monkeypatch.setattr("zascarr.services.comic_vine.ComicVineClient", _no_debe_llamarse)
        monkeypatch.setattr("zascarr.services.anilist.AniListClient", _no_debe_llamarse)
        assert banco.main(["--seco", "--salida", str(tmp_path)]) == 0

    def test_el_jsonl_no_publica_url_query_ni_claves(self, tmp_path):
        assert banco.main(["--seco", "--salida", str(tmp_path)]) == 0
        texto = (tmp_path / "registro.jsonl").read_text(encoding="utf-8")
        for prohibido in ("http://", "https://", "api_key", "Authorization", "Cookie",
                          "?query=", "?q="):
            assert prohibido not in texto, prohibido


class TestRealFailClosed:
    def _args(self, tmp_path, *extra):
        return ["--real", "--salida", str(tmp_path), "--casos", "ES-001",
                "--fuentes", "comic_vine", "--unidades", "serie", *extra]

    def test_sin_autorizacion_exit_2_cero_peticiones_y_filas_sin_autorizacion(
            self, tmp_path, monkeypatch):
        def _cliente_prohibido(*_a, **_k):
            raise AssertionError("sin autorización no se puede construir un cliente")
        monkeypatch.setattr("zascarr.services.comic_vine.ComicVineClient", _cliente_prohibido)
        rc = banco.main(self._args(tmp_path))
        assert rc == 2
        filas = [json.loads(x) for x in
                 (tmp_path / "registro.jsonl").read_text(encoding="utf-8").splitlines()]
        assert filas and all(f["estado_tecnico"] == "no_ejecutado" for f in filas)
        assert all(f["motivo_no_ejecutado"] == "sin_autorizacion" for f in filas)
        assert all(f["peticiones"] == 0 for f in filas)

    def test_autorizacion_caducada_o_fuera_de_ambito_es_exit_2(self, tmp_path):
        corpus, sha = banco.cargar_corpus(banco.CORPUS_DEFECTO)
        ahora = datetime.now(UTC)
        datos = {
            "id": "auth-test", "ambito": ["comic_vine"], "presupuesto_peticiones": 80,
            "desde": (ahora - timedelta(days=2)).isoformat(),
            "hasta": (ahora - timedelta(days=1)).isoformat(),   # caducada
            "concede": "PO", "condiciones": "prueba", "sha_corpus": sha,
        }
        ruta = tmp_path / "auth.json"
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        async def _prohibido(*_a, **_k):
            raise AssertionError("no se puede llamar a un cliente sin autorización")
        # monkeypatch local del test para la comprobación de cero peticiones
        import scripts.medicion.banco_cobertura as modulo
        original = modulo._llamar_cliente
        modulo._llamar_cliente = _prohibido
        try:
            assert banco.main(self._args(tmp_path, "--autorizacion", str(ruta))) == 2
            datos["hasta"] = (ahora + timedelta(days=1)).isoformat()
            datos["ambito"] = ["anilist"]                             # fuera de ámbito
            ruta.write_text(json.dumps(datos), encoding="utf-8")
            assert banco.main(self._args(tmp_path, "--autorizacion", str(ruta))) == 2
        finally:
            modulo._llamar_cliente = original

    def test_autorizacion_con_sha_distinto_o_sin_presupuesto_es_invalida(self):
        ahora = datetime.now(UTC)
        base = {
            "id": "a", "ambito": ["comic_vine"], "presupuesto_peticiones": 80,
            "desde": (ahora - timedelta(days=1)).isoformat(),
            "hasta": (ahora + timedelta(days=1)).isoformat(),
            "concede": "PO", "condiciones": "", "sha_corpus": "sha-correcto",
        }
        assert banco.validar_autorizacion(base, sha_corpus="sha-correcto",
                                          fuentes=["comic_vine"], ahora=ahora) == []
        assert "sha_corpus_distinto" in banco.validar_autorizacion(
            {**base, "sha_corpus": "otro"}, sha_corpus="sha-correcto",
            fuentes=["comic_vine"], ahora=ahora)
        assert "presupuesto_invalido" in banco.validar_autorizacion(
            {**base, "presupuesto_peticiones": 0}, sha_corpus="sha-correcto",
            fuentes=["comic_vine"], ahora=ahora)
        assert "fuera_de_ambito" in banco.validar_autorizacion(
            base, sha_corpus="sha-correcto", fuentes=["anilist"], ahora=ahora)


class TestRegresionesDeSeguridad:
    def test_el_seco_en_subproceso_no_carga_httpx_ni_clientes(self, tmp_path):
        """El arnés seco no importa `discovery`, que arrastra httpx/lxml/sqlalchemy."""
        codigo = (
            "import sys;"
            "from scripts.medicion import banco_cobertura as b;"
            f"assert b.main(['--seco', '--salida', {str(tmp_path)!r}]) == 0;"
            "assert 'httpx' not in sys.modules, 'httpx cargado en modo seco';"
            "assert 'zascarr.services.discovery' not in sys.modules, 'discovery cargado';"
        )
        entorno = {"PYTHONPATH": str(banco.RAIZ / "src"), "PATH": "/usr/bin:/bin"}
        resultado = subprocess.run([sys.executable, "-c", codigo], cwd=banco.RAIZ,
                                   env=entorno, capture_output=True, text=True, timeout=90)
        assert resultado.returncode == 0, resultado.stderr

    def test_una_autorizacion_con_fecha_naive_no_revienta_y_se_interpreta_utc(self):
        ahora = datetime.now(UTC)
        datos = {
            "id": "a", "ambito": ["comic_vine"],
            "presupuesto_peticiones": 80,
            "desde": (ahora - timedelta(days=1)).replace(tzinfo=None).isoformat(),
            "hasta": (ahora + timedelta(days=1)).replace(tzinfo=None).isoformat(),
            "concede": "PO", "condiciones": "", "sha_corpus": "sha",
        }
        assert banco.validar_autorizacion(datos, sha_corpus="sha",
                                          fuentes=["comic_vine"], ahora=ahora) == []

    def test_fichero_de_autorizacion_no_utf8_es_exit_2_sin_traceback(self, tmp_path):
        ruta = tmp_path / "auth.bin"
        ruta.write_bytes(b"\xff\xfe\x00no es json")
        rc = banco.main(["--real", "--salida", str(tmp_path / "salida"),
                         "--casos", "ES-001", "--fuentes", "comic_vine",
                         "--unidades", "serie", "--autorizacion", str(ruta)])
        assert rc == 2
        assert (tmp_path / "salida" / "informe.json").exists()

    def test_sin_autorizacion_caducada_no_llama_a_ningun_cliente(self, tmp_path, monkeypatch):
        corpus, sha = banco.cargar_corpus(banco.CORPUS_DEFECTO)
        ahora = datetime.now(UTC)
        auth = {"id": "a", "ambito": ["comic_vine"], "presupuesto_peticiones": 80,
                "desde": (ahora - timedelta(days=2)).isoformat(),
                "hasta": (ahora - timedelta(days=1)).isoformat(),
                "concede": "PO", "condiciones": "", "sha_corpus": sha}
        ruta = tmp_path / "auth.json"
        ruta.write_text(json.dumps(auth), encoding="utf-8")

        async def _prohibido(*_a, **_k):
            raise AssertionError("no se puede llamar a un cliente sin autorización")
        monkeypatch.setattr(banco, "_llamar_cliente", _prohibido)
        assert banco.main(["--real", "--salida", str(tmp_path / "salida"),
                           "--casos", "ES-001", "--fuentes", "comic_vine",
                           "--unidades", "serie", "--autorizacion", str(ruta)]) == 2

    def test_el_sha_del_corpus_se_compara_con_el_manifiesto(self, tmp_path):
        corpus, sha = banco.cargar_corpus(banco.CORPUS_DEFECTO, banco.MANIFIESTO_DEFECTO)
        assert len(corpus["casos"]) == 30
        malo = tmp_path / "manifiesto.json"
        malo.write_text(json.dumps({"version": "v1", "sha256": "0" * 64, "casos": 30}),
                        encoding="utf-8")
        with pytest.raises(banco.ErrorBanco) as exc:
            banco.cargar_corpus(banco.CORPUS_DEFECTO, malo)
        assert "sha256" in str(exc.value)

    def test_el_jsonl_es_append_only(self, tmp_path):
        assert banco.main(["--seco", "--salida", str(tmp_path),
                           "--sha-ejecutor", "abc123"]) == 0
        assert banco.main(["--seco", "--salida", str(tmp_path),
                           "--sha-ejecutor", "abc123"]) == 0
        lineas = (tmp_path / "registro.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lineas) == 16       # 8 por ejecución, no se reescribe
        assert all(json.loads(x)["sha_ejecutor"] == "abc123" for x in lineas)

    def test_el_informe_no_publica_rutas_y_usa_sha_explicito(self, tmp_path):
        assert banco.main(["--seco", "--salida", str(tmp_path),
                           "--sha-ejecutor", "abc123"]) == 0
        texto = (tmp_path / "informe.json").read_text(encoding="utf-8")
        assert str(tmp_path) not in texto
        assert "abc123" in texto and "no_disponible" not in texto

    def test_el_informe_calcula_el_tamano_real_del_corpus(self):
        corpus = _corpus()
        corpus["casos"] = corpus["casos"][:1]
        corpus["tamano_objetivo"] = 1
        corpus["estratos"] = {"serie": 1, "edicion_publicacion": 0,
                              "numero_formato": 0, "campo": 0}
        informe = banco.construir_informe(
            registros=[], corpus=corpus, corpus_sha="x", modo="seco",
            autorizacion=None, errores_autorizacion=[], sha_ejecutor="sha")
        pass_texto = " ".join(informe["pass_fail_not_run"]["PASS"])
        assert "1 casos" in pass_texto and "30 casos" not in pass_texto

    @pytest.mark.parametrize("valor", [
        "https://ejemplo.invalid", "ftp://servidor/x", "file:///etc/passwd",
        "C:\\Users\\coleccionista\\x", "token=abc", "password=123",
        "persona@ejemplo.invalid", "?q=secreto",
    ])
    def test_el_centinela_rechaza_esos_formatos(self, valor):
        assert banco._tiene_url_o_secreto(valor) is True

    def test_la_salida_se_escanea_antes_de_escribir_y_usa_lista_blanca(self):
        with pytest.raises(banco.ErrorBanco):
            banco.validar_salida([{"notas": "ftp://servidor/x"}], {"cobertura": "NOT RUN"})
        with pytest.raises(banco.ErrorBanco):
            banco.validar_salida([{"campo_inventado": 1}], {"cobertura": "NOT RUN"})


class TestAjustesRuntime:
    """ADR 0013: los interruptores viven en runtime_settings, no en el .env."""

    def test_el_overlay_de_ajustes_enciende_la_fuente(self, monkeypatch):
        from zascarr.config import get_settings

        async def valores(_url):
            return {"comicvine_enabled": True, "comicvine_api_key": "clave"}

        monkeypatch.setattr(banco, "_leer_valores_ajustes", valores)
        settings = get_settings()
        monkeypatch.setattr(settings, "comicvine_enabled", False)
        monkeypatch.setattr(settings, "comicvine_api_key", "")
        assert asyncio.run(banco.aplicar_ajustes_runtime("postgresql://x")) is True
        assert settings.comicvine_enabled is True
        assert banco._configuracion_fuente("comic_vine") == (True, None)

    def test_sin_fila_sigue_con_el_env_y_da_fuente_apagada(self, monkeypatch):
        from zascarr.config import get_settings

        async def sin_fila(_url):
            return None

        monkeypatch.setattr(banco, "_leer_valores_ajustes", sin_fila)
        monkeypatch.setattr(get_settings(), "comicvine_enabled", False)
        assert asyncio.run(banco.aplicar_ajustes_runtime("postgresql://x")) is False
        assert banco._configuracion_fuente("comic_vine") == (False, "fuente_apagada")

    def test_sin_database_url_no_intenta_leer(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("TEST_DATABASE_URL", raising=False)

        async def prohibido(_url):
            raise AssertionError("no se puede leer sin DATABASE_URL")
        monkeypatch.setattr(banco, "_leer_valores_ajustes", prohibido)
        assert asyncio.run(banco.aplicar_ajustes_runtime(None)) is False

    def test_el_ejecutor_aplica_ajustes_antes_de_comprobar_la_fuente(self, monkeypatch):
        corpus = _corpus_min(1)
        auth = _auth(casos=[corpus["casos"][0]["caso_id"]])
        aplicado = []

        async def overlay():
            aplicado.append(True)
            monkeypatch.setattr(banco, "_configuracion_fuente", lambda _f: (True, None))
        monkeypatch.setattr(banco, "aplicar_ajustes_runtime", overlay)
        plan = banco.plan_real(corpus, fuentes=["comic_vine"], unidades=["serie"])
        filas = asyncio.run(banco.ejecutar_real(
            plan, corpus, auth, max_peticiones=10, max_por_fuente=10,
            salida=Path("/tmp/x"), corpus_sha="sha-corpus", fuentes=["comic_vine"],
            cliente_factory=lambda _f: ClienteFalso(lambda q: [{"name": "x"}]),
            sha_ejecutor="abc", aplicar_ajustes=True))
        assert aplicado == [True]
        assert filas[0]["estado_tecnico"] == "ok"


class TestTextosDinamicosDelInforme:
    def test_corpus_acreditado_revision_y_titulo_real(self, tmp_path):
        corpus = _corpus()                     # 12 acreditados / 18 en borrador
        filas: list[dict] = []
        informe = banco.construir_informe(
            registros=filas, corpus=corpus, corpus_sha="sha", modo="real",
            autorizacion={"id": "piloto-cobertura-2026-11-06",
                          "concede": "juanajok (PO)",
                          "condiciones": "no publicar"},
            errores_autorizacion=[], sha_ejecutor="abc")
        pass_texto = " ".join(informe["pass_fail_not_run"]["PASS"])
        not_run = " ".join(informe["pass_fail_not_run"]["NOT RUN"])
        assert "12 acreditados / 18 en borrador" in pass_texto
        assert "NOT RUN hasta la revisión humana" in not_run
        assert "verificador: el PO" in not_run
        assert "ejecutado el" in not_run and "piloto-cobertura-2026-11-06" in not_run
        assert "pendiente de autorización" not in not_run
        banco.escribir_informe(informe, filas, tmp_path)
        md = (tmp_path / "informe.md").read_text(encoding="utf-8")
        assert "— ejecución real" in md and "— preparación" not in md
        serializado = json.dumps(informe, ensure_ascii=False)
        assert "concede" not in serializado and "juanajok" not in serializado
        assert set(informe["meta"]["autorizacion"]) == {
            "id", "ambito", "presupuesto_peticiones", "max_por_fuente",
            "desde", "hasta", "sha_corpus"}


class TestAutorizacionEfectiva:
    def _base(self, **extra):
        ahora = datetime.now(UTC)
        datos = {"id": "a", "ambito": ["comic_vine"], "presupuesto_peticiones": 80,
                 "desde": (ahora - timedelta(days=1)).isoformat(),
                 "hasta": (ahora + timedelta(days=1)).isoformat(),
                 "concede": "PO", "condiciones": "", "sha_corpus": "sha"}
        datos.update(extra)
        return datos

    def _plan(self, casos, fuentes=("comic_vine",), unidades=("serie",)):
        corpus = {"version": "v1", "casos": [{"caso_id": c} for c in casos]}
        return banco.plan_real(corpus, fuentes=list(fuentes), unidades=list(unidades))

    def test_tipos_estrictos_claves_no_permisibles_y_presupuesto_bool(self):
        errores = banco.validar_autorizacion(
            self._base(presupuesto_peticiones=True), sha_corpus="sha",
            fuentes=["comic_vine"])
        assert "presupuesto_invalido" in errores
        assert "claves_no_permitidas" in banco.validar_autorizacion(
            self._base(clave_extra=1), sha_corpus="sha", fuentes=["comic_vine"])
        assert "ambito_invalido" in banco.validar_autorizacion(
            self._base(ambito=["comic_vine:unidad_inventada"]), sha_corpus="sha",
            fuentes=["comic_vine"])

    def test_el_ambito_limita_capacidad_unidad_y_caso(self):
        plan = self._plan(["ES-001", "ES-002"], unidades=("serie", "edicion"))
        auth = self._base(ambito=["comic_vine:serie"])
        assert "fuera_de_ambito" in banco.validar_autorizacion(
            auth, sha_corpus="sha", fuentes=["comic_vine"], plan=plan)
        auth2 = self._base(ambito=["caso:ES-001"])
        assert "fuera_de_ambito" in banco.validar_autorizacion(
            auth2, sha_corpus="sha", fuentes=["comic_vine"], plan=plan)
        auth3 = self._base(ambito=["comic_vine"], casos=["ES-001", "ES-002"])
        assert banco.validar_autorizacion(auth3, sha_corpus="sha",
                                          fuentes=["comic_vine"], plan=plan) == []


class TestMapeoDeEstados:
    def test_mapea_las_excepciones_de_133_y_134(self):
        from zascarr.utils.cortesia import CortesiaEnEspera, FuenteApagada
        from zascarr.utils.peticiones import ReintentosAgotados

        assert banco.estado_desde_excepcion(
            CortesiaEnEspera("comic_vine", "host", 12.0)) == (
                "limite_de_cortesia", "limite_de_cortesia")
        assert banco.estado_desde_excepcion(FuenteApagada("anilist")) == (
            "no_ejecutado", "fuente_apagada")
        assert banco.estado_desde_excepcion(ReintentosAgotados("gcd", 2, 429)) == (
            "limite_de_cortesia", "limite_de_cortesia")
        assert banco.estado_desde_excepcion(ReintentosAgotados("gcd", 2, 500)) == (
            "fallo_transitorio", "fallo_transitorio")
        assert banco.estado_desde_excepcion(RuntimeError("boom")) == (
            "fallo_transitorio", "fallo_transitorio")

    def test_los_estados_tecnicos_incluyen_los_de_133_y_no_ejecutado(self):
        assert set(banco.ESTADOS_FUENTE_133) == {
            "ok", "sin_resultados", "fallo_transitorio", "limite_de_cortesia",
            "configuracion_incompleta", "fuente_apagada"}
        assert banco.ESTADOS_FUENTE_133 | {"no_ejecutado"} == banco.ESTADOS_TECNICOS


class TestMetricas:
    def _registro(self, caso_id: str, *, estado="ok", editorial=None, acreditada=True,
                  campos=("titulo",), ausentes=(), fuente="comic_vine", unidad="serie"):
        return {
            "fuente": fuente, "unidad": unidad, "caso_id": caso_id,
            "metodo": "test.metodo", "estado_tecnico": estado,
            "resultado_editorial": editorial,
            "revision": ({"veredicto": editorial} if editorial else
                         {"veredicto": None}),
            "campos_evaluados": list(campos), "campos_ausentes": list(ausentes),
            "motivo_no_ejecutado": None,
        }

    def _corpus(self, ids, *, acreditada=True):
        return {"version": "v1", "casos": [
            {"caso_id": i, "identidad_acreditada": acreditada,
             "acreditacion": "verificada" if acreditada else "borrador",
             "etiqueta_editorial": {"campos": {}}} for i in ids]}

    def test_denominador_cero_y_n_menor_que_10_no_publican_porcentaje(self):
        assert banco._tasa(0, 0)["porcentaje"] is None
        assert "sin base" in banco._tasa(0, 0)["nota"]
        tres = banco._tasa(2, 3)
        assert tres["porcentaje"] is None and "n<10" in tres["nota"]
        diez = banco._tasa(5, 10)
        assert diez["porcentaje"] == 50.0 and diez["numerador"] == 5 and diez["denominador"] == 10

    def test_precision_y_disponibilidad_se_calculan_por_separado(self):
        ids = [f"S{i}" for i in range(12)]
        corpus = self._corpus(ids)
        registros = []
        for i, caso_id in enumerate(ids):
            if i < 6:
                registros.append(self._registro(
                    caso_id, editorial="coincidencia_verificada"))
            elif i < 8:
                registros.append(self._registro(caso_id, editorial="ambiguo"))
            elif i < 10:
                registros.append(self._registro(caso_id, editorial="incorrecto"))
            else:
                registros.append(self._registro(caso_id, estado="fallo_transitorio"))
        metricas = banco.calcular_metricas(registros, corpus)
        grupo = metricas["por_fuente_unidad"]["comic_vine__serie"]
        assert grupo["planificados"] == 12 and grupo["ejecutados"] == 12
        assert grupo["coincidencias_verificadas"] == 6
        assert grupo["ambiguos"] == 2 and grupo["incorrectos"] == 2
        assert grupo["precision_editorial"]["denominador"] == 10
        assert grupo["precision_editorial"]["porcentaje"] == 60.0
        assert grupo["disponibilidad_tecnica"]["denominador"] == 12
        assert grupo["disponibilidad_tecnica"]["porcentaje"] == 83.3
        assert grupo["errores"] == 2

    def test_las_no_acreditadas_no_suman_a_coincidencias(self):
        corpus = self._corpus(["S1"], acreditada=False)
        registros = [self._registro("S1", editorial="coincidencia_verificada")]
        grupo = banco.calcular_metricas(registros, corpus)["por_fuente_unidad"]["comic_vine__serie"]
        assert grupo["evaluables"] == 0
        assert grupo["coincidencias_verificadas"] == 0
        assert grupo["no_acreditadas"] == 1

    def test_las_ausencias_son_sin_resultados_y_no_incorrectas(self):
        corpus = self._corpus(["S1"])
        registros = [self._registro("S1", estado="sin_resultados")]
        grupo = banco.calcular_metricas(registros, corpus)["por_fuente_unidad"]["comic_vine__serie"]
        assert grupo["ausencias"] == 1
        assert grupo["coincidencias_verificadas"] == 0
        assert grupo["incorrectos"] == 0
        assert grupo["cobertura_editorial_verificada"]["denominador"] == 1

    def test_no_ejecutado_no_cuenta_como_ausencia_ni_como_planificado(self):
        corpus = self._corpus(["S1", "S2"])
        registros = [self._registro("S1", estado="sin_resultados"),
                     self._registro("S2", estado="no_ejecutado")]
        registros[1]["metodo"] = None
        registros[1]["motivo_no_ejecutado"] = "fuente_apagada"
        grupo = banco.calcular_metricas(registros, corpus)["por_fuente_unidad"]["comic_vine__serie"]
        assert grupo["planificados"] == 1          # la celda sin método no se planifica
        assert grupo["no_ejecutados"] == 1
        assert grupo["ausencias"] == 1             # solo la sin_resultados acreditada
        assert grupo["evaluables"] == 1
        assert grupo["errores"] == 0               # no_ejecutado no es error

    def test_campos_faltantes_por_campo(self):
        corpus = self._corpus(["S1", "S2"])
        registros = [self._registro("S1", campos=("titulo", "editorial"), ausentes=("editorial",)),
                     self._registro("S2", campos=("titulo", "editorial"))]
        metricas = banco.calcular_metricas(registros, corpus)
        campo = metricas["por_campo"]["comic_vine__editorial"]
        assert campo["campos_evaluados"] == 2 and campo["campos_faltantes"] == 1
        assert campo["tasa_campo"]["porcentaje"] is None   # n=2 < 10


# ═══════════════════════════════════════════════════════════════════════════════
# PR-3: ejecutor real con cliente inyectado (cero red)
# ═══════════════════════════════════════════════════════════════════════════════

import asyncio  # noqa: E402

from zascarr.utils.peticiones import ReintentosAgotados  # noqa: E402


def _corpus_min(n: int = 4) -> dict:
    corpus = _corpus()
    corpus["casos"] = corpus["casos"][:n]
    corpus["tamano_objetivo"] = n
    corpus["estratos"] = {"serie": n, "edicion_publicacion": 0,
                          "numero_formato": 0, "campo": 0}
    return corpus


def _auth(sha: str = "sha-corpus", *, casos=None, ambito=None) -> dict:
    ahora = datetime.now(UTC)
    return {
        "id": "auth-test", "ambito": ambito or ["comic_vine"],
        "presupuesto_peticiones": 80, "max_por_fuente": 20,
        "casos": casos or [],
        "desde": (ahora - timedelta(days=1)).isoformat(),
        "hasta": (ahora + timedelta(days=1)).isoformat(),
        "concede": "PO", "condiciones": "prueba", "sha_corpus": sha,
    }


class ClienteFalso:
    def __init__(self, comportamiento):
        self._comportamiento = comportamiento

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None

    async def search_series(self, consulta):
        return self._comportamiento(consulta)

    async def search_manga(self, consulta):
        return self._comportamiento(consulta)


def _ejecutar(corpus, auth, *, max_peticiones=80, max_por_fuente=20, comportamiento=None,
              llamadas=None):
    plan = banco.plan_real(corpus, fuentes=["comic_vine"], unidades=["serie"])
    llamadas = llamadas if llamadas is not None else []

    def factory(_fuente):
        return ClienteFalso(lambda consulta: (llamadas.append(consulta) or
                                              comportamiento(consulta)))

    return asyncio.run(banco.ejecutar_real(
        plan, corpus, auth, max_peticiones=max_peticiones,
        max_por_fuente=max_por_fuente, salida=Path("/tmp/salida-inexistente"),
        corpus_sha="sha-corpus", fuentes=["comic_vine"],
        cliente_factory=factory, sha_ejecutor="abc",
        aplicar_ajustes=False)), llamadas


class TestEjecutorReal:
    def test_ejecuta_y_para_por_presupuesto(self, tmp_path, monkeypatch):
        corpus = _corpus_min(4)
        auth = _auth(casos=[c["caso_id"] for c in corpus["casos"]])
        monkeypatch.setattr(banco, "_configuracion_fuente", lambda _f: (True, None))
        filas, llamadas = _ejecutar(
            corpus, auth, max_peticiones=2,
            comportamiento=lambda q: [{"name": f"Resultado {q}"}])
        assert len(llamadas) == 2                     # cero peticiones fuera del presupuesto
        assert len(filas) == 4
        assert [f["estado_tecnico"] for f in filas[:2]] == ["ok", "ok"]
        assert all(f["estado_tecnico"] == "no_ejecutado" for f in filas[2:])
        assert all(f["motivo_no_ejecutado"] == "presupuesto_agotado" for f in filas[2:])
        assert filas[0]["peticiones"] == 1 and filas[0]["autorizacion"]["id"] == "auth-test"
        assert filas[-1]["condiciones"]["parada"] == "presupuesto"
        informe = banco.construir_informe(
            registros=filas, corpus=corpus, corpus_sha="sha-corpus", modo="real",
            autorizacion=auth, errores_autorizacion=[], sha_ejecutor="abc")
        assert informe["cobertura"] == "NOT RUN"
        assert informe["pass_fail_not_run"]["PASS"]
        assert "NOT RUN" in informe["pass_fail_not_run"]

    def test_fuente_apagada_no_hace_ninguna_peticion(self, monkeypatch):
        corpus = _corpus_min(3)
        auth = _auth(casos=[c["caso_id"] for c in corpus["casos"]])
        monkeypatch.setattr(banco, "_configuracion_fuente",
                            lambda _f: (False, "fuente_apagada"))
        filas, llamadas = _ejecutar(
            corpus, auth, comportamiento=lambda q: (_ for _ in ()).throw(
                AssertionError("no se puede llamar")))
        assert llamadas == []
        assert len(filas) == 3
        assert all(f["estado_tecnico"] == "no_ejecutado" for f in filas)
        assert all(f["motivo_no_ejecutado"] == "fuente_apagada" for f in filas)
        assert filas[0]["estado_fuente_133"] == "fuente_apagada"
        assert filas[-1]["condiciones"]["parada"] == "fuente_apagada"

    def test_429_es_limite_de_cortesia_sin_reintento_extra(self, monkeypatch):
        corpus = _corpus_min(3)
        auth = _auth(casos=[c["caso_id"] for c in corpus["casos"]])
        monkeypatch.setattr(banco, "_configuracion_fuente", lambda _f: (True, None))

        def boom(_q):
            raise ReintentosAgotados("comic_vine", 3, 429)
        filas, llamadas = _ejecutar(corpus, auth, comportamiento=boom)
        assert len(llamadas) == 1                    # el cliente ya agotó sus reintentos
        assert len(filas) == 3
        assert filas[0]["estado_tecnico"] == "limite_de_cortesia"
        assert filas[0]["peticiones"] == 3 and filas[0]["reintentos"] == 2
        assert all(f["motivo_no_ejecutado"] == "fuera_de_alcance" for f in filas[1:])
        assert filas[-1]["condiciones"]["parada"] == "limite_de_cortesia"

    def test_tres_fallos_consecutivos_detienen_la_fuente(self, monkeypatch):
        corpus = _corpus_min(5)
        auth = _auth(casos=[c["caso_id"] for c in corpus["casos"]])
        monkeypatch.setattr(banco, "_configuracion_fuente", lambda _f: (True, None))

        def boom(_q):
            raise RuntimeError("red")
        filas, llamadas = _ejecutar(corpus, auth, comportamiento=boom)
        assert len(llamadas) == 3
        assert [f["estado_tecnico"] for f in filas[:3]] == ["fallo_transitorio"] * 3
        assert all(f["estado_tecnico"] == "no_ejecutado" for f in filas[3:])
        assert filas[-1]["condiciones"]["parada"] == "fallos_transitorios"

    def test_una_espera_de_cortesia_no_cuenta_como_peticion(self, monkeypatch):
        corpus = _corpus_min(2)
        auth = _auth(casos=[c["caso_id"] for c in corpus["casos"]])
        monkeypatch.setattr(banco, "_configuracion_fuente", lambda _f: (True, None))
        from zascarr.utils.cortesia import CortesiaEnEspera

        def espera(_q):
            raise CortesiaEnEspera("comic_vine", "host", 60.0, "bloqueo_fuente")
        filas, llamadas = _ejecutar(corpus, auth, comportamiento=espera)
        assert len(llamadas) == 1
        assert filas[0]["estado_tecnico"] == "limite_de_cortesia"
        assert filas[0]["peticiones"] == 0 and filas[0]["reintentos"] == 0
        assert filas[-1]["condiciones"]["parada"] == "limite_de_cortesia"

    def test_revalida_el_permiso_y_no_confia_en_el_llamador(self):
        corpus = _corpus_min(2)
        auth = _auth(casos=[c["caso_id"] for c in corpus["casos"]])
        auth["sha_corpus"] = "sha-distinto"
        with pytest.raises(PermissionError):
            _ejecutar(corpus, auth, comportamiento=lambda q: [])

    def test_el_ambito_por_caso_se_revalida_en_el_ejecutor(self):
        corpus = _corpus_min(2)
        auth = _auth(casos=[corpus["casos"][0]["caso_id"]], ambito=["comic_vine"])
        plan = banco.plan_real(corpus, fuentes=["comic_vine"], unidades=["serie"])
        # El plan filtrado por el CLI puede traer el segundo caso: la revalidación lo rechaza.
        with pytest.raises(PermissionError):
            asyncio.run(banco.ejecutar_real(
                plan, corpus, auth, max_peticiones=10, max_por_fuente=10,
                salida=Path("/tmp/x"), corpus_sha="sha-corpus", fuentes=["comic_vine"]))


class TestTopePorFuente:
    def _plan_dos_fuentes(self, corpus):
        return banco.plan_real(corpus, fuentes=["comic_vine", "anilist"],
                               unidades=["serie"])

    def _auth_dos(self, corpus):
        return _auth(casos=[c["caso_id"] for c in corpus["casos"]],
                     ambito=["comic_vine", "anilist"])

    def test_el_tope_de_una_fuente_no_detiene_a_las_demas(self, monkeypatch):
        corpus = _corpus_min(2)
        auth = self._auth_dos(corpus)
        monkeypatch.setattr(banco, "_configuracion_fuente", lambda _f: (True, None))
        plan = self._plan_dos_fuentes(corpus)
        # Orden explícito: primero las dos celdas de CV, luego las de AniList.
        plan = ([c for c in plan if c["fuente"] == "comic_vine"]
                + [c for c in plan if c["fuente"] == "anilist"])
        llamadas = []
        filas = asyncio.run(banco.ejecutar_real(
            plan, corpus, auth, max_peticiones=10, max_por_fuente=1,
            salida=Path("/tmp/x"), corpus_sha="sha-corpus",
            fuentes=["comic_vine", "anilist"],
            cliente_factory=lambda _f: ClienteFalso(
                lambda q: (llamadas.append(q) or [{"name": "x"}])),
            sha_ejecutor="abc", aplicar_ajustes=False))
        assert len(llamadas) == 2                       # una por fuente
        assert filas[0]["estado_tecnico"] == "ok"        # CV case1
        assert filas[1]["motivo_no_ejecutado"] == "limite_por_fuente"
        assert filas[2]["estado_tecnico"] == "ok"        # AniList sigue
        assert filas[3]["motivo_no_ejecutado"] == "limite_por_fuente"
        assert all(f["condiciones"]["parada"] == "final" for f in filas)

    def test_el_tope_global_si_detiene_todo(self, monkeypatch):
        corpus = _corpus_min(2)
        auth = self._auth_dos(corpus)
        monkeypatch.setattr(banco, "_configuracion_fuente", lambda _f: (True, None))
        plan = self._plan_dos_fuentes(corpus)
        llamadas = []
        filas = asyncio.run(banco.ejecutar_real(
            plan, corpus, auth, max_peticiones=1, max_por_fuente=10,
            salida=Path("/tmp/x"), corpus_sha="sha-corpus",
            fuentes=["comic_vine", "anilist"],
            cliente_factory=lambda _f: ClienteFalso(
                lambda q: (llamadas.append(q) or [{"name": "x"}])),
            sha_ejecutor="abc", aplicar_ajustes=False))
        assert len(llamadas) == 1
        assert filas[0]["estado_tecnico"] == "ok"
        assert all(f["motivo_no_ejecutado"] == "presupuesto_agotado" for f in filas[1:])
        assert filas[-1]["condiciones"]["parada"] == "presupuesto"

    def test_limite_por_fuente_no_se_presenta_como_presupuesto_agotado(self, monkeypatch):
        corpus = _corpus_min(2)
        auth = self._auth_dos(corpus)
        monkeypatch.setattr(banco, "_configuracion_fuente", lambda _f: (True, None))
        plan = banco.plan_real(corpus, fuentes=["comic_vine"], unidades=["serie"])
        filas = asyncio.run(banco.ejecutar_real(
            plan, corpus, auth, max_peticiones=10, max_por_fuente=1,
            salida=Path("/tmp/x"), corpus_sha="sha-corpus", fuentes=["comic_vine"],
            cliente_factory=lambda _f: ClienteFalso(lambda q: [{"name": "x"}]),
            sha_ejecutor="abc", aplicar_ajustes=False))
        assert filas[1]["motivo_no_ejecutado"] == "limite_por_fuente"
        assert filas[1]["motivo_no_ejecutado"] != "presupuesto_agotado"
        assert "limite_por_fuente" in banco.MOTIVOS_NO_EJECUTADO


class TestCandidatosAniList:
    def test_ani_list_usa_title_romaji_o_title_english_y_solo_id_y_etiqueta(self):
        from zascarr.services.anilist import AniListResult

        romaji = AniListResult(anilist_id=42, title_romaji="Dragon Ball",
                               title_english="Dragon Ball Z")
        sin_romaji = AniListResult(anilist_id=43, title_romaji=None,
                                   title_english="One Piece")
        candidatos = banco._candidatos_saneados([romaji, sin_romaji])
        assert candidatos[0] == {"rank": 1, "id_externo": "42",
                                 "etiqueta_propuesta": "Dragon Ball"}
        assert candidatos[1]["etiqueta_propuesta"] == "One Piece"
        assert all(set(c) == {"rank", "id_externo", "etiqueta_propuesta"}
                   for c in candidatos)
