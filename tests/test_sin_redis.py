# ruff: noqa: E501
"""ADR 0011 — Redis se retiró del stack: lo que antes eran un servicio, dos dependencias y una promesa de la
documentación no puede volver «por descuido». Pruebas de texto y de código fuente: sin base de datos ni Docker.

Cada prueba cierra una de las formas en que Redis podía seguir ahí sin que nadie lo usara: el servicio, el entorno, la
dependencia, el cliente y las dos órdenes de los scripts que lo tocaban."""
from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SRC = RAIZ / "src" / "zascarr"


def _compose() -> str:
    return (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")


class TestCompose:

    def test_no_hay_servicio_redis_ni_imagen_ni_volumen(self):
        c = _compose()
        assert not re.search(r"^  redis:\s*$", c, re.M)
        assert "redis:7" not in c and "redis-server" not in c and "/redis:/data" not in c

    def test_la_app_no_recibe_redis_url_ni_depende_de_redis(self):
        c = _compose()
        assert "REDIS_URL" not in c
        assert not re.search(r"depends_on:(?:\n\s+\S.*)*?\n\s+redis:", c)


class TestCodigo:

    def _modulos(self):
        return sorted(SRC.rglob("*.py"))

    @pytest.mark.parametrize("paquete", ["redis", "arq"])
    def test_ningun_modulo_importa_el_cliente(self, paquete):
        importan = []
        for p in self._modulos():
            for nodo in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                nombres = []
                if isinstance(nodo, ast.Import):
                    nombres = [a.name for a in nodo.names]
                elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                    nombres = [nodo.module]
                if any(n == paquete or n.startswith(paquete + ".") for n in nombres):
                    importan.append(str(p.relative_to(RAIZ)))
        assert importan == []

    def test_la_configuracion_ya_no_tiene_campos_de_redis(self):
        from zascarr.config import Settings
        assert not [n for n in Settings.model_fields if "redis" in n.lower()]

    def test_un_redis_url_heredado_en_el_entorno_se_ignora(self, monkeypatch):
        """Un `.env` de una instalación anterior puede traerla: no puede romper el arranque."""
        from zascarr.config import Settings
        monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
        assert Settings() is not None


class TestDependencias:

    def test_pyproject_no_declara_redis_ni_arq(self):
        deps = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
        nombres = {re.split(r"[\[<>=!~ ]", d, maxsplit=1)[0].lower() for d in deps}
        assert not nombres & {"redis", "arq"}, nombres & {"redis", "arq"}


class TestScripts:

    def test_bootstrap_no_crea_ni_levanta_redis(self):
        t = (RAIZ / "bootstrap.sh").read_text(encoding="utf-8")
        assert "up -d postgres redis" not in t and "{postgres,redis," not in t
        assert re.search(r"up -d postgres\b", t)

    def test_update_retira_el_contenedor_heredado(self):
        t = (RAIZ / "scripts" / "update.sh").read_text(encoding="utf-8")
        assert "up -d --remove-orphans zascarr" in t

    def test_rollback_ya_no_vacia_ninguna_cache(self):
        t = (RAIZ / "scripts" / "rollback.sh").read_text(encoding="utf-8")
        assert "redis-cli" not in t and "exec -T redis" not in t and "FLUSHDB" not in t

    def test_la_purga_sigue_limpiando_el_directorio_heredado(self):
        """`redis/` puede existir en instalaciones anteriores: `--purge` tiene que seguir borrándolo."""
        t = (RAIZ / "scripts" / "uninstall.sh").read_text(encoding="utf-8")
        assert "/purgar/redis" in t and "--remove-orphans" in t


class TestDocumentacionViva:

    @pytest.mark.parametrize("ruta", ["README.md", "docs/TESTING_E2E.md", "docs/TESTING_NFR_Zascarr.md"])
    def test_las_guias_no_mandan_a_tocar_un_redis(self, ruta):
        t = (RAIZ / ruta).read_text(encoding="utf-8")
        assert "redis-cli" not in t and "up -d postgres redis" not in t and "exec -T redis" not in t

    def test_claude_md_ya_no_afirma_que_haya_redis(self):
        t = (RAIZ / "CLAUDE.md").read_text(encoding="utf-8")
        assert "PostgreSQL + Redis" not in t and "usa Redis como canal" not in t
        assert "ADR-0011" in t

    def test_el_adr_existe_y_esta_en_la_tabla_de_documentos_vivos(self):
        assert (RAIZ / "docs" / "adr" / "0011-retirar-redis.md").is_file()
