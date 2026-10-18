# M4-01 — Observación 1 (primer intento)
- Entrada: `sudo bash bootstrap.sh < /dev/null` (sin terminal), código del candidato 0a591d6 (bootstrap.sh SHA-256 e8860ff2…44fc4), VM limpia, red cerrada, clon desde el espejo local.
- Resultado: **RC=1**. El instalador copia `.env.example` a `/opt/zascarr/.env` y se detiene en «Validando .env»:
  «DB_PASSWORD tiene el valor por defecto. Edita /opt/zascarr/.env y pon una contraseña segura.»
- Clasificación: **comportamiento del candidato, no condición del arnés** (no falta ningún recurso; el fallo no depende del espejo ni de la red).
  El mensaje es claro y en español (no queda oculto), pero **hay un paso manual obligatorio** (editar `.env`) que el README no menciona
  («pegar una línea», «3 preguntas»). La validación de la Pi usó un `.env` escrito a mano (guion §4.1).
- Efectos colaterales a registrar: se creó el usuario/grupo `media`, el clon en /opt/zascarr/zascarr, `.env`, y las carpetas
  Comics, Manga, BD, Tebeos, Fumetti, Manhwa, Graphic Novels, _Unsorted (y Comics/_Specials, Comics/_Omnibus) dentro de /media/library.
- Decisión: continuar aplicando el paso que pide el propio instalador, registrado como **intervención manual**, para poder medir M4-02.
