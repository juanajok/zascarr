# Contrato de seguridad y red

**Estado: migración en curso.** Reglas trasladadas desde la guía vigente. La copia de `CLAUDE.md` se conserva: trasladar **no** retira la norma hasta aprobación expresa. Ante discrepancia, manda la guía y este fichero se corrige.

## PRE-03 — Mass assignment prohibido en endpoints

Los endpoints de escritura usan esquemas Pydantic explícitos (`WishlistCreate`, `SeriesCreate`), nunca `Model(**data)` ni `setattr(model, k, v)` sobre el cuerpo crudo. El hallazgo M1 del peer review se cerró con ese patrón: se aplica a todos los routers nuevos sin excepción.

## PRE-11 — La aceptación legal bloquea solo acciones de riesgo

Es una **dependencia** (`require_legal_acknowledgment` en `services/legal.py`) sobre las acciones que la requieren, no un middleware global: un middleware rompería los tests con sesión simulada y castigaría al usuario por consultar su propia biblioteca.

## PRE-14 — Toda URL variable pasa por la validación SSRF central

Cualquier petición del servidor a una URL que no sea fija atraviesa `utils/url_portada.py`: lista de nombres permitidos, comprobación de direcciones resueltas públicas (IPv4 e IPv6), conexión a la IP ya validada, redirecciones gestionadas a mano y tope de tamaño. Un token firmado garantiza integridad, **no** la seguridad de una URL externa ([hallazgo H1](../docs/design/hallazgo-h1-cover-url.md)).

## PRE-30 — Cortesía compartida por fuente y por host efectivo

El espaciado entre peticiones externas es **compartido por todo el proceso** (`utils/cortesia.py`), no por instancia de cliente: las fuentes con cliente propio y las portadas externas pasan por la cola por fuente y por host efectivo, contando cada salto HTTP, redirecciones incluidas, con espera visible y presupuestada.

- Tebeosfera mantiene **2.5 s** como mínimo del proyecto aunque la configuración diga menos: es scraping cortés a una asociación cultural sin ánimo de lucro, no una cuestión de bugs.
- Depende de ejecutar **un solo proceso** (`uvicorn --workers 1`). Con varias réplicas no hay coordinación entre ellas y la política es conservadora por instancia; el alcance de lo que se coordina está en [cortesía compartida](../docs/design/cortesia-compartida.md).

## Límites

Este contrato no sustituye a los ADR que originan estas decisiones, ni a la revisión de seguridad del SHA final que exige la clasificación de riesgo. No autoriza cambios de comportamiento en red, legal o API.
