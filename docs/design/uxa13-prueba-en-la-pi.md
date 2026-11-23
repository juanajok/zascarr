# UXA-13 · Guion de la prueba en la Pi (integraciones reales)

**Historias:** #1130 (UXA-13a, PR #1255) · **Quién:** el PO, en la Pi con Prowlarr, el foro y Transmission o aMule reales.
**Para qué:** la historia pide «probar con dobles de cliente y luego en un entorno de prueba con integraciones autorizadas». Los dobles ya están en la PR; esto es lo segundo, y no se puede hacer desde fuera de la Pi.

## Antes de empezar

- Desplegada la versión con #1255 (`sudo bash scripts/update.sh --rama main`) y el aviso legal aceptado.
- Usa un **deseo de prueba** (una serie que no te importe) y bórralo al acabar («Quitar»). **No confirmes ningún envío salvo el de la prueba 6**, y elige un candidato pequeño.
- Anota el estado inicial de Ajustes (qué fuentes y clientes están encendidos) para dejarlo igual al terminar.
- Cada prueba parte de la pantalla Deseados; tras cambiar Ajustes, pulsa «Reintentar» en el deseo (el motivo lo escribe el ciclo o ese botón).

## Pruebas

| # | Cómo provocarlo | Qué debe verse en la fila | Causa esperada |
|---|---|---|---|
| 1 | Apaga Prowlarr, el foro y el blog/RSS en Ajustes → «Reintentar» | «Sin configurar» + «Enciende Prowlarr, el foro o un blog/RSS…» + enlace «Ir a Ajustes» | Sin configurar |
| 2 | Enciende Prowlarr con la clave vacía → «Reintentar» | «Sin configurar» + «Completa la URL y la clave de Prowlarr» + enlace a Ajustes | Sin configurar |
| 3 | Con el foro encendido, haz dos búsquedas seguidas del mismo deseo | «En espera» + «No hace falta hacer nada: se reintenta sola» (sin enlace) | En espera |
| 4 | Para Transmission (o aMule) y deja que el ciclo o un envío lo intente | «Ha fallado» + «Comprueba que Transmission esté encendido…» + enlace a Ajustes | Ha fallado |
| 5 | Añade un deseo con un título inventado («Zzqx Prueba 99») → «Reintentar» | «Sin resultados» + «Prueba «Buscar ahora»…» + enlace «Ver las fuentes» | Sin resultados |
| 6 | «Buscar ahora» en un deseo con resultados → «Descargar este…» | Antes de enviar: «Vas a enviar «título» (origen: …) a **Transmission** o **aMule**. Empezará a descargarse y… no se deshace desde aquí». Solo «Sí, descargar» envía | Confirmación |
| 7 | Con un candidato de enlace `ed2k://` (foro) abre «Descargar este…» | El aviso dice **aMule**; con un magnet o .torrent, **Transmission** | Cliente |

## Qué anotar (una fila por prueba)

| # | ¿Salió la causa esperada? | ¿Se entiende qué hacer? (sí/no + frase textual) | ¿El enlace llevó adonde decía? | Notas / captura |
|---|---|---|---|---|

- En la 6, confirma además: que **no se envió nada** hasta pulsar «Sí, descargar», y que, al confirmar, el cliente indicado recibió el torrent o el enlace y el deseo pasó a «Descargando».
- Si un motivo sale **sin** causa (solo el texto en cursiva), anota el texto exacto: ZascArr no lo reconoce y habrá que clasificarlo.

## Cuándo parar

Si algo se envía sin que lo pidas, para, anota qué pulsaste y avisa antes de seguir. Al terminar, devuelve Ajustes a su estado inicial y quita el deseo de prueba.

## Qué no cubre

La cancelación de una tanda (qué dejó de esperar el navegador y qué sigue en curso) es #1254. Móvil real, lector de pantalla y varios navegadores quedan fuera de este guion.
