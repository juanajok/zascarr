#!/usr/bin/env python3
"""Banco de cobertura española (#135, MIT-M8-US03) — **arnés en seco**.

Implementa el corte PR-1+PR-2 de `docs/design/banco-cobertura-espanola.md`: corpus v1 en
borrador y el arnés que valida el registro, los estados, las métricas y el informe **sin
ejecutar cobertura real**.

- `--seco`: lee fixtures saneados versionados; no importa/construye clientes ni llama a
  `pedir_con_cortesia`; no abre sockets. La cobertura es **NOT RUN**: los sintéticos validan el
  arnés, no acreditan cobertura.
- `--real`: exige una autorización versionada (ámbito, presupuesto, caducidad y SHA del corpus).
  Sin autorización válida: **exit 2, cero peticiones** y filas `no_ejecutado: sin_autorizacion`.
  En esta entrega no se lanza ninguna ejecución real.

Estados técnicos y de fuente: reutiliza el conjunto cerrado de #133
(`services.discovery.ESTADOS_DE_FUENTE`) y los errores de #134 (`utils/peticiones.py`); no
redefine ninguno. `no_ejecutado` es **solo del banco** (no entra en #133).

Privacidad: el registro y los informes no llevan URL, query, claves, cabeceras ni datos
personales. El JSONL es append-only (si se relanza, se escribe otro fichero de ejecución).

Uso:
  python scripts/medicion/banco_cobertura.py --seco \\
      --corpus docs/design/corpus-cobertura-v1.json \\
      --fixtures docs/design/fixtures-cobertura/seco.json \\
      --salida docs/design/medicion-cobertura-2026-11-06

  # Solo con autorización aprobada (NO ejecutar en la entrega de preparación):
  python scripts/medicion/banco_cobertura.py --real --autorizacion <ruta> ...
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from zascarr.services.estados_fuentes import ESTADOS_DE_FUENTE

RAIZ = Path(__file__).resolve().parents[2]
CORPUS_DEFECTO = RAIZ / "docs" / "design" / "corpus-cobertura-v1.json"
FIXTURES_DEFECTO = RAIZ / "docs" / "design" / "fixtures-cobertura" / "seco.json"
SALIDA_DEFECTO = RAIZ / "docs" / "design" / "medicion-cobertura-2026-11-06"

#: Estados técnicos del registro: el conjunto de #133 + `no_ejecutado` (solo banco, §4.2).
ESTADOS_TECNICOS = set(ESTADOS_DE_FUENTE) | {"no_ejecutado"}
ESTADOS_FUENTE_133 = set(ESTADOS_DE_FUENTE)
RESULTADOS_EDITORIALES = {"coincidencia_verificada", "ambiguo", "incorrecto"}
MOTIVOS_NO_EJECUTADO = {
    "sin_autorizacion", "modo_seco", "fuente_apagada", "configuracion_incompleta",
    "presupuesto_agotado", "sin_metodo_autorizado", "fuera_de_alcance",
}
UNIDADES = {"serie", "edicion", "publicacion", "numero", "formato", "campo"}
ESTRATOS = {"serie", "edicion_publicacion", "numero_formato", "campo"}
PROCEDENCIAS = {
    "copia_propia", "isbn", "deposito_legal", "catalogo_publico", "dependiente_de_la_fuente",
}
FUENTES = {"comic_vine", "anilist", "tebeosfera", "gcd"}

#: Mapa de capacidad técnica usada SOLO como identificador de ensayo; no publica capacidades
#: nuevas en #133.
CAPACIDAD_POR_UNIDAD = {
    "serie": "busqueda_serie",
    "edicion": "identidad_edicion",
    "publicacion": "busqueda_publicacion",
    "numero": "numero",
    "formato": "formato",
    "campo": "campo",
}

#: Métodos autorizados (los del código vigente; la web no acredita nada). `None` = no probar.
METODOS: dict[str, dict[str, str | None]] = {
    "comic_vine": {
        "serie": "ComicVineClient.search_series",
        "publicacion": "ComicVineClient.find_issue",
        "numero": "ComicVineClient.find_issue",
        "campo": "ComicVineClient.get_issue_detail",
    },
    "anilist": {"serie": "AniListClient.search_manga", "campo": "AniListClient.search_manga"},
    "tebeosfera": {
        "serie": "TebeosferaClient.search_series",
        "edicion": "TebeosferaClient.search_series",
        "publicacion": "TebeosferaClient.search_series",
        "formato": "TebeosferaClient.search_series",
        "campo": "TebeosferaClient.search_series",
    },
    "gcd": {
        "serie": "GCDClient.search_series",
        "edicion": "GCDClient.search_series",
        "campo": "GCDClient.search_series",
    },
}

#: Por debajo de este denominador no se publican porcentajes (solo cantidades, §5).
UMBRAL_PORCENTAJE = 10


class ErrorBanco(Exception):  # noqa: N818 — nombre del contrato de error del arnés
    """El corpus, las fixtures o la autorización no son válidos."""


def ahora_utc() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def sha256_bytes(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def sha256_archivo(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _leer_json(path: Path) -> Any:
    """Lee JSON una vez, en bytes; un fichero no-UTF8 es un error del banco, no un traceback."""
    try:
        datos = path.read_bytes()
    except OSError as exc:
        raise ErrorBanco(f"no se pudo leer {path.name}") from exc
    try:
        return json.loads(datos.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ErrorBanco(f"{path.name} no es JSON UTF-8 válido") from exc


MANIFIESTO_DEFECTO = RAIZ / "docs" / "design" / "banco-cobertura" / "manifiesto-corpus-v1.json"


def _comparar_manifiesto(manifiesto: Path, *, sha: str, casos: int) -> None:
    datos = _leer_json(manifiesto)
    if not isinstance(datos, dict) or not isinstance(datos.get("sha256"), str):
        raise ErrorBanco("manifiesto sin sha256")
    if datos["sha256"] != sha:
        raise ErrorBanco("el sha256 del corpus no coincide con el manifiesto")
    if datos.get("casos") != casos:
        raise ErrorBanco("el número de casos no coincide con el manifiesto")


# ── Corpus ─────────────────────────────────────────────────────────────────────────────────────

_PATRONES_SENSIBLES = (
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"\b(?:ftp|file|smb|mailto|gopher)://", re.IGNORECASE),
    re.compile(r"[a-z]:\\", re.IGNORECASE),                       # C:\...
    re.compile(r"\b(?:api[_-]?key|token|password|passwd|secret|authorization|cookie|bearer)\b\s*[:=]",
               re.IGNORECASE),
    re.compile(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", re.IGNORECASE),   # email
    re.compile(r"[?&][a-z_][a-z0-9_]*=", re.IGNORECASE),            # query string
)


def _tiene_url_o_secreto(valor: Any) -> bool:
    """Centinela de privacidad: URL de cualquier esquema, ruta Windows, query, token o email."""
    if isinstance(valor, dict):
        return any(_tiene_url_o_secreto(k) or _tiene_url_o_secreto(v) for k, v in valor.items())
    if isinstance(valor, (list, tuple)):
        return any(_tiene_url_o_secreto(v) for v in valor)
    if not isinstance(valor, str):
        return False
    return any(patron.search(valor) for patron in _PATRONES_SENSIBLES)


CLAVES_CORPUS = {"version", "creado", "criterios_inclusion", "tamano_objetivo", "estratos",
                 "acreditacion", "nota", "casos"}
CLAVES_CASO = {"caso_id", "estrato", "consulta", "unidad_esperada", "etiqueta_editorial",
               "identidad_acreditada", "acreditacion", "estado_identidad", "procedencia",
               "evidencia", "verificador", "fecha_verificacion", "desacuerdo", "notas"}
CLAVES_ETIQUETA = {"obra", "serie", "editorial", "coleccion", "pais", "idioma", "edicion",
                   "numero", "formato", "anio", "campos"}
CLAVES_FIXTURES = {"version", "descripcion", "seed", "ensayos"}
CLAVES_ENSAYO = {"caso_id", "fuente", "capacidad", "unidad", "metodo", "estado_tecnico",
                 "estado_fuente_133", "motivo_no_ejecutado", "reintentar_en", "candidatos",
                 "campos_evaluados", "campos_presentes", "campos_ausentes", "notas"}


def validar_corpus(datos: Any) -> None:
    if not isinstance(datos, dict):
        raise ErrorBanco("el corpus tiene que ser un objeto JSON")
    if set(datos) - CLAVES_CORPUS:
        raise ErrorBanco("el corpus tiene campos fuera de la lista blanca")
    for clave in ("version", "casos", "tamano_objetivo"):
        if clave not in datos:
            raise ErrorBanco(f"al corpus le falta «{clave}»")
    casos = datos["casos"]
    if not isinstance(casos, list) or not casos:
        raise ErrorBanco("«casos» tiene que ser una lista no vacía")
    if datos["tamano_objetivo"] != len(casos):
        raise ErrorBanco("«tamano_objetivo» no coincide con el número de casos")
    if _tiene_url_o_secreto(datos):
        raise ErrorBanco("el corpus contiene URL, query o una clave")
    vistos: set[str] = set()
    for caso in casos:
        if not isinstance(caso, dict):
            raise ErrorBanco("cada caso tiene que ser un objeto")
        if set(caso) - CLAVES_CASO:
            raise ErrorBanco(f"{caso.get('caso_id', '?')}: campos fuera de la lista blanca")
        for clave in ("caso_id", "estrato", "consulta", "unidad_esperada",
                      "etiqueta_editorial", "identidad_acreditada", "acreditacion",
                      "procedencia", "verificador"):
            if clave not in caso:
                raise ErrorBanco(f"caso sin «{clave}»")
        caso_id = caso["caso_id"]
        if not isinstance(caso_id, str) or not caso_id or caso_id in vistos:
            raise ErrorBanco("caso_id vacío o duplicado")
        vistos.add(caso_id)
        if caso["estrato"] not in ESTRATOS:
            raise ErrorBanco(f"{caso_id}: estrato desconocido")
        if caso["unidad_esperada"] not in UNIDADES:
            raise ErrorBanco(f"{caso_id}: unidad desconocida")
        if not isinstance(caso["identidad_acreditada"], bool):
            raise ErrorBanco(f"{caso_id}: identidad_acreditada tiene que ser booleana")
        acreditacion = caso.get("acreditacion")
        if acreditacion not in {"borrador", "verificada", "sin_identidad_acreditada"}:
            raise ErrorBanco(f"{caso_id}: acreditacion desconocida")
        if caso["identidad_acreditada"] and acreditacion != "verificada":
            raise ErrorBanco(f"{caso_id}: identidad acreditada exige acreditacion=verificada")
        if caso["procedencia"] not in PROCEDENCIAS:
            raise ErrorBanco(f"{caso_id}: procedencia no permitida")
        etiqueta = caso["etiqueta_editorial"]
        if not isinstance(etiqueta, dict) or not isinstance(etiqueta.get("campos", {}), dict):
            raise ErrorBanco(f"{caso_id}: etiqueta_editorial inválida")
        if set(etiqueta) - CLAVES_ETIQUETA:
            raise ErrorBanco(f"{caso_id}: etiqueta con campos fuera de la lista blanca")
        for clave in ("obra", "serie", "editorial", "coleccion", "pais", "idioma",
                      "edicion", "numero", "formato", "anio", "campos"):
            if clave not in etiqueta:
                raise ErrorBanco(f"{caso_id}: etiqueta sin «{clave}»")
    estratos = datos.get("estratos")
    if estratos is not None and (
            not isinstance(estratos, dict) or sum(estratos.values()) != len(casos)):
        raise ErrorBanco("«estratos» no suma el número de casos")


def cargar_corpus(path: Path, manifiesto: Path | None = None) -> tuple[dict, str]:
    """Lee el corpus UNA vez en bytes: hashea esos bytes, parsea de ahí y compara el manifiesto."""
    try:
        crudo = path.read_bytes()
    except OSError as exc:
        raise ErrorBanco(f"no se pudo leer {path.name}") from exc
    sha = sha256_bytes(crudo)
    try:
        datos = json.loads(crudo.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ErrorBanco(f"{path.name} no es JSON UTF-8 válido") from exc
    validar_corpus(datos)
    if manifiesto is not None:
        _comparar_manifiesto(manifiesto, sha=sha, casos=len(datos["casos"]))
    return datos, sha


def casos_por_id(corpus: dict) -> dict[str, dict]:
    return {caso["caso_id"]: caso for caso in corpus["casos"]}


# ── Fixtures (modo seco) ──────────────────────────────────────────────────────────────────────

def validar_fixtures(datos: Any, corpus: dict) -> None:
    if not isinstance(datos, dict) or not isinstance(datos.get("ensayos"), list):
        raise ErrorBanco("las fixtures tienen que tener «ensayos»")
    if set(datos) - CLAVES_FIXTURES:
        raise ErrorBanco("las fixtures tienen campos fuera de la lista blanca")
    if _tiene_url_o_secreto(datos):
        raise ErrorBanco("las fixtures contienen URL, query o una clave")
    casos = casos_por_id(corpus)
    for ensayo in datos["ensayos"]:
        if not isinstance(ensayo, dict):
            raise ErrorBanco("un ensayo de fixture no es un objeto")
        if set(ensayo) - CLAVES_ENSAYO:
            raise ErrorBanco("un ensayo de fixture tiene campos fuera de la lista blanca")
        for clave in ("caso_id", "fuente", "capacidad", "unidad", "estado_tecnico"):
            if clave not in ensayo:
                raise ErrorBanco(f"ensayo de fixture sin «{clave}»")
        if ensayo["caso_id"] not in casos:
            raise ErrorBanco(f"fixture con caso desconocido: {ensayo['caso_id']}")
        if ensayo["fuente"] not in FUENTES:
            raise ErrorBanco("fixture con fuente desconocida")
        if ensayo["unidad"] not in UNIDADES:
            raise ErrorBanco("fixture con unidad desconocida")
        if ensayo["estado_tecnico"] not in ESTADOS_TECNICOS:
            raise ErrorBanco("fixture con estado técnico fuera del conjunto")
        if (ensayo["estado_tecnico"] == "no_ejecutado"
                and ensayo.get("motivo_no_ejecutado") not in MOTIVOS_NO_EJECUTADO):
            raise ErrorBanco("fixture no_ejecutado sin motivo válido")
        estado133 = ensayo.get("estado_fuente_133")
        if estado133 is not None and estado133 not in ESTADOS_FUENTE_133:
            raise ErrorBanco("fixture con estado de fuente #133 desconocido")


def cargar_fixtures(path: Path, corpus: dict) -> dict:
    datos = _leer_json(path)
    validar_fixtures(datos, corpus)
    return datos


# ── Registro ─────────────────────────────────────────────────────────────────────────────────

def _hash_saneado(contenido: Any) -> str:
    return sha256_bytes(json.dumps(contenido, ensure_ascii=False, sort_keys=True).encode())


def _registro(
    *, caso: dict, corpus_version: str, fuente: str, capacidad: str, unidad: str,
    metodo: str | None, estado_tecnico: str, estado_fuente_133: str | None,
    motivo_no_ejecutado: str | None, peticiones: int, reintentos: int,
    resultado_editorial: str | None, campos_evaluados: Sequence[str],
    campos_presentes: Sequence[str], campos_ausentes: Sequence[str],
    candidatos: Sequence[dict], modo: str, condiciones: dict,
    hash_respuesta: str | None = None, revision: dict | None = None,
    notas: str = "", sha_ejecutor: str = "no_disponible",
) -> dict:
    ensayo_id = f"{caso['caso_id']}__{fuente}__{unidad}__1"
    return {
        "ensayo_id": ensayo_id,
        "corpus_version": corpus_version,
        "caso_id": caso["caso_id"],
        "fuente": fuente,
        "capacidad": capacidad,
        "unidad": unidad,
        "metodo": metodo,
        "sha_ejecutor": sha_ejecutor,
        "modo": modo,
        "autorizacion": None,
        "estado_tecnico": estado_tecnico,
        "estado_fuente_133": estado_fuente_133,
        "motivo_no_ejecutado": motivo_no_ejecutado,
        "peticiones": peticiones,
        "reintentos": reintentos,
        "resultado_editorial": resultado_editorial,
        "campos_evaluados": list(campos_evaluados),
        "campos_presentes": list(campos_presentes),
        "campos_ausentes": list(campos_ausentes),
        "candidatos": list(candidatos),
        "revision": revision or {"verificador": None, "fecha": None,
                                 "veredicto": None, "evidencia": None},
        "desacuerdo": None,
        "condiciones": condiciones,
        "hash_respuesta": hash_respuesta,
        "notas": notas,
    }


def registros_seco(fixtures: dict, corpus: dict, autorizacion: dict | None = None,
                   *, sha_ejecutor: str = "no_disponible") -> list[dict]:
    """Convierte fixtures saneados en registros. NO ejecuta peticiones ni construye clientes."""
    casos = casos_por_id(corpus)
    condiciones = {
        "fecha": _iso(ahora_utc()), "red": "fixture", "fuentes_encendidas": [],
        "presupuesto": 0, "parada": "final",
    }
    filas = []
    for ensayo in fixtures["ensayos"]:
        caso = casos[ensayo["caso_id"]]
        campos_evaluados = list(ensayo.get("campos_evaluados") or [])
        presentes = list(ensayo.get("campos_presentes") or [])
        ausentes = list(ensayo.get("campos_ausentes") or [])
        candidatos = list(ensayo.get("candidatos") or [])
        filas.append(_registro(
            caso=caso, corpus_version=corpus["version"], fuente=ensayo["fuente"],
            capacidad=ensayo["capacidad"], unidad=ensayo["unidad"],
            metodo=ensayo.get("metodo"),
            estado_tecnico=ensayo["estado_tecnico"],
            estado_fuente_133=ensayo.get("estado_fuente_133"),
            motivo_no_ejecutado=ensayo.get("motivo_no_ejecutado"),
            peticiones=0, reintentos=0,
            resultado_editorial=None,            # un sintético NUNCA acredita editorial
            campos_evaluados=campos_evaluados, campos_presentes=presentes,
            campos_ausentes=ausentes, candidatos=candidatos,
            modo="seco", condiciones={**condiciones, "parada": "final"},
            sha_ejecutor=sha_ejecutor,
            hash_respuesta=_hash_saneado({"candidatos": candidatos,
                                          "campos": {"evaluados": campos_evaluados,
                                                     "presentes": presentes,
                                                     "ausentes": ausentes}}),
            notas=ensayo.get("notas", ""),
        ))
    if autorizacion:
        for fila in filas:
            fila["autorizacion"] = autorizacion
    return filas


# ── Autorización (modo real) ─────────────────────────────────────────────────────────────────

def _parsear_fecha(valor: Any) -> datetime | None:
    """Fecha ISO; si no trae zona se interpreta como UTC (nunca revienta con TypeError)."""
    if not isinstance(valor, str) or not valor:
        return None
    try:
        fecha = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return fecha.replace(tzinfo=UTC) if fecha.tzinfo is None else fecha


CLAVES_AUTORIZACION = {
    "id", "ambito", "presupuesto_peticiones", "max_por_fuente", "casos",
    "desde", "hasta", "concede", "condiciones", "sha_corpus",
}


def _ambito_valido(entrada: Any) -> bool:
    if not isinstance(entrada, str) or not entrada.strip():
        return False
    if entrada.startswith("caso:"):
        return bool(entrada[5:].strip())
    partes = entrada.split(":")
    if len(partes) == 1:
        return partes[0] in FUENTES
    if len(partes) != 2 or partes[0] not in FUENTES:
        return False
    return partes[1] in UNIDADES or partes[1] in CAPACIDAD_POR_UNIDAD.values()


def _celda_autorizada(celda: dict, ambito: Sequence[str], casos_auth: set[str] | None) -> bool:
    if casos_auth is not None and celda["caso"]["caso_id"] not in casos_auth:
        return False
    for entrada in ambito:
        if entrada.startswith("caso:"):
            if celda["caso"]["caso_id"] == entrada[5:]:
                return True
            continue
        partes = entrada.split(":")
        if len(partes) == 1:
            if celda["fuente"] == partes[0]:
                return True
        elif (len(partes) == 2 and celda["fuente"] == partes[0]
              and partes[1] in (celda["unidad"], celda["capacidad"])):
            return True
    return False


def validar_autorizacion(datos: Any, *, sha_corpus: str, fuentes: Iterable[str],
                         ahora: datetime | None = None,
                         plan: Sequence[dict] | None = None) -> list[str]:
    """Errores de autorización; lista vacía = válida. Tipos estrictos y ámbito por celda."""
    errores: list[str] = []
    if not isinstance(datos, dict):
        return ["autorizacion_no_es_objeto"]
    claves = set(datos)
    if claves - CLAVES_AUTORIZACION:
        errores.append("claves_no_permitidas")
    for clave in ("id", "ambito", "presupuesto_peticiones", "desde", "hasta", "concede",
                  "condiciones", "sha_corpus"):
        if clave not in datos:
            errores.append(f"falta_{clave}")
    if errores:
        return errores
    if not isinstance(datos["id"], str) or not datos["id"].strip():
        errores.append("id_invalido")
    if datos.get("sha_corpus") != sha_corpus:
        errores.append("sha_corpus_distinto")
    if not isinstance(datos["concede"], str) or not datos["concede"].strip():
        errores.append("concede_invalido")
    if not isinstance(datos["condiciones"], str):
        errores.append("condiciones_invalidas")
    desde = _parsear_fecha(datos.get("desde"))
    hasta = _parsear_fecha(datos.get("hasta"))
    if desde is None or hasta is None:
        errores.append("fechas_invalidas")
    elif desde > hasta:
        errores.append("fechas_invertidas")
    else:
        momento = ahora or ahora_utc()
        if not (desde <= momento <= hasta):
            errores.append("fuera_de_vigencia")
    presupuesto = datos.get("presupuesto_peticiones")
    if type(presupuesto) is not int or presupuesto <= 0:   # bool también se rechaza
        errores.append("presupuesto_invalido")
    if "max_por_fuente" in datos:
        maximo = datos["max_por_fuente"]
        if type(maximo) is not int or maximo <= 0:
            errores.append("max_por_fuente_invalido")
    casos_auth: set[str] | None = None
    if "casos" in datos:
        casos = datos["casos"]
        if (not isinstance(casos, list) or not casos
                or any(not isinstance(c, str) or not c.strip() for c in casos)):
            errores.append("casos_invalidos")
        else:
            casos_auth = set(casos)
    ambito = datos["ambito"]
    if not isinstance(ambito, list) or not ambito or not all(_ambito_valido(a) for a in ambito):
        errores.append("ambito_invalido")
        ambito = []
    if not errores and plan:
        if any(not _celda_autorizada(celda, ambito, casos_auth) for celda in plan):
            errores.append("fuera_de_ambito")
    elif not errores and not plan:
        permitidas = {str(a).split(":")[0] for a in ambito}
        if any(f not in permitidas for f in fuentes):
            errores.append("fuera_de_ambito")
    # Sin plan no se puede comprobar el ámbito por caso/capacidad; lo hará `plan` en PR-3.
    return errores


def cargar_autorizacion(path: Path | None, *, sha_corpus: str, fuentes: Iterable[str],
                        ahora: datetime | None = None,
                        plan: Sequence[dict] | None = None) -> tuple[dict | None, list[str]]:
    if path is None:
        return None, ["sin_fichero_autorizacion"]
    try:
        datos = _leer_json(path)
    except ErrorBanco:
        return None, ["autorizacion_ilegible"]
    errores = validar_autorizacion(datos, sha_corpus=sha_corpus, fuentes=fuentes,
                                   ahora=ahora, plan=plan)
    return (datos if not errores else None), errores


def plan_real(corpus: dict, *, fuentes: Sequence[str], unidades: Sequence[str],
              casos: Sequence[str] | None = None) -> list[dict]:
    """Celdas del plan real: caso × fuente × unidad, con método o `sin_metodo_autorizado`."""
    unidades = [u for u in unidades if u in UNIDADES]
    seleccion = set(casos) if casos else None
    plan = []
    for caso in corpus["casos"]:
        if seleccion and caso["caso_id"] not in seleccion:
            continue
        for fuente in fuentes:
            for unidad in unidades:
                metodo = METODOS.get(fuente, {}).get(unidad)
                plan.append({"caso": caso, "fuente": fuente, "unidad": unidad,
                             "capacidad": CAPACIDAD_POR_UNIDAD[unidad], "metodo": metodo})
    return plan


def registros_sin_autorizacion(plan: Sequence[dict], corpus: dict,
                                *, sha_ejecutor: str = "no_disponible") -> list[dict]:
    condiciones = {"fecha": _iso(ahora_utc()), "red": "real", "fuentes_encendidas": [],
                   "presupuesto": 0, "parada": "sin_autorizacion"}
    return [
        _registro(
            caso=celda["caso"], corpus_version=corpus["version"], fuente=celda["fuente"],
            capacidad=celda["capacidad"], unidad=celda["unidad"], metodo=celda["metodo"],
            estado_tecnico="no_ejecutado", estado_fuente_133=None,
            motivo_no_ejecutado="sin_autorizacion", peticiones=0, reintentos=0,
            resultado_editorial=None, campos_evaluados=[], campos_presentes=[],
            campos_ausentes=[], candidatos=[], modo="real", condiciones=condiciones,
            notas="fail-closed: sin autorización válida no se hace ninguna petición",
            sha_ejecutor=sha_ejecutor,
        )
        for celda in plan
    ]


# ── Clasificación técnica (reutiliza #133/#134) ──────────────────────────────────────────────

def estado_desde_excepcion(exc: BaseException) -> tuple[str, str | None]:
    """Mapea una excepción de #134 a (estado_tecnico, estado_fuente_133)."""
    from zascarr.utils.cortesia import CortesiaEnEspera, FuenteApagada
    from zascarr.utils.peticiones import ErrorDePeticion, ReintentosAgotados

    if isinstance(exc, FuenteApagada):
        return "no_ejecutado", "fuente_apagada"
    if isinstance(exc, CortesiaEnEspera):
        return "limite_de_cortesia", "limite_de_cortesia"
    if isinstance(exc, ReintentosAgotados):
        if getattr(exc, "ultimo_codigo", None) == 429:
            return "limite_de_cortesia", "limite_de_cortesia"
        return "fallo_transitorio", "fallo_transitorio"
    if isinstance(exc, ErrorDePeticion):
        return "fallo_transitorio", "fallo_transitorio"
    return "fallo_transitorio", "fallo_transitorio"


