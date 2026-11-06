# ruff: noqa: E501
"""`scripts/medicion/banco_cobertura.py` (#135): arnés en seco, fail-closed y métricas.

Sin Postgres y sin red: el modo seco usa fixtures saneados; el modo real sin autorización no
construye clientes. Ningún test lanza cobertura real (PR-3, con permiso separado).
"""
from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta

import pytest

from scripts.medicion import banco_cobertura as banco


def _corpus() -> dict:
    return json.loads(banco.CORPUS_DEFECTO.read_text(encoding="utf-8"))


class TestCorpus:
    def test_el_corpus_v1_es_borrador_de_30_casos_y_su_sha_coincide(self):
        corpus, sha = banco.cargar_corpus(banco.CORPUS_DEFECTO)
        assert len(corpus["casos"]) == 30
        assert corpus["tamano_objetivo"] == 30
        assert sha == banco.sha256_archivo(banco.CORPUS_DEFECTO)
        assert all(c["acreditacion"] == "borrador" for c in corpus["casos"])
        assert all(not c["identidad_acreditada"] for c in corpus["casos"])
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
        datos["casos"][0]["identidad_acreditada"] = True   # sin acreditacion=verificada
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
        assert "PASS" in (tmp_path / "informe.md").read_text(encoding="utf-8")
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
        assert banco.main(self._args(tmp_path, "--autorizacion", str(ruta))) == 2
        datos["hasta"] = (ahora + timedelta(days=1)).isoformat()
        datos["ambito"] = ["anilist"]                             # fuera de ámbito
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        assert banco.main(self._args(tmp_path, "--autorizacion", str(ruta))) == 2

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
            "estado_tecnico": estado,
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

    def test_campos_faltantes_por_campo(self):
        corpus = self._corpus(["S1", "S2"])
        registros = [self._registro("S1", campos=("titulo", "editorial"), ausentes=("editorial",)),
                     self._registro("S2", campos=("titulo", "editorial"))]
        metricas = banco.calcular_metricas(registros, corpus)
        campo = metricas["por_campo"]["comic_vine__editorial"]
        assert campo["campos_evaluados"] == 2 and campo["campos_faltantes"] == 1
        assert campo["tasa_campo"]["porcentaje"] is None   # n=2 < 10
