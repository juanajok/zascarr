"""
D8 — política de búsqueda por serie: qué números quiere y qué se retira.

Fuera del orquestador a propósito. La ficha de serie necesita el **mismo**
predicado que genera, y no debe instanciar un `Orchestrator` (con sus clientes
de Prowlarr/Transmission/aMule) solo para preguntar. Aquí vive el predicado
—`querer_de_serie`— y la retirada; el orquestador pone el ciclo: lote,
generación por rondas y orden.

La generación **y** la retirada consumen el mismo predicado («números que esta
política quiere ahora»): se materializa lo que el predicado pide y no existe, y
se retira lo de origen `politica` que el predicado ya no pide. Con una sola
fuente de verdad no pueden divergir ni dejar items huérfanos: cualquier motivo
para dejar de querer un número (cambió la política, llegó el fichero, apareció
un item manual de serie) entra por el mismo sitio.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import (
    Issue,
    Series,
    Wishlist,
    WishlistOrigin,
    WishlistPolicy,
    WishlistStatus,
)
from zascarr.services.series import huecos_de_serie, numero_de_grapa

#: D8: `futuros` está reservado en el tipo pero no sabe calcularse todavía. No
#: es un fallo: se declara (D9) en vez de inventar una lista de números.
MOTIVO_POLITICA_FUTUROS = (
    "La política «futuros» todavía no se puede aplicar: haría falta que la fuente "
    "publique los números que aún no han salido"
)
#: D8: un item manual a nivel de serie pide la serie genérica. Generar además
#: cada número la buscaría dos veces, así que el predicado no quiere ninguno
#: mientras ese item siga vivo. Importa el caso en que el item manual aparece
#: DESPUÉS: los generados pendientes se retiran igual que si cambiara la
#: política, para no acabar con las dos búsquedas a la vez.
MOTIVO_SERIE_EN_CURSO = (
    "Ya hay un item de esta serie en curso: no se generan números para no buscarla dos veces"
)

#: D8: un item en estos estados ya no cuenta como "vivo" al decidir si hay un
#: item manual de serie en curso o un número ya ocupado a mano. FAILED sí
#: cuenta: sigue en la lista y se reintenta tras el cooldown.
ESTADOS_TERMINADOS = (WishlistStatus.IMPORTED, WishlistStatus.RETIRADO)

#: D8: lo ÚNICO que la generación puede reactivar.
#:
#: - `RETIRADO`: volver a querer un número que se dejó de buscar.
#: - `IMPORTED`: el fichero del número desapareció del disco, así que vuelve a
#:   ser un hueco y hay que pedirlo otra vez.
#:
#: Todo lo demás se deja **en paz**, y en particular:
#: - `FAILED` ya lo reintenta `process_wishlist` por su cuenta tras el cooldown.
#:   Reiniciarlo cada ciclo borraría su `last_error` (el motivo de D9 desaparece
#:   justo cuando el coleccionista lo necesita), alternaría el estado entre
#:   `FAILED` y `WANTED`, y gastaría el lote del ciclo en items que ya existen.
#: - `DOWNLOADED` tiene la descarga terminada y está esperando al importador:
#:   reiniciarlo volvería a buscar un número que ya viene de camino.
ESTADOS_REACTIVABLES = (WishlistStatus.RETIRADO, WishlistStatus.IMPORTED)


@dataclass(frozen=True)
class Querer:
    """D8: números que la política de UNA serie quiere **ahora**. Es el único
    predicado de la feature — lo consumen la generación, la retirada y la ficha
    de serie.

    `computable=False` significa "no hay con qué calcularlo" (misma semántica
    que `Huecos`), nunca "no falta nada". `motivo` es el texto en español que
    la UI enseña cuando no hay números que generar.
    """
    numeros: frozenset[int]
    computable: bool
    motivo: str | None = None


async def querer_de_serie(db: AsyncSession, series: Series) -> Querer:
    """«Números que la política de ESTA serie quiere ahora» — el predicado único
    de D8.

    Falla cerrado y declara: si no se puede calcular, `numeros` va vacío y
    `motivo` lo dice, en vez de inventar una lista (misma regla que
    `huecos_de_serie` en #13).
    """
    # `None` solo puede aparecer en un objeto aún sin pasar por la BD (la
    # columna es NOT NULL con `default`/`server_default`). Se trata como el
    # valor por defecto para que el predicado sea total.
    politica = series.wishlist_policy or WishlistPolicy.NONE
    if politica == WishlistPolicy.NONE:
        return Querer(frozenset(), True)
    if politica == WishlistPolicy.FUTURE:
        return Querer(frozenset(), False, MOTIVO_POLITICA_FUTUROS)

    # Items manuales de esta serie que siguen vivos (un FAILED sigue contando:
    # está en la lista y se reintenta tras el cooldown).
    manuales = (await db.execute(
        select(Wishlist.issue_id, Wishlist.numero)
        .where(Wishlist.series_id == series.id)
        .where(Wishlist.origen == WishlistOrigin.MANUAL)
        .where(Wishlist.status.not_in(ESTADOS_TERMINADOS))
    )).all()

    # Un item manual a NIVEL DE SERIE pide la serie genérica: generar además
    # cada número la buscaría dos veces. Ojo al orden temporal — da igual que
    # el item manual sea anterior o posterior a los generados: el predicado es
    # declarativo y la retirada usa este mismo resultado.
    if any(issue_id is None and numero is None for issue_id, numero in manuales):
        return Querer(frozenset(), True, MOTIVO_SERIE_EN_CURSO)

    huecos = await huecos_de_serie(db, series)
    if not huecos.computable:
        return Querer(frozenset(), False, huecos.motivo)

    numeros = (frozenset(range(1, series.total_issues + 1))
               if politica == WishlistPolicy.ALL else frozenset(huecos.faltantes))

    # Un item manual de un NÚMERO concreto ocupa ese número: generarlo también
    # sería la misma duplicación. El índice único parcial no cubre los manuales
    # (a propósito), así que la base no lo impide — hay que excluirlo aquí.
    ocupados = {numero for _, numero in manuales if numero is not None}
    ids_issue = [issue_id for issue_id, _ in manuales if issue_id is not None]
    if ids_issue:
        for numero_issue, formato in (await db.execute(
                select(Issue.issue_number, Issue.format)
                .where(Issue.id.in_(ids_issue)))).all():
            if (n := numero_de_grapa(numero_issue, formato)) is not None:
                ocupados.add(n)
    return Querer(numeros - ocupados, True)


def stmt_retirada(series_id, querer: Querer):
    """El `UPDATE` atómico que retira lo de política que ya no se quiere.

    Separado para poder fijar en un test el `WHERE` exacto: **solo**
    `WANTED`/`FAILED` (lo que no ha empezado) y **solo** `origen='politica'`
    (lo manual no se toca nunca).

    Un item `SEARCHING`/`DOWNLOADING` queda fuera a propósito: hay una búsqueda
    en vuelo o una descarga en marcha y marcarlo `retirado` sería mentir (D9)
    sobre lo que está pasando.
    """
    stmt = (
        update(Wishlist)
        .where(Wishlist.series_id == series_id)
        .where(Wishlist.origen == WishlistOrigin.POLICY)
        .where(Wishlist.status.in_([WishlistStatus.WANTED, WishlistStatus.FAILED]))
        .values(status=WishlistStatus.RETIRADO, last_error=None)
    )
    if querer.numeros:
        # Sin números que quiera, se retira todo lo pendiente de esa serie. Se
        # evita `NOT IN ()` para no depender del renderizado de un IN vacío.
        stmt = stmt.where(or_(
            Wishlist.numero.is_(None),
            Wishlist.numero.not_in(sorted(querer.numeros)),
        ))
    return stmt


async def retirar_de_serie(db: AsyncSession, series: Series, querer: Querer) -> int:
    """Aplica la retirada a UNA serie y devuelve cuántos items retiró.

    Lo usa el ciclo completo (`Orchestrator.sync_policy_items`) y también el
    guardado de la política en la UI: cuando el coleccionista pide parar, la
    retirada no puede esperar al siguiente ciclo. La generación sí espera.
    """
    resultado = await db.execute(stmt_retirada(series.id, querer))
    return resultado.rowcount or 0