class _SinDatos(Exception):  # noqa: N818 — marcador interno, no se publica
    """El caso no trae el dato que el método autorizado necesita (p. ej. volume_id)."""


async def _invocar(cliente: Any, fuente: str, metodo: str | None, caso: dict) -> list[Any]:
    """Invoca el método autorizado sobre un cliente ya construido (real o inyectado)."""
    if metodo is None:
        raise _SinDatos()
    etiqueta = caso["etiqueta_editorial"]
    campos = etiqueta.get("campos") or {}
    if fuente == "comic_vine":
        if metodo.endswith("search_series"):
            return list(await cliente.search_series(caso["consulta"]))
        if metodo.endswith("find_issue"):
            volume_id = campos.get("volume_id")
            numero = etiqueta.get("numero")
            if not volume_id or not numero:
                raise _SinDatos()
            return list(await cliente.find_issue(int(volume_id), str(numero)))
        if metodo.endswith("get_issue_detail"):
            issue_id = campos.get("issue_id")
            if not issue_id:
                raise _SinDatos()
            return [await cliente.get_issue_detail(int(issue_id))]
    if fuente == "anilist":
        return list(await cliente.search_manga(caso["consulta"]))
    if fuente in ("tebeosfera", "gcd"):
        return list(await cliente.search_series(caso["consulta"]))
    raise _SinDatos()


