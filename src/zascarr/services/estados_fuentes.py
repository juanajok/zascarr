"""Estados por fuente y capacidad de #133 — **solo stdlib**.

Este módulo existe para que herramientas que no deben cargar clientes de red (el banco de
cobertura, #135) puedan reutilizar el conjunto cerrado de estados sin importar `discovery.py`,
que a su vez importa los cuatro clientes (`httpx`, `lxml`, `sqlalchemy`). `discovery` reexporta
estos nombres: el contrato público no cambia y #133 sigue siendo la única fuente de verdad.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Conjunto CERRADO de estados de una fuente para una capacidad (MIT-M8-US01, #133).
FUENTE_OK = "ok"
FUENTE_SIN_RESULTADOS = "sin_resultados"
FUENTE_FALLO_TRANSITORIO = "fallo_transitorio"
FUENTE_CONFIGURACION_INCOMPLETA = "configuracion_incompleta"
FUENTE_LIMITE_DE_CORTESIA = "limite_de_cortesia"
FUENTE_APAGADA = "fuente_apagada"
ESTADOS_DE_FUENTE = frozenset({
    FUENTE_OK, FUENTE_SIN_RESULTADOS, FUENTE_FALLO_TRANSITORIO,
    FUENTE_CONFIGURACION_INCOMPLETA, FUENTE_LIMITE_DE_CORTESIA, FUENTE_APAGADA,
})

#: Única capacidad VERIFICADA en esta entrega para las cuatro fuentes: **buscar series**.
CAPACIDAD_BUSQUEDA = "busqueda"
#: Capacidad de contrato de BL-FU2 (#465): pedir el detalle de una edición/candidato. No se
#: publica en la UI como «disponible»; describe el resultado del método de detalle.
CAPACIDAD_DETALLE = "detalle_edicion"


@dataclass(frozen=True)
class EstadoFuente:
    """En qué quedó UNA fuente para UNA capacidad.

    `motivo` es texto en español para la persona (nunca un identificador ni una causa inventada);
    `reintentar_en` son segundos y solo va relleno si el contrato los aportó.
    """
    fuente: str
    capacidad: str
    estado: str
    motivo: str | None = None
    reintentar_en: int | None = None
