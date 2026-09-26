"""
RuntimeSettingsService — D11: ajustes de integraciones (Comic Vine,
Prowlarr, Transmission, aMule) editables desde /ui/ajustes, sin editar
`.env` a mano ni reiniciar el contenedor.

Diseño (mínimo impacto a propósito): `config.py`/`.env` siguen siendo la
ÚNICA declaración de campos, tipos y valores por defecto (CLAUDE.md §2)
— esto NO es una segunda fuente de verdad paralela. Lo que añade es un
override en caliente: una fila única en Postgres (`RuntimeSetting`,
JSONB) que se aplica MUTANDO el objeto `Settings` ya cacheado por
`@lru_cache get_settings()`. Como `get_settings()` siempre devuelve la
MISMA instancia y la app corre con `--workers 1` (un solo proceso,
docker-compose.yml), mutar sus atributos es visible al instante para
todo el código que ya existe (`ComicVineClient`, `ProwlarrClient`,
`TransmissionClient`, `AMuleClient`, `Orchestrator`, `DiscoveryService`)
sin tocar una sola línea de esos ficheros.

Solo se pueden sobrescribir los campos de `OVERRIDABLE_FIELDS` — nunca
cualquier atributo de Settings a través de la UI (mismo principio que
M1: nada de escritura sin lista blanca explícita).
"""
from __future__ import annotations

import secrets
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.models import RuntimeSetting

# Campos que la UI de ajustes puede tocar, agrupados por integración
# (mismo agrupado que se usa para el formulario). Todo lo demás de
# Settings (db_pool_size, log_level, scan_interval_minutes...) queda
# fuera a propósito: esta pantalla es "conectar servicios", no un editor
# genérico de configuración.
OVERRIDABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "comic_vine": ("comicvine_api_key",),
    "prowlarr": ("prowlarr_url", "prowlarr_api_key", "prowlarr_enabled"),
    "transmission": (
        "transmission_url", "transmission_username",
        "transmission_password", "transmission_enabled",
    ),
    "amule": ("amule_url", "amule_password", "amule_enabled"),
    # A6: auth_password_hash nunca llega aquí en claro — web/ajustes.py lo
    # calcula (services/auth.py::hash_password) ANTES de llamar a save().
    "seguridad": ("auth_mode", "auth_username", "auth_password_hash", "base_url"),
}
# Nunca se devuelven en claro tras guardarse (D11): la UI los muestra
# como "configurado"/"no configurado", nunca con el valor real.
SECRET_FIELDS = {
    "comicvine_api_key", "prowlarr_api_key", "transmission_password",
    "amule_password", "auth_password_hash",
}
# secret_key (A6) firma la cookie de sesión — nunca aparece en el
# formulario de /ui/ajustes (no está en ningún grupo de OVERRIDABLE_
# FIELDS de arriba), pero SÍ debe pasar por apply_overrides() como los
# demás, así que se añade a la lista blanca por separado.
_CAMPOS_INTERNOS = {"secret_key"}
_ALL_FIELDS = (
    {campo for campos in OVERRIDABLE_FIELDS.values() for campo in campos} | _CAMPOS_INTERNOS
)

_SETTINGS_ROW_ID = 1


class RuntimeSettingsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _row(self) -> RuntimeSetting:
        row = (await self.db.execute(
            select(RuntimeSetting).where(RuntimeSetting.id == _SETTINGS_ROW_ID)
        )).scalar_one_or_none()
        if row is None:
            # No debería pasar (la migración 0011 siembra la fila), pero
            # una instalación que restauró un backup de antes de esa
            # migración no debe romperse por esto.
            row = RuntimeSetting(id=_SETTINGS_ROW_ID, values={})
            self.db.add(row)
            await self.db.flush()
        return row

    async def get_overrides(self) -> dict[str, Any]:
        row = await self._row()
        return dict(row.values or {})

    async def save(self, updates: dict[str, Any]) -> None:
        """Guarda solo claves conocidas y las aplica AL INSTANTE. Un
        campo de contraseña/clave enviado vacío significa "no cambiar"
        — nunca pisa un secreto ya guardado con una cadena vacía (así es
        como la UI puede mostrar los campos de secreto siempre en
        blanco sin arriesgarse a borrarlos al guardar el resto)."""
        row = await self._row()
        values = dict(row.values or {})
        for key, value in updates.items():
            if key not in _ALL_FIELDS:
                raise ValueError(f"Ajuste desconocido: {key}")
            if key in SECRET_FIELDS and value == "":
                continue
            values[key] = value
        row.values = values
        await self.db.flush()
        apply_overrides(values)

    # ── Marcadores internos (B11 y similares) ───────────────────────────
    # Misma fila JSONB, pero NUNCA pasan por `save()` ni su lista blanca:
    # son estado interno de una sola vez ("¿ya se adoptó la biblioteca?"),
    # no un ajuste editable desde /ui/ajustes. Se guardan bajo una clave
    # con prefijo "_" para distinguirlos a simple vista de los campos de
    # integración si alguien inspecciona la fila a mano.
    async def get_flag(self, key: str) -> bool:
        row = await self._row()
        return bool((row.values or {}).get(key, False))

    async def set_flag(self, key: str, value: bool) -> None:
        row = await self._row()
        values = dict(row.values or {})
        values[key] = value
        row.values = values
        await self.db.flush()

    async def ensure_secret_key(self) -> str:
        """A6: llamado una vez desde el lifespan de main.py. Genera
        secret_key (firma la cookie de sesión) solo si todavía no existe
        — nunca la regenera en un arranque posterior, o toda sesión
        activa se invalidaría de golpe en cada reinicio/deploy."""
        row = await self._row()
        values = dict(row.values or {})
        clave = values.get("secret_key")
        if clave:
            apply_overrides({"secret_key": clave})
            return clave
        clave = secrets.token_hex(32)
        values["secret_key"] = clave
        row.values = values
        await self.db.flush()
        apply_overrides({"secret_key": clave})
        return clave


def apply_overrides(values: dict[str, Any]) -> None:
    """Muta el Settings ya cacheado — ver docstring del módulo."""
    settings = get_settings()
    for key, value in values.items():
        if key in _ALL_FIELDS:
            setattr(settings, key, value)


async def load_overrides_at_startup(db: AsyncSession) -> None:
    """Llamado una vez desde el lifespan de main.py: sin esto, un
    override guardado en una ejecución anterior no se vería hasta el
    primer guardado posterior desde /ui/ajustes en la ejecución nueva."""
    overrides = await RuntimeSettingsService(db).get_overrides()
    apply_overrides(overrides)