async def _llamar_cliente(fuente: str, metodo: str | None, caso: dict, *,
                          cliente_factory=None) -> list[Any]:
    """Llamada real a un método autorizado. Solo se usa en `--real` con autorización válida.

    `cliente_factory(fuente)` permite inyectar un doble en las pruebas (cero red). Sin factory
    se usan los clientes reales, que ya pasan por `pedir_con_cortesia` (#134); aquí no se hace
    ninguna petición directa.
    """
    if metodo is None:
        raise _SinDatos()
    if cliente_factory is not None:
        cliente = cliente_factory(fuente)
        if hasattr(cliente, "__aenter__"):
            async with cliente as abierto:
                return await _invocar(abierto, fuente, metodo, caso)
        return await _invocar(cliente, fuente, metodo, caso)
    if fuente == "comic_vine":
        from zascarr.services.comic_vine import ComicVineClient
        async with ComicVineClient() as cliente:
            return await _invocar(cliente, fuente, metodo, caso)
    if fuente == "anilist":
        from zascarr.services.anilist import AniListClient
        async with AniListClient() as cliente:
            return await _invocar(cliente, fuente, metodo, caso)
    if fuente == "tebeosfera":
        from zascarr.services.tebeosfera import TebeosferaClient
        async with TebeosferaClient() as cliente:
            return await _invocar(cliente, fuente, metodo, caso)
    if fuente == "gcd":
        from zascarr.services.gcd import GCDClient
        async with GCDClient() as cliente:
            return await _invocar(cliente, fuente, metodo, caso)
    raise _SinDatos()


