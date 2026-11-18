# Benchmark previo — LECUX1 (ajustes de imagen)

- **Historia:** [#1068](https://github.com/juanajok/zascarr/issues/1068); épica #1067.
- **Fuente principal:** `docs/design/benchmark-BL-LEC-mercado-lectores-2026.md` y consulta de
  las guías de las apps (2026-11-18). Lo no comprobado se marca **NOT RUN**.

## Lo observado

| App | Qué ofrece / cómo | Decisión para ZascArr |
|---|---|---|
| **Panels** | Filtros de imagen en el menú «…»: reducir ruido, nitidez, quitar bordes, reducir muaré; se aplican varias capas. [Guía](https://guides.panels.app/read-content/image-filters) | **Descartar** nitidez/ruido/bordes/muaré: requieren análisis de imagen y coste en la Pi. Se adopta la idea de ajustes visuales en cliente. |
| **Kavita** | Menú extendido con **Brightness** (brillo) y otras opciones del lector; no recodifica el archivo. [Wiki](https://wiki.kavitareader.com/guides/readers/comic-manga/) | **Adoptar** brillo como `filter` CSS acotado, sin petición al servidor. |
| **YACReader** | `A` ajusta al ancho/alto, `D` doble página, `L`/`R` rotan, `W` tamaño completo y lupa; son transformaciones de vista, no recodificación. [Atajos](https://github.com/yacreader/yacreader/blob/328ea1a9d606034cd5da1e9c326eff235217d1c4/files/shortcuts.html) | **Adoptar** la idea de que los ajustes son de vista y reversibles; **descartar** rotación y lupa propia (zoom nativo ya decidido). |
| **Perfect Viewer / OpenComic** | La ficha de mercado les atribuye brillo/contraste/gamma y filtros; sus versiones/OPDS/PSE están **NOT RUN** en la ficha | **Adaptar** solo brillo/contraste/sepia/invertir con CSS; no se copia su UI ni sus filtros de análisis. |
| **Komga** | Fondo claro/gris/negro y opciones de visualización; no se verificó un control de brillo en su webreader | **Descartar** como fuente de filtros; el fondo ya se decidió en LECUX6. |

## Decisión

Solo se implementan **brillo**, **contraste**, **sepia** e **invertir** mediante `filter` de CSS
sobre el contenedor de páginas:

- no se recodifica, redimensiona ni vuelve a pedir ninguna página;
- el `ETag`, los bytes y el servidor no cambian;
- no hay nitidez, reducción de ruido, recorte, muaré, gamma ni colorización: análisis de imagen
  descartado por coste en la Pi y por el alcance del benchmark (§4.2/§7.5);
- preferencia por dispositivo en `localStorage`, con valores neutros si falla;
- el filtro no toca controles, barra ni interfaz.

Esto aplica la decisión D-LUX3 del PO y no amplía la historia con funciones que el benchmark no
justifica para esta instalación.
