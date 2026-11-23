# Conflictos de la biblioteca y estrategia (2026-11-23)

> Análisis de solo lectura sobre la biblioteca real. No aplica cambios; las decisiones de
> datos son del PO y se ejecutan por lotes con copia y confirmación.

## 1. Qué se ha encontrado

### 1.1 Los 4 grupos de G1 **no son duplicados**

G1 agrupa por título normalizado; al mirar los datos, cada grupo es una cosa distinta:

| Grupo | Fichas | Conclusión |
|---|---|---|
| `ANIMAL MAN` (Tebeosfera 1989 Zinco, 26 nº) / `Animal Man` (CV 2011, 4 nº) | dos ediciones/volúmenes | **no duplicado** |
| `El Batman Que Rie` (regular, 7 nº) / `El Batman Que Rie` (one_shot, 1 nº) | serie + one-shot del evento | **no duplicado** |
| `The DC Universe by Mike Mignola` (CV 101682, 0 nº) / (manual one_shot, 1 archivo) | la del CV está **vacía** | no duplicado: ficha CV vacía |
| `Monstress` (CV 92191, 7 nº) / `Monstress` (manual, 23 nº) | dos volúmenes/ediciones | **no duplicado** |

Lección: el detector por título solo **genera falsos positivos**, igual que el matcher por
título. Un duplicado real exige coincidir en **año, tipo y solapamiento de números**, no en
el texto.

### 1.2 Números sin archivo (3)

`Batman Vol 1 #2A3`, `Green Lantern #98`, `Green Lantern: War of the Green Lanterns #07`.
No hay números repetidos dentro de una serie (la unicidad se cumple).

### 1.3 Asociaciones dudosas

50 medias (0,70–0,80), 65 débiles, 15 sin candidato, 11 con error de fuente. Las 76 fuertes
están aplicadas y con evidencia; B9 marca 1 (Monstress, edición Cross Cult/Image).

### 1.4 Edición, tie-ins y anuales

8 títulos distintos (edición original/española o puntuación), 2 B2b y 2 B7 de edición,
38 C2c aceptados como dato, 4 Flashpoint corregidos y SUPERMAN corregido.

## 2. Estrategia

1. **Detector de duplicados por identidad**: título normalizado **+** año (±1) **+** tipo
   (`kind`) **+** solapamiento de números/archivos. Solo entonces se ofrece fusionar; nunca
   automático. El título solo no basta.
2. **Fusión con confirmación y copia**: mostrar las dos fichas con sus archivos y el número
   que se queda; mover issues/archivos, conservar la procedencia del superviviente y borrar
   la vacía. Sin fusión en masa.
3. **Una fuente de verdad por serie** (ya implementado): `metadata_source` + id +
   `locked_fields`; el enricher no toca manual; la primera fuente solo con acción explícita.
4. **Confianza y cola de revisión**: ≥ 0,85 aplicar con evidencia CCM; 0,70–0,85 revisar;
   < 0,70 no proponer. Las 50 medias son esa cola.
5. **Huérfanos a revisión**, no a borrado automático: ¿sobra el número o falta el archivo?
6. **Tie-ins y anuales**: `kind` visible, saga no asociable, aviso si la local mezcla
   números de la principal y del evento; el `StoryArc` queda para arcos, no para asociar.
7. **Medida y reversibilidad**: censo antes/después, B9, copia por lote y ningún cambio en
   masa.

## 3. Prioridad

- **Ahora:** mejorar G1 (identidad, no título) y revisar la ficha CV vacía de DC Universe;
  los 3 huérfanos a la cola.
- **Después:** las 50 medias con evidencia y confirmación; la edición de Monstress.
- **Estructural:** pantalla de duplicados con fusión confirmada, reglas del import/triage y
  el marcado de tie-in en la comparación.