def _candidatos_saneados(resultados: Sequence[Any]) -> list[dict]:
    """Solo id y etiqueta propuesta: nunca URL, portada, sinopsis ni credenciales."""
    sanitizados = []
    for rank, resultado in enumerate(resultados, start=1):
        if isinstance(resultado, dict):
            id_externo = resultado.get("id") or resultado.get("external_id") or ""
            etiqueta = resultado.get("name") or resultado.get("title") or ""
        else:
            id_externo = (getattr(resultado, "cv_id", None)
                          or getattr(resultado, "anilist_id", None)
                          or getattr(resultado, "gcd_id", None)
                          or getattr(resultado, "slug", "") or "")
            etiqueta = getattr(resultado, "name", None) or getattr(resultado, "title", "")
        sanitizados.append({"rank": rank, "id_externo": str(id_externo),
                            "etiqueta_propuesta": str(etiqueta)[:120]})
    return sanitizados


def _configuracion_fuente(fuente: str) -> tuple[bool, str | None]:
    """(se_puede_consultar, estado #133 si no). Sin tráfico; lee Ajustes de solo lectura."""
    from zascarr.config import get_settings
    s = get_settings()
    atributo = f"{fuente}_enabled"
    if not getattr(s, atributo, False):
        return False, "fuente_apagada"
    if fuente == "comic_vine" and not getattr(s, "comicvine_api_key", ""):
        return False, "configuracion_incompleta"
    if fuente == "foro" and not getattr(s, "forum_url", ""):
        return False, "configuracion_incompleta"
    return True, None


