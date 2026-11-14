"""Diagnóstico del foro IPB (SCR4): charset, login y una búsqueda, sin mostrar credenciales.

Se ejecuta **dentro del contenedor** (lee `get_settings()`, es decir, el `.env` inyectado):

    docker compose exec zascarr python scripts/diagnostico_foro.py
    docker compose exec zascarr python scripts/diagnostico_foro.py --consulta "Año Uno"
    # opcional, añade un GET al primer tema:
    docker compose exec zascarr python scripts/diagnostico_foro.py --leer-tema

Reglas:
- Máximo **3 peticiones** (4 con `--leer-tema`): GET de entrada, POST de login y búsqueda;
  `--leer-tema` lee después el primer tema. La pausa entre pasos es ≥3 s.
- **Nunca** imprime contraseña, usuario completo, cookies, `s=<sesión>`, títulos ni enlaces:
  solo el estado, el charset detectado, el número de resultados y el tipo de muestra.
- Códigos de salida: 0 correcto, 2 sin configurar, 3 error de red, 4 flood con segundos,
  5 login no confirmado. Siempre con una explicación en español de qué revisar.
"""
from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable

from zascarr.config import get_settings
from zascarr.services.forum_scraper import ForumFloodControl, ForumScraper
from zascarr.utils.peticiones import ErrorDePeticion

#: Campos que deben estar puestos para diagnosticar (solo se nombran, nunca su valor).
_CAMPOS_NECESARIOS = (
    ("forum_url", "FORUM_URL"),
    ("forum_username", "FORUM_USERNAME"),
    ("forum_password", "FORUM_PASSWORD"),
)
CONSULTA_POR_DEFECTO = "Año Uno"
PAUSA_ENTRE_PASOS_S = 3.0
#: Margen que se recomienda esperar tras un flood (el foro pide 20–60 s).
_MARGEN_TRAS_FLOOD_S = 5


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diagnóstico de solo lectura del foro IPB configurado (SCR4).")
    parser.add_argument(
        "--consulta", default=CONSULTA_POR_DEFECTO,
        help=f"Texto de la búsqueda de prueba (por defecto: «{CONSULTA_POR_DEFECTO}»).")
    parser.add_argument(
        "--leer-tema", action="store_true",
        help="Lee además el primer tema encontrado (1 GET más, sin mostrar sus enlaces).")
    return parser


def _faltan(ajustes) -> list[str]:
    """Nombres de variables que faltan o están vacías (sin valores), y si está desactivado."""
    faltan = [nombre for campo, nombre in _CAMPOS_NECESARIOS
              if not str(getattr(ajustes, campo, "") or "").strip()]
    if not bool(getattr(ajustes, "forum_enabled", False)):
        faltan.append("FORUM_ENABLED=true")
    return faltan


def _charset_legible(charset: str | None) -> str:
    return charset if charset else "(ausente)"


async def _diagnostico(ajustes, *, consulta: str, leer_tema: bool, fabrica,
                       salida: Callable[[str], None],
                       dormir=asyncio.sleep) -> int:
    """Los tres pasos del diagnóstico. `fabrica` inyectable para las pruebas sin red."""
    url = str(ajustes.forum_url)
    http = url.startswith("http://")
    salida("ZascArr — diagnóstico del foro (SCR4)")
    aviso_tls = "  [HTTP SIN TLS: las credenciales viajan sin cifrar]" if http else ""
    salida(f"Foro: {url}{aviso_tls}")
    scraper = fabrica(ajustes)
    paso = 1
    try:
        # [1]-[2] Login: GET de entrada (charset y formulario) + POST en ese charset.
        confirmado = await scraper.login(ajustes.forum_username, ajustes.forum_password)
        cabecera, meta, usado = scraper.charset_entrada or (None, None, "cp1252")
        salida(f"[1] Entrada: HTTP {scraper.estado_entrada} | charset cabecera: "
               f"{_charset_legible(cabecera)} | charset meta: {_charset_legible(meta)} | "
               f"usado: {usado}")
        if not confirmado:
            salida("[2] Login: NO confirmado (no llegó cookie de miembro) | flood: no")
            salida("Conclusión: revisa FORUM_USERNAME/FORUM_PASSWORD y que la cuenta pueda "
                   "entrar en el foro. No se ha buscado nada.")
            return 5
        salida(f"[2] Login: OK (cookies recibidas: {scraper.cookies_recibidas}; no se imprimen) "
               "| flood: no")
        paso = 3
        await dormir(PAUSA_ENTRE_PASOS_S)
        resultados = await scraper.use_ipb_search(consulta, abrir_temas=False)
        muestra = "tema (sin título)" if resultados else "—"
        salida(f"[3] Búsqueda «{consulta}»: HTTP 200 | flood: no | "
               f"resultados: {len(resultados)} | muestra: {muestra}")
        if leer_tema and resultados:
            await dormir(PAUSA_ENTRE_PASOS_S)
            tema = await scraper.leer_tema(resultados[0].topic_url)
            salida(f"[4] Tema: ed2k {'sí' if tema.ed2k_links else 'no'} | "
                   f"magnet {'sí' if tema.magnet_links else 'no'}")
        salida(f"Conclusión: charset OK; sin flood; {len(resultados)} resultados. "
               "Pega estas líneas al Lead (no pegues el .env).")
        return 0
    except ForumFloodControl as exc:
        segundos = int(round(exc.segundos))
        if scraper.charset_entrada is not None:
            cabecera, meta, usado = scraper.charset_entrada
            salida(f"[1] Entrada: HTTP {scraper.estado_entrada} | charset cabecera: "
                   f"{_charset_legible(cabecera)} | charset meta: {_charset_legible(meta)} | "
                   f"usado: {usado}")
        salida(f"[{paso}] Flood: SÍ (~{segundos} s). El foro ha pedido esperar; "
               f"reintenta en {segundos + _MARGEN_TRAS_FLOOD_S} s y no repitas la búsqueda.")
        return 4
    except (ErrorDePeticion, OSError) as exc:
        salida(f"Error de red en el paso [{paso}]: no se pudo consultar el foro. "
               "Revisa FORUM_URL, que la Pi llegue al foro y vuelve a intentarlo.")
        salida("Detalle técnico: " + type(exc).__name__)
        return 3


def main(argv: list[str] | None = None, *, ajustes=None,
         fabrica=None, salida: Callable[[str], None] = print,
         dormir=asyncio.sleep) -> int:
    args = _parser().parse_args(argv)
    ajustes = ajustes if ajustes is not None else get_settings()
    faltan = _faltan(ajustes)
    if faltan:
        salida("ZascArr — diagnóstico del foro (SCR4)")
        salida("Faltan datos para diagnosticar: " + ", ".join(faltan) + ".")
        salida("Configura el foro en Ajustes › Descargas › Foro (o en el .env) y activa la "
               "integración. No se ha hecho ninguna petición.")
        return 2
    fabrica = fabrica or (lambda s: ForumScraper(base_url=s.forum_url))
    return asyncio.run(_diagnostico(ajustes, consulta=args.consulta,
                                    leer_tema=args.leer_tema, fabrica=fabrica,
                                    salida=salida, dormir=dormir))


if __name__ == "__main__":
    raise SystemExit(main())
