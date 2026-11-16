# Novedades semanales — v1 USA/Comic Vine (D5)

> **Fecha:** 2026-11-16. **Alcance aprobado:** primera entrega del track USA; la
> parte de Norma/ECC/Panini queda fuera hasta verificar su HTML real (el BACKLOG
> ya avisaba de que no se construyera sin ese spike).

## Qué hace

- `GET /ui/novedades` muestra los números de Comic Vine con `cover_date` en la
  semana elegida, agrupados por día y filtrables por editorial.
- `GET /api/novedades?semana=AAAA-MM-DD&editorial=…` devuelve lo mismo en JSON.
- Cada número se cruza con la biblioteca:
  - por `comic_vine_id` del volumen (caso normal);
  - si no, por título normalizado exacto y **solo si hay una única serie**.
- «Te interesa» = la serie tiene un deseo activo o una política distinta de
  «ninguno». No se crea ningún deseo ni se descarga nada desde esta pantalla.

## Decisiones

| Tema | Decisión |
|---|---|
| Fecha mostrada | `cover_date` de Comic Vine; es la fecha que la fuente publica. |
| Anunciado/Publicado | `Publicado` si la fecha es hoy o pasada; si no, `Anunciado`. |
| Persistencia | Sin tabla ni migración: se calcula a demanda y se cachea en memoria 30 min. |
| Fuente apagada | Si Comic Vine está apagado o sin clave, la vista lo dice y no consulta. |
| Editorial | Solo se conoce si el volumen casa con una serie local; el resto muestra «Editorial sin dato» y no entra en el filtro. |
| Caché | Una entrada por lunes; no se cachean datos de usuario (solo la respuesta de la fuente). |
| Paginación | Se piden páginas de 100 con `offset` hasta agotar el total de Comic Vine. |
| Cabeceras | UI y API responden `Cache-Control: no-store` (incluyen qué series sigue la persona). |
| Privacidad | No se registran títulos consultados ni la URL pedida. |
| Frecuencia | La caché de 30 min evita repetir la llamada al abrir/refrescar; no hay job semanal todavía. |

## Límites explícitos

- **No** incluye Norma/ECC/Panini: falta el spike de HTML real.
- **No** incluye aviso al móvil por serie seguida (E4/D5 F09): queda como
  siguiente pieza, reutilizando el notificador.
- **No** incluye descarga ni alta automática.
- La vista depende de la cobertura de Comic Vine para futuros; si un número no
  tiene `cover_date`, no aparece.
- El filtro de editorial no puede clasificar los volúmenes que no están en la
  biblioteca; para esos solo se muestra «Editorial sin dato».

## Verificación

- `tests/test_novedades.py`: agrupación, cruce por CV y por título, «Te
  interesa», anunciado/publicado, editoriales, semana ISO, fuente apagada y
  rutas UI/API.
- `tests/test_web_navegacion.py`: entrada de menú, URL, título/h1 y estructura.
- Prueba real pendiente: Comic Vine real desde la Pi con la clave configurada y
  navegador.