async def ejecutar_real(
    plan: Sequence[dict], corpus: dict, autorizacion: dict, *,
    max_peticiones: int, max_por_fuente: int, salida: Path,
    corpus_sha: str, fuentes: Sequence[str] | None = None,
    cliente_factory=None, sha_ejecutor: str = "no_disponible",
    ahora: datetime | None = None,
) -> list[dict]:
    """Ejecuta el plan real con la cortesía de #134. No se lanza en tests ni en PR-3 aquí.

    Revalida el permiso contra el corpus (no confía en el diccionario del llamador), aplica
    ámbito/casos/topes y se detiene por presupuesto, cortesía, fuente apagada o 3 fallos
    consecutivos. Las celdas no ejecutadas quedan `no_ejecutado` con su motivo.
    """
    fuentes = list(fuentes or sorted({c["fuente"] for c in plan}))
    errores = validar_autorizacion(autorizacion, sha_corpus=corpus_sha, fuentes=fuentes,
                                   ahora=ahora, plan=plan)
    if errores:
        raise PermissionError("autorizacion_invalida:" + ",".join(errores))
    casos_auth = set(autorizacion.get("casos") or [])
    plan = [c for c in plan
            if _celda_autorizada(c, autorizacion["ambito"], casos_auth or None)]
    # El tope efectivo nunca puede superar el permiso, aunque el llamador pase más.
    max_peticiones = min(max_peticiones, autorizacion["presupuesto_peticiones"])
    max_por_fuente = min(max_por_fuente, autorizacion.get("max_por_fuente", max_por_fuente))

    fuentes_encendidas: list[str] = []
    for fuente in sorted({c["fuente"] for c in plan}):
        disponible, _causa = _configuracion_fuente(fuente)
        if disponible:
            fuentes_encendidas.append(fuente)
    condiciones = {"fecha": _iso(ahora_utc()), "red": "real",
                   "fuentes_encendidas": fuentes_encendidas,
                   "presupuesto": max_peticiones, "parada": "final"}
    filas: list[dict] = []
    peticiones = 0
    por_fuente: Counter[str] = Counter()
    fallos_consecutivos: Counter[str] = Counter()
    parada: str | None = None

    def _no_ejecutado(celda: dict, motivo: str, estado133: str | None = None,
                      notas: str = "", *, cuenta: bool = False) -> None:
        filas.append(_registro(
            caso=celda["caso"], corpus_version=corpus["version"], fuente=celda["fuente"],
            capacidad=celda["capacidad"], unidad=celda["unidad"], metodo=celda["metodo"],
            estado_tecnico="no_ejecutado", estado_fuente_133=estado133,
            motivo_no_ejecutado=motivo, peticiones=0, reintentos=0,
            resultado_editorial=None, campos_evaluados=[], campos_presentes=[],
            campos_ausentes=[], candidatos=[], modo="real", condiciones=condiciones,
            notas=notas, sha_ejecutor=sha_ejecutor))
        if cuenta:
            filas[-1]["autorizacion"] = autorizacion

    for celda in plan:
        caso, fuente = celda["caso"], celda["fuente"]
        if parada is not None:
            motivo = ("presupuesto_agotado" if parada == "presupuesto"
                      else "fuente_apagada" if parada == "fuente_apagada"
                      else "fuera_de_alcance")
            _no_ejecutado(celda, motivo, notas=f"detenido: {parada}", cuenta=True)
            continue
        if peticiones >= max_peticiones or por_fuente[fuente] >= max_por_fuente:
            parada = "presupuesto"
            _no_ejecutado(celda, "presupuesto_agotado", notas="parada por presupuesto",
                          cuenta=True)
            continue
        if celda["metodo"] is None:
            _no_ejecutado(celda, "sin_metodo_autorizado",
                          notas="sin método autorizado; no se prueba", cuenta=True)
            continue
        disponible, causa = _configuracion_fuente(fuente)
        if not disponible:
            if causa == "fuente_apagada":
                parada = "fuente_apagada"
            _no_ejecutado(celda, causa or "fuera_de_alcance", estado133=causa,
                          notas="precomprobación sin tráfico", cuenta=True)
            if parada is None and causa == "configuracion_incompleta":
                parada = "configuracion_incompleta"
            continue
        filas.append(None)  # marcador de orden; se sustituye por la fila real
        peticiones += 1
        por_fuente[fuente] += 1
        try:
            resultados = await _llamar_cliente(fuente, celda["metodo"], caso,
                                               cliente_factory=cliente_factory)
        except _SinDatos:
            peticiones -= 1
            por_fuente[fuente] -= 1
            filas.pop()
            _no_ejecutado(celda, "fuera_de_alcance",
                          notas="al caso le falta el dato que pide el método", cuenta=True)
            continue
        except Exception as exc:  # noqa: BLE001 — se clasifica con #133/#134
            if filas and filas[-1] is None:
                filas.pop()
            estado, estado133 = estado_desde_excepcion(exc)
            if isinstance(exc, _SinDatos):
                peticiones -= 1
                por_fuente[fuente] -= 1
            intentos = getattr(exc, "intentos", 1) if estado in (
                "fallo_transitorio", "limite_de_cortesia") else 1
            if estado == "limite_de_cortesia":
                from zascarr.utils.cortesia import CortesiaEnEspera
                if isinstance(exc, CortesiaEnEspera):
                    # La cortesía no llegó a enviar: coste real 0, no se inventa una petición.
                    intentos = 0
                    peticiones -= 1
                    por_fuente[fuente] -= 1
                if intentos > 1:
                    peticiones += intentos - 1
                    por_fuente[fuente] += intentos - 1
                parada = "limite_de_cortesia"
                filas.append(_registro(
                    caso=caso, corpus_version=corpus["version"], fuente=fuente,
                    capacidad=celda["capacidad"], unidad=celda["unidad"],
                    metodo=celda["metodo"], estado_tecnico="limite_de_cortesia",
                    estado_fuente_133="limite_de_cortesia",
                    motivo_no_ejecutado=None, peticiones=intentos,
                    reintentos=max(0, intentos - 1), resultado_editorial=None,
                    campos_evaluados=[], campos_presentes=[], campos_ausentes=[],
                    candidatos=[], modo="real", condiciones=condiciones,
                    notas="parada por cortesía; no se reenvía", sha_ejecutor=sha_ejecutor))
                filas[-1]["autorizacion"] = autorizacion
                continue
            if intentos > 1:
                peticiones += intentos - 1
                por_fuente[fuente] += intentos - 1
            if estado == "no_ejecutado":
                peticiones -= 1
                por_fuente[fuente] -= 1
                parada = "fuente_apagada"
                _no_ejecutado(celda, "fuente_apagada", estado133=estado133,
                              notas="la fuente se apagó durante la ejecución", cuenta=True)
                continue
            if estado == "fallo_transitorio":
                fallos_consecutivos[fuente] += 1
                if fallos_consecutivos[fuente] >= 3:
                    parada = "fallos_transitorios"
            filas.append(_registro(
                caso=caso, corpus_version=corpus["version"], fuente=fuente,
                capacidad=celda["capacidad"], unidad=celda["unidad"], metodo=celda["metodo"],
                estado_tecnico=estado, estado_fuente_133=estado133,
                motivo_no_ejecutado=None, peticiones=intentos,
                reintentos=max(0, intentos - 1),
                resultado_editorial=None, campos_evaluados=[], campos_presentes=[],
                campos_ausentes=[], candidatos=[], modo="real", condiciones=condiciones,
                notas=f"error clasificado: {type(exc).__name__}", sha_ejecutor=sha_ejecutor))
            filas[-1]["autorizacion"] = autorizacion
            continue
        if filas and filas[-1] is None:
            filas.pop()
        fallos_consecutivos[fuente] = 0
        candidatos = _candidatos_saneados(resultados)
        estado = "ok" if resultados else "sin_resultados"
        filas.append(_registro(
            caso=caso, corpus_version=corpus["version"], fuente=fuente,
            capacidad=celda["capacidad"], unidad=celda["unidad"], metodo=celda["metodo"],
            estado_tecnico=estado, estado_fuente_133=estado,
            motivo_no_ejecutado=None, peticiones=1, reintentos=0,
            resultado_editorial=None, campos_evaluados=[], campos_presentes=[],
            campos_ausentes=[], candidatos=candidatos, modo="real",
            condiciones=condiciones, hash_respuesta=_hash_saneado(candidatos),
            notas="candidatos pendientes de revisión humana", sha_ejecutor=sha_ejecutor))
        filas[-1]["autorizacion"] = autorizacion
    for fila in filas:
        fila["condiciones"] = {**fila["condiciones"], "parada": parada or "final"}
    return filas


