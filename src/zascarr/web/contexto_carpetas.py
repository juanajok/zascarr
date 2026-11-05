"""
Contexto de la lista de «Pendientes por carpeta» que viaja por el asistente (BL-FILT1, #397).

La lista de carpetas tiene siete valores de contexto: `nombre`, `estado`,
`por_confirmar`, `en_conflicto`, `serie`, `limite` y `desplazamiento` (spec §6.1).
Viajan **siempre en la URL** (GET) y en campos ocultos de los formularios POST del
asistente; **nunca** en servidor (sin sesión ni cookie: una recarga lo conserva y un
reinicio no depende de nada).

`limite` solo viaja si no es el de por defecto (50) y `desplazamiento` solo si no es 0,
igual que la URL canónica de la lista (§3.3). El contexto se reconstruye con los valores
del formulario/consulta, **nunca** con una URL arbitraria de retorno: por eso no existe
`volver`, `next` ni `return_to` (spec §6.1).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from urllib.parse import urlencode

from fastapi import Request

#: Valores admitidos del selector de estado; "" y "todas" son «sin restricción».
ESTADOS_DE_CARPETA = ("", "todas", "sin_serie", "serie_sugerida", "mixto")

#: Orden del contexto en las URLs del asistente (spec §6.1).
_ORDEN = ("nombre", "estado", "por_confirmar", "en_conflicto", "serie", "limite", "desplazamiento")

LIMITE_POR_DEFECTO = "50"


def _texto(valor: str | None, *, maximo: int = 200) -> str:
    """Recorta la entrada que solo se reenvía: sin controles, sin espacios en los bordes y
    con el mismo tope que valida la lista. No avisa (la lista es quien lo explica)."""
    limpio = "".join(c for c in (valor or "") if ord(c) >= 32 and ord(c) != 127)
    return limpio.strip().lstrip("\ufeff")[:maximo]


def _numero(valor: str | None, *, por_defecto: str) -> str:
    """Un entero en texto, o "" si es el valor por defecto o no es un entero."""
    limpio = (valor or "").strip()
    if not limpio:
        return ""
    try:
        entero = int(limpio)
    except ValueError:
        return ""
    if entero < 0:
        return ""
    texto = str(entero)
    return "" if texto == por_defecto else texto


@dataclass(frozen=True)
class ContextoCarpetas:
    """Contexto de la lista, listo para reenviar por enlaces y formularios."""

    nombre: str = ""
    estado: str = ""
    por_confirmar: str = ""
    en_conflicto: str = ""
    serie: str = ""
    limite: str = ""
    desplazamiento: str = ""

    @classmethod
    def desde(cls, request: Request) -> ContextoCarpetas:
        """Lee el contexto de la query de la petición (GET o POST con la query en el
        `action`). Un valor inválido se descarta aquí; la lista lo volverá a validar y
        avisará."""
        consulta = request.query_params
        estado = _texto(consulta.get("estado"), maximo=40)
        if estado not in ESTADOS_DE_CARPETA or estado == "todas":
            estado = ""
        return cls(
            nombre=_texto(consulta.get("nombre")),
            estado=estado,
            por_confirmar="1" if consulta.get("por_confirmar") == "1" else "",
            en_conflicto="1" if consulta.get("en_conflicto") == "1" else "",
            serie=_texto(consulta.get("serie"), maximo=64),
            limite=_numero(consulta.get("limite"), por_defecto=LIMITE_POR_DEFECTO),
            desplazamiento=_numero(consulta.get("desplazamiento"), por_defecto="0"),
        )

    @property
    def activo(self) -> bool:
        return bool(self.nombre or self.estado or self.por_confirmar or self.en_conflicto)

    def _valores(self) -> list[tuple[str, str]]:
        return [(clave, getattr(self, clave)) for clave in _ORDEN if getattr(self, clave)]

    @property
    def query(self) -> str:
        """Sufijo `&clave=valor…` para pegar detrás de un enlace o un `action`; "" si no hay
        contexto. Jinja lo escapa como `&amp;` al pintarlo en un `href`/`action`."""
        valores = self._valores()
        return ("&" + urlencode(valores)) if valores else ""

    @property
    def campos(self) -> list[tuple[str, str]]:
        """Campos ocultos para los formularios POST del asistente."""
        return self._valores()

    def con(self, **cambios: str) -> ContextoCarpetas:
        """Copia con algún valor cambiado (p. ej. la serie al preparar su vinculación)."""
        return replace(self, **cambios)

    def url(self, base: str) -> str:
        """Pega el contexto a una URL que ya puede traer query (`?` o `&`, según el caso)."""
        sufijo = self.query
        if not sufijo:
            return base
        separador = "&" if "?" in base else "?"
        return f"{base}{separador}{sufijo[1:]}"
