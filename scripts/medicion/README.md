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
   cohorte (carpeta contenedora), sobremuestreando el long tail y
   ponderando después por el tamaño real de cada estrato. Semilla fija
   → `muestra_bruta.csv` (columnas vacías, para etiquetar sin mirar el
   parser).
2. **`etiquetas.py`** — verdad de referencia escrita **antes** de
   ejecutar el parser (evita sesgo de confirmación). Marca los casos
   `requiere_contexto=True`: aquellos cuya respuesta correcta NO está en
   el nombre del archivo (abreviatura que solo la carpeta resuelve,
   autor delante de la obra) — es el **techo** real del parsing por
   nombre, no un fallo que arreglar con más regex.
3. **`evaluar_real.py`** — compara contra el pipeline REAL (capa 0
   ComicInfo + capa 1 naming, no solo `parse_comic_filename` aislado);
   deduplica por SHA256 (no por nombre — dos archivos con nombres
   distintos y contenido idéntico cuentan como el mismo hallazgo) y
   comprueba consistencia entre gemelos. Escribe
   `muestra81_etiquetada.csv`, **autocontenido**: no hace falta cruzar
   con `etiquetas.py` para auditar una fila.
4. **`censo.py`** — censo de la población entera (sin verdad de
   referencia): cobertura, cohortes y presencia de ComicInfo.
5. **`sonda_cbr.py`** — mide si los CBR llevan ComicInfo dentro, con
   tiempos p50/p95. Decide si merece la pena una dependencia para leerlos.

```bash
python3 muestreo_estratificado.py /ruta/a/biblioteca --n 200 --seed 42 --out muestra_bruta.csv
# → etiquetar etiquetas.py a mano, SIN mirar la salida del parser
PYTHONPATH=../../src python3 evaluar_real.py
PYTHONPATH=../../src python3 sonda_cbr.py 200
```

## Resultado oficial (2026-09-26, 762 cómics reales, n=81 rutas → 62 de contenido único, cohorte activa)

```
SOBRE CONTENIDO ÚNICO (n=62, la cifra que cuenta):
  CLASIFICA SOLO ... 83%   (antes de la cohorte: 73%)
  ES VERAZ .......... 86%   (antes de la cohorte: 76%)

Vía usada en la muestra: capa1_nombre 74, capa1_cohorte 5, capa0_comicinfo 2

Consistencia entre gemelos: 19 pares por SHA256, 0 divergencias
  (RF-20, determinismo, verificado con datos reales — no solo en teoría)

Techo del parsing por nombre: 3 archivos de 62 (5%) cuya respuesta
correcta NO está en el nombre del archivo — solo B14 (carpeta) los
resuelve.
```

**+10 puntos por `core/cohort.py`** (detección de prefijos de orden de
lectura por evidencia de cohorte — ver `docs/BACKLOG.md`): un prefijo
numérico suelto ("42 Dreadstar...", "65 Dreadstar...") es la MISMA
forma que un título que empieza por cifra ("100 Balas...") — ninguna
regla local del parser los distingue sin inventar. Los propios datos
sí: "Dreadstar" aparece con ~70 prefijos distintos y el resto del
nombre estable; "100 Balas" aparece siempre con el mismo "100". Solo 5
de las 81 filas de la muestra usaron la vía cohorte (el resto de
Dreadstar en la muestra ya caía por otras vías o no estaba en la
muestra), y aun así el salto es de 10 puntos — la palanca es real en
población, no solo en la muestra.

Lo que queda sin resolver tras la cohorte es, en su mayoría, el
techo ya documentado: abreviaturas de carpeta (`Avras Cap Torrezno`),
autor delante de la obra (`Hiroaki Samura`) y ediciones cuyo nombre de
línea editorial diverge del de la serie real (`Jim Starlin's
Dreadstar` — la cohorte SÍ quitó el prefijo correctamente; lo que
queda es una cuestión de alias/matcher, no de la cohorte).

**La primera versión de este informe reportaba 74%/76% sobre 81
*rutas*, no sobre contenido.** 19 de esas 81 rutas eran copias
duplicadas por descarga (`archivo.cbr` + `archivo(1).cbr`, mismo
SHA256) — contaban el mismo hallazgo dos veces e inflaban artificialmente
N sin aportar información nueva. Corregido: la cifra oficial es sobre
**contenido único** (n=62). El punto ponderado apenas se movió (74%→73%,
76%→76%) porque los duplicados se concentraban en el estrato
`B_pequena`, que ya pesa poco en la media ponderada por tamaño
poblacional — pero la potencia estadística real de la muestra sí baja,
de 81 a 62.

**La sonda de CBR mató la hipótesis principal de la primera ronda:**
solo **1 de 200 CBR** lleva ComicInfo.xml (0,5%), frente al **75% de los
CBZ**. La metadata embebida existe en la escena digital inglesa (CBZ) y
no en la española (CBR), que es el 75% de esta biblioteca. Conclusión:
**no añadir `unrar`/`bsdtar` como dependencia** — no hay nada que leer
ahí dentro. (`7z`, ya instalado, basta para la sonda: lista sin
descomprimir con `7z l`, así que el contraste es fiable incluso con
archivos RAR sólidos.)

## Nota sobre los estratos

El estrato `C_media` (cohortes de 11-50 archivos) no aparece: no existía
en la población en el momento del muestreo. La biblioteca tiene una
carpeta plana `Tebeos/Tebeos/` con 711 archivos sueltos sin subcarpetas
(volcado de descargas, no una biblioteca organizada por carpetas) que
colapsa en la macro-cohorte `D_grande`, y el resto son carpetas temáticas
de 2-10 archivos (`B_pequena`). No es una omisión del muestreo.

## Aviso de sesgo, explícito

Las etiquetas de `etiquetas.py` las escribió el mismo agente que escribió
el parser. Se mitigó etiquetando antes de ejecutar nada, pero **conviene
que el coleccionista revise por encima** `muestra81_etiquetada.csv`: si
una etiqueta está mal, la cifra está mal.
