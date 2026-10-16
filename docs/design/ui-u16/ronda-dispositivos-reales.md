# Ronda en dispositivos reales — U16 (#203, criterio 4)

> **Estado: NOT RUN en todas las filas, y FUERA DEL ALCANCE EXIGIDO.** El 2026-10-16 el responsable fijó #203 como **validación emulada** en
> un Debian de ensayo aislado, **sin móviles de prueba y sin tocar la Pi** (ver [`verificacion-u16.md`](verificacion-u16.md)). Este registro
> **se conserva** por si algún día se ejecuta la ronda real, pero **ya no es un requisito para aceptar esta versión de #203** ni una deuda
> que lo impida. **Un NOT RUN sigue sin contar como PASS**, y ningún cierre se referirá a compatibilidad certificada con teléfonos reales.
> *(Hasta el 2026-10-15 la tarjeta decía lo contrario —«no se cierra con iPhone y Android en NOT RUN»—; esa lectura queda sustituida.)*

## Qué hay que hacer (por pantalla y por dispositivo)

Dispositivos: **iPhone con Safari** y **Android de gama baja con Chrome**, contra la **Pi** (no contra el ensayo), con la aplicación
desplegada con el código de esta tarjeta. Anchos: 360, 390 y 414 px (si el teléfono no tiene exactamente ese ancho, se anota el real).

1. **Sin desplazamiento lateral:** abrir la pantalla y arrastrar de lado. PASS = la página no se mueve; FAIL = se desplaza.
2. **Sin zoom al escribir (solo iPhone):** tocar un campo (buscador, número, título, contraseña). PASS = la página no se amplía;
   FAIL = se amplía.
3. **Objetivos suficientes:** tocar los controles primarios (buscar, asignar, ignorar, guardar). PASS = se aciertan sin ampliar y sin
   tocar el vecino; FAIL = hay que repetir o se toca otro control.

Registrar **PASS, FAIL o NOT RUN** (con el motivo si es NOT RUN) y, si es FAIL, el elemento y una captura. Cada celda es *una* pantalla en
*un* dispositivo y *un* ancho.

## Registro

Cuando se ejecute, cada celda llevará `lateral / zoom / objetivos` con PASS o FAIL (el zoom solo se mira en el iPhone: en Android se anota «—»). Mientras tanto, la celda entera es NOT RUN.

| Pantalla | Dispositivo | 360 px | 390 px | 414 px |
|---|---|---|---|---|
| panel (`/ui/`) | iPhone · Safari | NOT RUN | NOT RUN | NOT RUN |
| panel | Android gama baja · Chrome | NOT RUN | NOT RUN | NOT RUN |
| biblioteca (`/ui/biblioteca`) | iPhone · Safari | NOT RUN | NOT RUN | NOT RUN |
| biblioteca | Android gama baja · Chrome | NOT RUN | NOT RUN | NOT RUN |
| ficha-de-serie (`/ui/series/4f0f6305-cd21-4f33-ba36-7c0dd3d2a362`) | iPhone · Safari | NOT RUN | NOT RUN | NOT RUN |
| ficha-de-serie | Android gama baja · Chrome | NOT RUN | NOT RUN | NOT RUN |
| descubrir (`/ui/descubrir`) | iPhone · Safari | NOT RUN | NOT RUN | NOT RUN |
| descubrir | Android gama baja · Chrome | NOT RUN | NOT RUN | NOT RUN |
| por-revisar (`/ui/pendientes`) | iPhone · Safari | NOT RUN | NOT RUN | NOT RUN |
| por-revisar | Android gama baja · Chrome | NOT RUN | NOT RUN | NOT RUN |
| pendientes-por-carpeta (`/ui/pendientes/carpetas`) | iPhone · Safari | NOT RUN | NOT RUN | NOT RUN |
| pendientes-por-carpeta | Android gama baja · Chrome | NOT RUN | NOT RUN | NOT RUN |
| asistente-de-carpeta (`/ui/pendientes/carpetas/asistente`) | iPhone · Safari | NOT RUN | NOT RUN | NOT RUN |
| asistente-de-carpeta | Android gama baja · Chrome | NOT RUN | NOT RUN | NOT RUN |
| revision-de-la-vinculacion (`/ui/pendientes/carpetas/asistente/vinculacion`) | iPhone · Safari | NOT RUN | NOT RUN | NOT RUN |
| revision-de-la-vinculacion | Android gama baja · Chrome | NOT RUN | NOT RUN | NOT RUN |
| deseados (`/ui/wishlist`) | iPhone · Safari | NOT RUN | NOT RUN | NOT RUN |
| deseados | Android gama baja · Chrome | NOT RUN | NOT RUN | NOT RUN |
| mi-biblioteca-auditoria (`/ui/auditoria`) | iPhone · Safari | NOT RUN | NOT RUN | NOT RUN |
| mi-biblioteca-auditoria | Android gama baja · Chrome | NOT RUN | NOT RUN | NOT RUN |
| ajustes (`/ui/ajustes`) | iPhone · Safari | NOT RUN | NOT RUN | NOT RUN |
| ajustes | Android gama baja · Chrome | NOT RUN | NOT RUN | NOT RUN |
| estado (`/estado`) | iPhone · Safari | NOT RUN | NOT RUN | NOT RUN |
| estado | Android gama baja · Chrome | NOT RUN | NOT RUN | NOT RUN |
| aviso-legal-asistente (`/ui/legal`) | iPhone · Safari | NOT RUN | NOT RUN | NOT RUN |
| aviso-legal-asistente | Android gama baja · Chrome | NOT RUN | NOT RUN | NOT RUN |
| aviso-legal-texto (`/legal`) | iPhone · Safari | NOT RUN | NOT RUN | NOT RUN |
| aviso-legal-texto | Android gama baja · Chrome | NOT RUN | NOT RUN | NOT RUN |

## Lo que SÍ se ha medido (emulación; no sustituye a lo anterior)

Chrome 154 con viewport táctil emulado, contra un ensayo aislado: ver [`README.md`](README.md) y los datos en bruto
(`medicion-antes.json`, `medicion-despues.json`). Una emulación no reproduce el zoom de Safari ni el tamaño de los dedos; por eso
estas filas siguen en NOT RUN.
