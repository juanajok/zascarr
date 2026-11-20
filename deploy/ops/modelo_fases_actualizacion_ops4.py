"""Modelo puro de fases de un intento de actualización; no persiste ni ejecuta.

Distingue un fallo sin efectos de un resultado incierto después de avanzar
código, migrar o pedir el arranque. Los terminales no vuelven a un estado
activo. La persistencia durable, el cerrojo y la reconciliación del host no
están implementados aquí; este modelo solo fija transiciones para pruebas y
para el futuro ejecutor. No conectar a la UI ni al auxiliar todavía.
"""
from __future__ import annotations

from enum import StrEnum


class Fase(StrEnum):
    PREPARANDO = "preparando"
    RESERVADA = "reservada"
    COPIANDO = "copiando"
    AVANZANDO = "avanzando"
    CONSTRUYENDO = "construyendo"
    MIGRANDO = "migrando"
    ARRANCANDO = "arrancando"
    VERIFICANDO = "verificando"
    HECHA = "hecha"
    FALLIDA = "fallida"
    INCIERTA = "incierta"


TERMINALES = frozenset({Fase.HECHA, Fase.FALLIDA, Fase.INCIERTA})

#: Éxitos permitidos. Un fallo nunca avanza.
EXITO = {
    Fase.PREPARANDO: Fase.RESERVADA,
    Fase.RESERVADA: Fase.COPIANDO,
    Fase.COPIANDO: Fase.AVANZANDO,
    Fase.AVANZANDO: Fase.CONSTRUYENDO,
    Fase.CONSTRUYENDO: Fase.MIGRANDO,
    Fase.MIGRANDO: Fase.ARRANCANDO,
    Fase.ARRANCANDO: Fase.VERIFICANDO,
    Fase.VERIFICANDO: Fase.HECHA,
}

#: Fases en las que un fallo puede haber dejado efectos parciales.
INCIERTAS_POR_FALLO = frozenset({Fase.AVANZANDO, Fase.MIGRANDO, Fase.ARRANCANDO, Fase.VERIFICANDO})


def siguiente(fase: object, resultado: object) -> Fase | None:
    """Devuelve la fase siguiente o None si la transición no es válida.

    `resultado` es "ok", "fallo" o "incierto". Un fallo antes de migrar se
    declara fallido; después puede ser incierto. Cualquier entrada rara
    devuelve None y el llamador debe detenerse.
    """
    if not isinstance(fase, Fase) or fase in TERMINALES:
        return None
    if resultado == "ok":
        return EXITO[fase]
    if resultado == "fallo":
        return Fase.INCIERTA if fase in INCIERTAS_POR_FALLO else Fase.FALLIDA
    if resultado == "incierto":
        return Fase.INCIERTA
    return None


def es_terminal(fase: object) -> bool:
    """Solo los estados terminales cierran el intento."""
    return isinstance(fase, Fase) and fase in TERMINALES


def puede_reintentar(fase: object) -> bool:
    """Ningún estado de este modelo autoriza reintento; siempre es False."""
    return False
