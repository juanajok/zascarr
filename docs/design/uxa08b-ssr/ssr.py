"""SSR (Semantic Similarity Rating) sobre las opiniones abiertas de los consumidores sintéticos.

Pasos (los del método): texto abierto -> vector -> similitud con cinco frases de referencia (1..5)
-> distribución de probabilidad sobre 1..5 (no una nota rígida) -> promedio sobre varios conjuntos de
referencia.

DESVIACIÓN DECLARADA: aquí el «embedding» es un TF-IDF de n-gramas de caracteres hecho a mano con la
biblioteca estándar (no hay modelo neuronal instalado ni permiso para bajarlo). Es un proxy léxico, no
semántico: captura palabras y raíces compartidas, no paráfrasis.
"""
from __future__ import annotations

import json
import math
import random
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

CARPETA = Path(__file__).parent / "respuestas"
TAREAS = {"t1": "Abrir la serie «Flash»", "t2": "Comprobar si algo falla",
          "t3": "Qué hacer ante el punto de aviso"}

# Tres conjuntos de cinco frases de referencia (1 = muy difícil ... 5 = muy fácil).
REFERENCIAS = [
    ["Me resultaría imposible o muy frustrante, no sabría por dónde empezar.",
     "Me costaría bastante, dudaría y tendría que probar varias cosas.",
     "Lo conseguiría, pero con alguna duda o rodeo.",
     "Lo encontraría con facilidad, casi sin pensarlo.",
     "Lo encontraría al instante, es evidente y directo."],
    ["Es confuso, nada indica dónde está lo que busco.",
     "No es intuitivo, tendría que ir adivinando.",
     "Es aceptable, aunque no del todo claro.",
     "Es claro y fácil de seguir.",
     "Es clarísimo, está justo donde lo esperaría."],
    ["No lo encontraría; me daría por vencido.",
     "Lo encontraría con mucho esfuerzo.",
     "Lo encontraría con algo de esfuerzo.",
     "Lo encontraría con poco esfuerzo.",
     "Lo encontraría sin esfuerzo alguno."],
]

N_GRAMAS = (3, 4, 5)
EPSILON = 1e-3
SEMILLA = 20261123
REMUESTREOS = 4000


def normalizar(texto: str) -> str:
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", texto.lower())
                         if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9ñ ]+", " ", sin_tildes)


def gramas(texto: str) -> Counter:
    cuenta: Counter = Counter()
    for palabra in normalizar(texto).split():
        marco = f"_{palabra}_"
        for n in N_GRAMAS:
            for i in range(max(len(marco) - n + 1, 0)):
                cuenta[marco[i:i + n]] += 1
    return cuenta


def construir_vectorizador(corpus: list[str]):
    docs = [gramas(t) for t in corpus]
    df: Counter = Counter()
    for d in docs:
        df.update(d.keys())
    n = len(docs)
    idf = {g: math.log((1 + n) / (1 + f)) + 1.0 for g, f in df.items()}

    def vectorizar(texto: str) -> dict[str, float]:
        c = gramas(texto)
        v = {g: (1 + math.log(tf)) * idf.get(g, 1.0) for g, tf in c.items()}
        norma = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {g: x / norma for g, x in v.items()}
    return vectorizar


def coseno(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(g, 0.0) for g, x in a.items())


def pmf(similitudes: list[float]) -> list[float]:
    """Método SSR: se resta la similitud mínima (el suelo) y se normaliza."""
    minimo = min(similitudes)
    pesos = [s - minimo + EPSILON for s in similitudes]
    total = sum(pesos)
    return [p / total for p in pesos]


def distribucion(texto: str, vectorizar) -> list[float]:
    v = vectorizar(texto)
    por_conjunto = []
    for conjunto in REFERENCIAS:
        por_conjunto.append(pmf([coseno(v, vectorizar(r)) for r in conjunto]))
    return [sum(p[i] for p in por_conjunto) / len(por_conjunto) for i in range(5)]


