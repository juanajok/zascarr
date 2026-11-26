# Antipatrones del proyecto

**Estado: migración en curso.** Reglas trasladadas desde la guía vigente (`CLAUDE.md`, sección 10). La copia de la guía se conserva; trasladar no retira la norma.

## PRE-23-1 — Interfaz sin SPA ni build de Node

Prohibido SPA, build de Node y frameworks reactivos como Alpine, Vue o React (ADR 0001, definitivo). Única excepción: el lector propio puede usar un único `static/lector.js` sin dependencias ni build, solo en su pantalla (ADR 0021).

## PRE-23-2 — No esperar que el enum Postgres se cree solo

`create_type=False` esperando que funcione sin un `postgresql.ENUM` explícito es un antipatrón documentado: el `create_table` vuelve a crear tipos si no se le dice lo contrario.

## PRE-23-3 — Nada de `Wishlist(**data)` desde el cuerpo crudo

El mass assignment se cerró con esquemas Pydantic explícitos; no se reabre pasando el cuerpo crudo a un modelo.

## PRE-23-4 — Sin hotlinking en la interfaz

La interfaz nunca carga recursos externos directamente; las portadas se sirven desde caché local o del propio archivo.

## PRE-23-5 — No copiar scrapers sin verificar en vivo

Copiar un scraper de un documento de referencia sin probarlo contra el servicio real es un antipatrón: Tebeosfera exigió `follow_redirects=True` porque sus CDN devuelven 302.

## PRE-23-6 — Sin credenciales ni fuentes por defecto

Ninguna credencial ni fuente de contenido viene configurada por defecto en `config.py` ni en el bootstrap.

## PRE-23-7 — La aceptación legal no es middleware

Un middleware global de aceptación legal rompe los tests con sesión simulada y castiga al usuario por consultar su biblioteca. Es una dependencia sobre las acciones de riesgo.

## Límites

Estos antipatrones no sustituyen a los ADR que los justifican ni a las pruebas que los detectan. Si una excepción nueva se aprueba, se registra aquí con su motivo.