# ── Métricas ─────────────────────────────────────────────────────────────────────────────────

def _tasa(numerador: int, denominador: int) -> dict:
    """Tasa con numerador, denominador y porcentaje SOLO si hay base suficiente (§5)."""
    base = {"numerador": numerador, "denominador": denominador}
    if denominador == 0:
        return {**base, "porcentaje": None, "nota": "sin base (denominador 0)"}
    if denominador < UMBRAL_PORCENTAJE:
        return {**base, "porcentaje": None,
                "nota": f"n<{UMBRAL_PORCENTAJE}: se publican cantidades, no porcentajes"}
    return {**base, "porcentaje": round(100.0 * numerador / denominador, 1), "nota": None}


def _es_evaluable(fila: dict, casos: dict[str, dict]) -> bool:
    """Un caso acreditado con respuesta válida entra en el universo editorial.

    `sin_resultados` cuenta aunque no tenga veredicto (ausencia, no `incorrecto`); `ok` solo
    cuenta como evaluable si la revisión humana ya le puso veredicto editorial.
    """
    caso = casos.get(fila["caso_id"], {})
    if not caso.get("identidad_acreditada"):
        return False
    if fila["estado_tecnico"] == "sin_resultados":
        return True
    revision = fila.get("revision") or {}
    return (fila["estado_tecnico"] == "ok"
            and revision.get("veredicto") in RESULTADOS_EDITORIALES)


def calcular_metricas(registros: Sequence[dict], corpus: dict) -> dict:
    """Métricas por fuente × unidad, con denominadores explícitos y sin agregado editorial."""
    casos = casos_por_id(corpus)
    grupos: dict[tuple[str, str], list[dict]] = {}
    for fila in registros:
        grupos.setdefault((fila["fuente"], fila["unidad"]), []).append(fila)
    salida: dict[str, list[dict]] = {}
    campos: dict[tuple[str, str], list[int]] = {}
    for (fuente, unidad), filas in sorted(grupos.items()):
        ejecutados = [f for f in filas if f["estado_tecnico"] != "no_ejecutado"]
        no_ejecutados = [f for f in filas if f["estado_tecnico"] == "no_ejecutado"]
        ok = [f for f in filas if f["estado_tecnico"] == "ok"]
        sin_resultados = [f for f in filas if f["estado_tecnico"] == "sin_resultados"]
        errores = [f for f in filas if f["estado_tecnico"] in
                   ("fallo_transitorio", "limite_de_cortesia")]
        evaluables = [f for f in filas if _es_evaluable(f, casos)]
        coincidencias = [f for f in evaluables
                         if f["resultado_editorial"] == "coincidencia_verificada"]
        ambiguos = [f for f in evaluables if f["resultado_editorial"] == "ambiguo"]
        incorrectos = [f for f in evaluables if f["resultado_editorial"] == "incorrecto"]
        ausencias = [f for f in evaluables if f["estado_tecnico"] == "sin_resultados"]
        no_acreditadas = [f for f in ejecutados
                          if not casos.get(f["caso_id"], {}).get("identidad_acreditada")]
        for f in filas:
            for campo in f.get("campos_evaluados") or []:
                clave = (fuente, campo)
                campos.setdefault(clave, [0, 0])
                campos[clave][0] += 1
                if campo in (f.get("campos_ausentes") or []):
                    campos[clave][1] += 1
        salida[f"{fuente}__{unidad}"] = {
            "fuente": fuente, "unidad": unidad,
            "planificados": sum(1 for f in filas if f.get("metodo")),
            "ejecutados": len(ejecutados),
            "no_ejecutados": len(no_ejecutados),
            "no_ejecutados_por_motivo": dict(Counter(
                f["motivo_no_ejecutado"] for f in no_ejecutados)),
            "respuestas_ok": len(ok),
            "sin_resultados": len(sin_resultados),
            "errores": len(errores),
            "evaluables": len(evaluables),
            "coincidencias_verificadas": len(coincidencias),
            "ambiguos": len(ambiguos),
            "incorrectos": len(incorrectos),
            "ausencias": len(ausencias),
            "no_acreditadas": len(no_acreditadas),
            "campos_faltantes": sum(len(f.get("campos_ausentes") or []) for f in filas),
            "disponibilidad_tecnica": _tasa(len(ok), len(ejecutados)),
            "precision_editorial": _tasa(
                len(coincidencias), len(coincidencias) + len(ambiguos) + len(incorrectos)),
            "cobertura_editorial_verificada": _tasa(
                len(coincidencias),
                len(coincidencias) + len(ambiguos) + len(incorrectos) + len(ausencias)),
            "tasa_ausencia": _tasa(len(ausencias), len(ok)),
        }
    campos_salida = {}
    for (fuente, campo), (evaluados, ausentes) in sorted(campos.items()):
        campos_salida[f"{fuente}__{campo}"] = {
            "fuente": fuente, "campo": campo,
            "campos_evaluados": evaluados, "campos_faltantes": ausentes,
            "tasa_campo": _tasa(evaluados - ausentes, evaluados),
        }
    return {"por_fuente_unidad": salida, "por_campo": campos_salida}


