# Medición honesta del parser

> Existe porque durante días se reportó un "63% de acierto" que era **una
> cifra sesgada**: salía de 41 casos elegidos a mano *porque fallaban*.
> Un número así no sirve para decidir nada. Esto lo sustituye.

## Las dos preguntas, que NO son la misma

| Pregunta | Métrica | Qué pasa si se ignora |
|---|---|---|
| ¿Miente? | **veraz** = no afirma nada falso | Se corrompe el catálogo en silencio |
| ¿Puede archivarlo solo? | **clasifica** = serie + número correctos | El coleccionista acaba clasificando a mano |

Un archivo sin número (una obra única) que el parser resuelve diciendo
"serie X, sin número" es **correcto** aunque no sea clasificable. Mezclar
las dos cosas fue un error real de la primera versión de esta medición y
hundía artificialmente la cifra.

## Método

1. **`muestreo_estratificado.py`** — muestra estratificada por tamaño de
   cohorte, sobremuestreando el long tail (donde vive el error) y
   ponderando después por el tamaño real de cada estrato. Semilla fija.
2. **`etiquetas.py`** — verdad de referencia escrita **antes** de mirar la
   salida del parser (evita sesgo de confirmación). Marca además los casos
   cuya respuesta NO está en el nombre del archivo: son el **techo** del
   parsing por nombre, no un fallo que arreglar con más regex.
3. **`evaluar_real.py`** — compara contra el pipeline REAL (capa 0
   ComicInfo + capa 1 naming), no solo contra `parse_comic_filename`.
4. **`censo.py`** — censo de la población entera (sin verdad de
   referencia): cobertura, cohortes y presencia de ComicInfo.
5. **`sonda_cbr.py`** — mide si los CBR llevan ComicInfo dentro, con
   tiempos p50/p95. Decide si merece la pena una dependencia para leerlos.

```bash
python3 muestreo_estratificado.py /ruta/a/biblioteca --n 200 --seed 42 --out muestra81.csv
PYTHONPATH=../../src python3 evaluar_real.py
PYTHONPATH=../../src python3 sonda_cbr.py 200
```

## Resultados (2026-09-25, 762 cómics reales, n=81)

```
CLASIFICA SOLO ....... 74%   (poblacional, ponderado por estrato)
ES VERAZ ............. 76%
errores .............. 14/81 en muestra cruda (sobremuestrea el tail)
```

**La sonda de CBR mató la hipótesis principal:** solo **1 de 200 CBR**
lleva ComicInfo.xml (0,5%), frente al **75% de los CBZ**. La metadata
embebida existe en la escena digital inglesa (CBZ) y no en la española
(CBR), que es el 75% de esta biblioteca. Conclusión: **no añadir `unrar`/
`bsdtar` como dependencia** — no hay nada que leer ahí dentro.

## Aviso de sesgo, explícito

Las etiquetas de `etiquetas.py` las escribió el mismo agente que escribió
el parser. Se mitigó etiquetando antes de ejecutar nada, pero **conviene
que el coleccionista revise por encima** `muestra81.csv`: si una etiqueta
está mal, la cifra está mal.
