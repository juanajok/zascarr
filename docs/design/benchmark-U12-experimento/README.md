# Experimento de U12: qué ocupa una portada que falla (sin JavaScript)

`portada-rota.html` reúne seis tarjetas con una `<img>` cuyo `src` **no existe** (`nope.jpg`) o es válido (`ok.png`,
100 × 150) y mide su alto. Medido el 2026-10-15 en **Google Chrome 154.0.8037.92** (headless, por CDP, `file://`,
tarjeta de 200 px de ancho):

| Variante (CSS de la imagen) | Imagen | Alto de la imagen | Alto de la tarjeta |
|---|---|---|---|
| `aspect-ratio: 2/3` (el actual) | rota | **300 px** | 352 px |
| `height: auto`, **sin** `aspect-ratio`, `alt=""` | rota | **0 px** | **52 px** |
| `aspect-ratio: auto 2/3` | rota | **300 px** | 352 px |
| `height: auto` | cargada | 300 px | 352 px |
| `height: auto; max-height: 140px; object-fit: cover` | cargada | 140 px | 192 px |
| `height: auto`, `loading="lazy"` | rota | **0 px** | 52 px |

**Conclusión acotada:** sin `aspect-ratio`, una imagen rota con `alt=""` no reserva espacio y una cargada ocupa su
sitio, sin `onerror` ni JS. **Solo Chrome.** Firefox y Safari (incluido iOS): **NOT RUN**. Para repetirlo, abrir
`portada-rota.html` en el navegador y leer `offsetHeight` de cada `img` desde la consola.