# ── Informe ─────────────────────────────────────────────────────────────────────────────────

def _linea_tasa(tasa: dict) -> str:
    if tasa["porcentaje"] is None:
        return f"{tasa['numerador']}/{tasa['denominador']} (sin porcentaje: {tasa['nota']})"
    return f"{tasa['numerador']}/{tasa['denominador']} ({tasa['porcentaje']} %)"


def banco_estados_esperados() -> tuple[str, ...]:
    """Estados que el arnés en seco debe ejercitar (los de #133 + `no_ejecutado`)."""
    return tuple(sorted(ESTADOS_TECNICOS))


def _estados_cubiertos(registros: Sequence[dict]) -> set[str]:
    """Estados técnicos y estados de fuente #133 presentes (los `no_ejecutado` conservan causa)."""
    cubiertos = {r["estado_tecnico"] for r in registros}
    cubiertos |= {r["estado_fuente_133"] for r in registros if r.get("estado_fuente_133")}
    return cubiertos


def construir_informe(*, registros: Sequence[dict], corpus: dict, corpus_sha: str, modo: str,
                      autorizacion: dict | None, errores_autorizacion: Sequence[str],
                      sha_ejecutor: str) -> dict:
    metricas = calcular_metricas(registros, corpus)
    cobertura = "NOT RUN"
    estados = _estados_cubiertos(registros)
    esperados = set(banco_estados_esperados()) if modo == "seco" else set()
    faltan = sorted(esperados - estados)
    pass_ = [
        f"El corpus {corpus.get('version')} valida contra su esquema: "
        f"{len(corpus['casos'])} casos (borrador).",
        f"Se han cargado {len(registros)} registros del modo {modo}.",
    ]
    if modo == "seco":
        pass_.append(
            "Estados ejercitados por los fixtures: " + ", ".join(sorted(estados)) + ".")
        if estados:
            pass_.append(
                f"Modo seco: {len(registros)} ensayos, cero peticiones y sin construir clientes.")
    fail_ = list(errores_autorizacion)
    if modo == "seco" and faltan:
        fail_.append(f"Fixtures sin ejercitar estos estados: {', '.join(faltan)}.")
    pass_fail = {
        "PASS": pass_,
        "FAIL": fail_,
        "NOT RUN": [
            "Cobertura real: no se ejecuta en esta entrega (PR-3, con permiso separado).",
            "Revisión humana de candidatos: sin verificador designado todavía.",
            "Red real de las fuentes y comportamiento cambiante entre fechas: no medido.",
            "Piloto de 12 casos / 80 peticiones: pendiente de autorización del PO.",
        ],
    }
    meta = {
        "modo": modo,
        "fecha": _iso(ahora_utc()),
        "sha_ejecutor": sha_ejecutor,
        "corpus_version": corpus.get("version"),
        "sha_corpus": corpus_sha,
        "autorizacion": autorizacion,
        "errores_autorizacion": list(errores_autorizacion),
    }
    return {
        "meta": meta,
        "total_registros": len(registros),
        "metricas": metricas,
        "cobertura": cobertura,
        "pass_fail_not_run": pass_fail,
        "registro_jsonl": "registro.jsonl",
    }


def validar_salida(registros: Sequence[dict], informe: dict) -> None:
    """Escanea TODO lo que se va a escribir: registro e informe, no solo corpus/fixtures."""
    contenido = json.dumps({"registro": list(registros), "informe": informe},
                           ensure_ascii=False)
    if _tiene_url_o_secreto(contenido):
        raise ErrorBanco("la salida contiene URL, ruta, email o una clave")
    campos_registro = {
        "ensayo_id", "corpus_version", "caso_id", "fuente", "capacidad", "unidad", "metodo",
        "sha_ejecutor", "modo", "autorizacion", "estado_tecnico", "estado_fuente_133",
        "motivo_no_ejecutado", "peticiones", "reintentos", "resultado_editorial",
        "campos_evaluados", "campos_presentes", "campos_ausentes", "candidatos", "revision",
        "desacuerdo", "condiciones", "hash_respuesta", "notas",
    }
    for fila in registros:
        if set(fila) != campos_registro:
            raise ErrorBanco("el registro tiene campos fuera de la lista blanca")


