# Parser: contexto de carpetas y acrónimos (2026-11-11)

Cuatro reglas nuevas en `naming.py`, todas con evidencia de carpeta y sin
catálogo. No sustituyen la serie por la carpeta por defecto.

## 1. Acrónimos de carpeta

- `JLD` + carpeta `Justice League Dark` → **Justice League Dark**.
- `OP`/`OP883` + `One Piece` → **One Piece**, con #966/#883.
- `927.cbr` sin serie pero con contexto `One Piece / Volumen 92` → **One Piece #927**.

Se exige que las iniciales de una carpeta coincidan con el acrónimo; no se
aplica a una carpeta de una sola palabra ni a una serie que ya coincide.

## 2. Contexto abuelo+padre

`Injustice - Gods Among Us - Año 3 #13`:

- carpeta: `Injustice - Gods Among Us / Injustice Año 3`;
- alternativa del nombre: `Injustice Gods Among Us Año 3`;
- los tokens de la alternativa están en el contexto → se usa la alternativa.

También resuelve `Green Lantern - Origenes Secretos` y `Superman: Year One`
cuando ambos tramos están en la ruta.

## 3. Carpeta que termina en la serie

`The Corinthian - Death in Venice 03`:

- parser: `Death in Venice`;
- carpeta: `The corinthian-death in venice`;
- la carpeta termina en la serie y añade el prefijo → se usa la carpeta.

## 4. Anual sin número en la serie corta

`Lobo - Anual 1` → **Lobo Anual #1**; la alternativa termina en Annual/Anual y
la serie corta es su prefijo.

## 5. Medición

| Medida | Antes | Después |
|---|---:|---:|
| Parser serie | 171 | **182 / 200** |
| Parser número | 196 | **197 / 200** |
| Parser ambos | 170 | **181 / 200** |
| Matcher enlaces | 94 | **95** |
| Identidad serie+número | 94/94 | **95/95** |
| Cobertura | 47,0 % | **47,5 %** |
| Desajustes de formato | 2 | **2** |

Tests del parser: **178** en verde; suite afectada completa en verde.

Quedan fallos que dependen de catálogo o de títulos canónicos sin señal en la
carpeta: `Batman: Shadow of the Bat`, `Green Lantern: Emerald Warriors`,
`Forever Evil: A.R.G.U.S`, `Supergirl: Woman of Tomorrow`, etc.