def esperado(p: list[float]) -> float:
    return sum((i + 1) * x for i, x in enumerate(p))


def media(xs):
    return sum(xs) / len(xs)


def intervalo(xs, rng):
    remuestras = sorted(media([rng.choice(xs) for _ in xs]) for _ in range(REMUESTREOS))
    return remuestras[int(0.025 * REMUESTREOS)], remuestras[int(0.975 * REMUESTREOS) - 1]


def main() -> None:
    datos = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(CARPETA.glob("[AB]-*.json"))]
    if len(datos) < 16:
        print(f"Solo hay {len(datos)} ficheros (se esperaban 16).")
    textos = [d[t] for d in datos for t in TAREAS if isinstance(d.get(t), str)]
    refs = [r for c in REFERENCIAS for r in c]
    vectorizar = construir_vectorizador(textos + refs)

    # Comprobación de validez del vectorizador: cada frase de referencia debe caer en su propio 1..5.
    aciertos = 0
    for c in REFERENCIAS:
        for i, frase in enumerate(c):
            v = vectorizar(frase)
            sims = [coseno(v, vectorizar(r)) for r in c]
            aciertos += sims.index(max(sims)) == i
    print(f"Validez (la frase de referencia se reconoce a sí misma): {aciertos}/15\n")

    rng = random.Random(SEMILLA)
    resultados: dict = {}
    for d in datos:
        for t in TAREAS:
            if isinstance(d.get(t), str):
                p = distribucion(d[t], vectorizar)
                resultados[(d["variante"], d["perfil"], t)] = {"pmf": p, "e": esperado(p)}

    perfiles = sorted({k[1] for k in resultados})
    salida = {}
    print("| Tarea | Variante | Media esperada | IC 95 % | P(1) | P(2) | P(3) | P(4) | P(5) | n |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for t, nombre in TAREAS.items():
        for v in ("A", "B"):
            es = [resultados[(v, p, t)]["e"] for p in perfiles if (v, p, t) in resultados]
            if not es:
                continue
            lo, hi = intervalo(es, rng)
            pm = [media([resultados[(v, p, t)]["pmf"][i] for p in perfiles
                         if (v, p, t) in resultados]) for i in range(5)]
            salida[f"{t}-{v}"] = {"media": media(es), "ic": [lo, hi], "pmf": pm, "n": len(es)}
            print(f"| {nombre} | {v} | {media(es):.2f} | {lo:.2f}–{hi:.2f} | "
                  + " | ".join(f"{x:.2f}" for x in pm) + f" | {len(es)} |")

    print("\nDiferencia pareada B − A por perfil (misma persona sintética en las dos variantes):")
    print("| Tarea | Δ media | IC 95 % | Perfiles con B > A |")
    print("|---|---|---|---|")
    for t, nombre in TAREAS.items():
        difs = [resultados[("B", p, t)]["e"] - resultados[("A", p, t)]["e"]
                for p in perfiles if ("A", p, t) in resultados and ("B", p, t) in resultados]
        if not difs:
            continue
        lo, hi = intervalo(difs, rng)
        mejora = sum(1 for x in difs if x > 0)
        salida[f"{t}-dif"] = {"media": media(difs), "ic": [lo, hi], "b_mayor": mejora, "n": len(difs)}
        print(f"| {nombre} | {media(difs):+.2f} | {lo:+.2f} a {hi:+.2f} | {mejora}/{len(difs)} |")

    # Dispersión: ¿el método distingue algo? (si todas las PMF son casi planas, no discrimina)
    planas = sum(1 for r in resultados.values() if max(r["pmf"]) - min(r["pmf"]) < 0.08)
    print(f"\nPMF casi planas (rango < 0,08): {planas}/{len(resultados)}")
    (CARPETA.parent / "resultado-ssr.json").write_text(
        json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