def escribir_informe(informe: dict, registros: Sequence[dict], salida: Path) -> None:
    validar_salida(registros, informe)
    salida.mkdir(parents=True, exist_ok=True)
    # Append-only: una ejecución añade sus líneas, no reescribe las anteriores.
    with (salida / "registro.jsonl").open("a", encoding="utf-8") as fichero:
        for fila in registros:
            fichero.write(json.dumps(fila, ensure_ascii=False) + "\n")
    (salida / "informe.json").write_text(
        json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lineas = [
        "# Informe del banco de cobertura española (#135) — preparación",
        "",
        f"- Modo: **{informe['meta']['modo']}**",
        f"- Fecha: {informe['meta']['fecha']}",
        f"- Corpus: {informe['meta']['corpus_version']} "
        f"(`sha256:{informe['meta']['sha_corpus']}`)",
        f"- Cobertura: **{informe['cobertura']}** (un `--seco` no acredita cobertura)",
        "",
        "## PASS / FAIL / NOT RUN",
        "",
    ]
    for estado in ("PASS", "FAIL", "NOT RUN"):
        lineas.append(f"### {estado}")
        if informe["pass_fail_not_run"][estado]:
            lineas += [f"- {texto}" for texto in informe["pass_fail_not_run"][estado]]
        else:
            lineas.append("- —")
        lineas.append("")
    lineas += ["## Métricas por fuente × unidad (denominadores explícitos)", ""]
    for _clave, datos in informe["metricas"]["por_fuente_unidad"].items():
        lineas += [
            f"### {datos['fuente']} · {datos['unidad']}",
            f"- planificados: {datos['planificados']}; ejecutados: {datos['ejecutados']}; "
            f"no ejecutados: {datos['no_ejecutados']} "
            f"({datos['no_ejecutados_por_motivo']})",
            f"- disponibilidad técnica: {_linea_tasa(datos['disponibilidad_tecnica'])}",
            f"- precisión editorial: {_linea_tasa(datos['precision_editorial'])}",
            f"- cobertura editorial verificada: "
            f"{_linea_tasa(datos['cobertura_editorial_verificada'])}",
            f"- evaluables: {datos['evaluables']}; "
            f"coincidencias: {datos['coincidencias_verificadas']}; "
            f"ambiguos: {datos['ambiguos']}; incorrectos: {datos['incorrectos']}; "
            f"no acreditadas: {datos['no_acreditadas']}",
            f"- ausencias: {_linea_tasa(datos['tasa_ausencia'])}; "
            f"campos faltantes: {datos['campos_faltantes']}",
            "",
        ]
    lineas += ["## Campos (por fuente, denominadores explícitos)", ""]
    for _clave, campo in informe["metricas"]["por_campo"].items():
        lineas.append(
            f"- {campo['fuente']} · {campo['campo']}: evaluados "
            f"{campo['campos_evaluados']}, faltantes {campo['campos_faltantes']}, "
            f"tasa {_linea_tasa(campo['tasa_campo'])}")
    lineas += ["", "## Límites", "",
               "- El corpus es intencional (no aleatorio): no se extrapola a la población.",
               "- Un `--seco` demuestra el arnés, no la cobertura.",
               "- Sin ejecución real + revisión humana no se declara cobertura verificada.",
               ""]
    (salida / "informe.md").write_text("\n".join(lineas), encoding="utf-8")


# ── CLI ─────────────────────────────────────────────────────────────────────────────────────

def _lista(valor: str | None, defecto: Iterable[str]) -> list[str]:
    if not valor:
        return list(defecto)
    return [x.strip() for x in valor.split(",") if x.strip()]


def _manifiesto_de(args: argparse.Namespace) -> Path | None:
    if args.manifiesto:
        return Path(args.manifiesto)
    if Path(args.corpus).resolve() == CORPUS_DEFECTO.resolve():
        return MANIFIESTO_DEFECTO
    return None


def _argumentos(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Banco de cobertura española (#135): arnés en seco y fail-closed real.")
    modo = parser.add_mutually_exclusive_group(required=True)
    modo.add_argument("--seco", action="store_true",
                      help="valida el arnés con fixtures; cobertura NOT RUN")
    modo.add_argument("--real", action="store_true",
                      help="exige autorización; sin ella exit 2 y cero peticiones")
    parser.add_argument("--corpus", default=str(CORPUS_DEFECTO))
    parser.add_argument("--fixtures", default=str(FIXTURES_DEFECTO))
    parser.add_argument("--autorizacion", default=None)
    parser.add_argument("--revision", default=None)
    parser.add_argument("--salida", default=str(SALIDA_DEFECTO))
    parser.add_argument("--fuentes", default=",".join(sorted(FUENTES)))
    parser.add_argument("--unidades", default=",".join(
        ["serie", "edicion", "publicacion", "numero", "formato", "campo"]))
    parser.add_argument("--casos", default=None)
    parser.add_argument("--max-peticiones", type=int, default=80)
    parser.add_argument("--max-por-fuente", type=int, default=20)
    parser.add_argument("--sha-ejecutor", default="no_disponible",
                        help="SHA del árbol ejecutor (explícito, nunca del entorno)")
    parser.add_argument("--manifiesto", default=None,
                        help="manifiesto sha256 del corpus; por defecto, el del corpus v1")
    return parser.parse_args(argv)


def _main_seco(args: argparse.Namespace) -> int:
    try:
        corpus, sha = cargar_corpus(Path(args.corpus), _manifiesto_de(args))
        fixtures = cargar_fixtures(Path(args.fixtures), corpus)
    except ErrorBanco as exc:
        print(f"FAIL  {exc}", file=sys.stderr)
        return 1
    # Cinturón de seguridad: en modo seco no se importan ni construyen clientes de red.
    registros = registros_seco(fixtures, corpus, sha_ejecutor=args.sha_ejecutor)
    informe = construir_informe(
        registros=registros, corpus=corpus, corpus_sha=sha, modo="seco",
        autorizacion=None, errores_autorizacion=[], sha_ejecutor=args.sha_ejecutor)
    try:
        escribir_informe(informe, registros, Path(args.salida))
    except ErrorBanco as exc:
        print(f"FAIL  {exc}", file=sys.stderr)
        return 1
    print(f"PASS  arnés en seco: {len(registros)} ensayos con fixtures saneados")
    print(f"      cobertura: {informe['cobertura']} (no se acredita con sintéticos)")
    print("      informe: informe.md / informe.json / registro.jsonl (en --salida)")
    return 0


def _main_real(args: argparse.Namespace) -> int:
    try:
        corpus, sha = cargar_corpus(Path(args.corpus), _manifiesto_de(args))
    except ErrorBanco as exc:
        print(f"FAIL  {exc}", file=sys.stderr)
        return 1
    fuentes = [f for f in _lista(args.fuentes, FUENTES) if f in FUENTES]
    unidades = [u for u in _lista(args.unidades, UNIDADES) if u in UNIDADES]
    casos = _lista(args.casos, []) or None
    plan = plan_real(corpus, fuentes=fuentes, unidades=unidades, casos=casos)
    autorizacion, errores = cargar_autorizacion(
        Path(args.autorizacion) if args.autorizacion else None,
        sha_corpus=sha, fuentes=fuentes, plan=None)
    if not errores and autorizacion is not None:
        # El ámbito por unidad/capacidad se comprueba contra el plan pedido; los `casos` del
        # permiso filtran el plan (los casos no pedidos no son «fuera de ámbito»).
        auth_sin_casos = {k: v for k, v in autorizacion.items() if k != "casos"}
        errores = validar_autorizacion(auth_sin_casos, sha_corpus=sha, fuentes=fuentes,
                                       plan=plan)
    if errores or autorizacion is None:
        registros = registros_sin_autorizacion(plan, corpus,
                                               sha_ejecutor=args.sha_ejecutor)
        informe = construir_informe(
            registros=registros, corpus=corpus, corpus_sha=sha, modo="real",
            autorizacion=None, errores_autorizacion=errores,
            sha_ejecutor=args.sha_ejecutor)
        try:
            escribir_informe(informe, registros, Path(args.salida))
        except ErrorBanco as exc:
            print(f"FAIL  {exc}", file=sys.stderr)
            return 1
        print("FAIL  sin autorización válida: 0 peticiones; informe con "
              "no_ejecutado: sin_autorizacion", file=sys.stderr)
        return 2
    # Autorización válida: ejecuta el plan autorizado con cortesía de #134.
    casos_auth = set(autorizacion.get("casos") or [])
    plan = [c for c in plan
            if not casos_auth or c["caso"]["caso_id"] in casos_auth]
    presupuesto = min(args.max_peticiones, autorizacion["presupuesto_peticiones"])
    max_fuente = min(args.max_por_fuente,
                     autorizacion.get("max_por_fuente", args.max_por_fuente))
    try:
        registros = asyncio.run(ejecutar_real(
            plan, corpus, autorizacion, max_peticiones=presupuesto,
            max_por_fuente=max_fuente, salida=Path(args.salida), corpus_sha=sha,
            fuentes=fuentes, sha_ejecutor=args.sha_ejecutor))
    except PermissionError as exc:
        print(f"FAIL  revalidación de autorización: {exc}", file=sys.stderr)
        return 2
    informe = construir_informe(
        registros=registros, corpus=corpus, corpus_sha=sha, modo="real",
        autorizacion=autorizacion, errores_autorizacion=[], sha_ejecutor=args.sha_ejecutor)
    try:
        escribir_informe(informe, registros, Path(args.salida))
    except ErrorBanco as exc:
        print(f"FAIL  {exc}", file=sys.stderr)
        return 1
    ejecutadas = sum(1 for r in registros if r["estado_tecnico"] != "no_ejecutado")
    parada = registros[-1]["condiciones"]["parada"] if registros else "final"
    print(f"PASS  ejecución real terminada: {len(registros)} celdas, "
          f"{ejecutadas} con petición, parada={parada}")
    print("      cobertura editorial: NOT RUN hasta la revisión humana")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _argumentos(argv)
    return _main_seco(args) if args.seco else _main_real(args)


if __name__ == "__main__":
    raise SystemExit(main())
