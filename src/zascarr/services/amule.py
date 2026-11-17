"""Cliente aMule vía amuleweb HTTP."""
import hashlib
import re
from urllib.parse import unquote

import httpx
import structlog

from zascarr.config import get_settings

logger = structlog.get_logger()


def hash_contrasena_amuleweb(password: str) -> str:
    """MD5 que usaba el protocolo antiguo de amuleweb (campo `p`).

    Se conserva para el formato heredado. Ojo: equivale a la contraseña y viaja por HTTP sin
    cifrar, igual que el formulario actual (`pass`), así que amuleweb debe quedarse en loopback o
    en una red de confianza (SECURITY.md). Nunca se escribe en logs. `usedforsecurity=False` deja
    funcionar el hash en builds FIPS. También lo usa la prueba de conexión de Ajustes."""
    return hashlib.md5(password.encode(), usedforsecurity=False).hexdigest()


def _es_pantalla_de_login(html: str) -> bool:
    """¿La respuesta sigue pidiendo la contraseña? (el marcador es estable en amuleweb)."""
    bajo = (html or "").lower()
    return 'name="pass"' in bajo or "enter password" in bajo


class AMuleClient:
    def __init__(self):
        s = get_settings()
        self._base = s.amule_url
        self._password = s.amule_password
        self._cookies: dict[str, str] = {}

    async def login(self) -> bool:
        """Entra en amuleweb. Acepta el formulario actual y el formato antiguo.

        El amuleweb real de la Pi pide `pass` con la contraseña y `submit`; el
        cliente enviaba solo `p` con el MD5 y recibía la pantalla de login, pero
        la daba por válida porque había cookie. Se prueba primero el formulario
        actual y, si sigue pidiendo contraseña, el `p` heredado.
        """
        pw_hash = hash_contrasena_amuleweb(self._password)
        intentos = (
            {"pass": self._password, "submit": "Submit"},
            {"p": pw_hash},
        )
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            ultima = None
            for datos in intentos:
                r = await client.post(f"{self._base}/", data=datos)
                ultima = r
                for name, value in r.cookies.items():
                    self._cookies[name] = value
                set_cookie = r.headers.get("set-cookie", "")
                if set_cookie and not self._cookies:
                    self._cookies["ses"] = set_cookie.split(";")[0].split("=", 1)[-1]
                if not _es_pantalla_de_login(r.text):
                    self._logged_in = bool(self._cookies)
                    if self._logged_in:
                        logger.info("amule.login_ok")
                    return self._logged_in
            self._logged_in = False
            logger.warning("amule.login_fallido", status=ultima.status_code if ultima else None)
            return False

    async def _get(self, path: str) -> str:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True,
                                     cookies=self._cookies) as client:
            r = await client.get(f"{self._base}{path}")
            r.raise_for_status()
            return r.text

    async def _post(self, path: str, datos: dict[str, str]) -> str:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True,
                                     cookies=self._cookies) as client:
            r = await client.post(f"{self._base}{path}", data=datos)
            r.raise_for_status()
            return r.text

    @staticmethod
    def _datos_de_enlace(link: str) -> dict[str, str]:
        """Campos del formulario real del footer de amuleweb.

        El panel tiene una página `footer.php` con
        `<form name="formlink" method="post" action="footer.php">
        <input name="ed2klink">…<input type="submit" value="Download link">`.
        El cliente usaba `GET /amuleweb/?ed2k=…`, que no existe: amuleweb
        responde 200 con una página de error de ~458 bytes y el enlace se
        perdía silenciosamente (bug real 2026-11-16: «le doy descargar y en
        aMule no aparece nada»). El enlace del foro llega URL-encoded
        (`DC%20K.O.…`): se desescapa, que es lo que haría el navegador.
        """
        return {
            "ed2klink": unquote(link),
            "selectcat": "all",
            "Submit": "Download link",
        }

    async def add_ed2k_link(self, link: str) -> bool:
        if not link.startswith("ed2k://"):
            return False
        try:
            await self._post("/footer.php", self._datos_de_enlace(link))
            logger.info("amule.ed2k_added", link=link[:80])
            return True
        except Exception:
            logger.exception("amule.add_failed")
            return False

    async def list_completed_comics(self) -> list[dict]:
        try:
            html = await self._get("/amuleweb/")
            pattern = re.compile(r'(\d+\.?\d*)\s*%', re.DOTALL)
            results = []
            for m in pattern.finditer(html):
                pct = float(m.group(1))
                if pct >= 100.0:
                    results.append({"percent_done": pct, "completed": True})
            return results
        except Exception:
            return []

    async def get_status(self) -> dict:
        try:
            html = await self._get("/amuleweb/")
            return {"reachable": True, "connected": "connected" in html.lower()}
        except Exception:
            return {"reachable": False, "connected": False}
