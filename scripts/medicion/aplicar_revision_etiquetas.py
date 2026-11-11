"""Aplica una revisión simulada a la muestra etiquetada de 200.

Entradas:
- ``--original``: CSV etiquetado de primera pasada.
- ``--revision``: CSV del revisor con id/estado y valores revisados.
- ``--output``: CSV final con etiquetas aplicadas.
- ``--cambios``: CSV de cambios para auditoría.

No lee el parser, el matcher ni el CSV de contexto. No modifica la entrada.
Las filas ``dudosa`` conservan la etiqueta original pero se marcan con
``excluir_benchmark=TRUE`` para que la métrica pueda separarlas.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

TIPOS = {"grapa", "anual", "capitulo", "tomo", "obra_unica",
         "pack", "especial", "desconocido"}
ESTADOS = {"mantener", "corregir", "dudosa"}


def _leer(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--original", required=True)
    ap.add_argument("--revision", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--cambios", required=True)
    args = ap.parse_args()

    original = _leer(Path(args.original))
    revision = _leer(Path(args.revision))
    if len(original) != 200 or len(revision) != 200:
        raise SystemExit(
            f"Se esperaban 200 filas: original={len(original)} "
            f"revision={len(revision)}")
    por_id = {r["id"]: r for r in revision}
    if len(por_id) != 200:
        raise SystemExit("La revisión tiene ids duplicados")
    if set(por_id) != {r["id"] for r in original}:
        raise SystemExit("Los ids de la revisión no coinciden con la muestra")

    final: list[dict] = []
    cambios: list[dict] = []
    for r in original:
        rev = por_id[r["id"]]
        estado = (rev.get("estado") or "").strip().lower()
        if estado not in ESTADOS:
            raise SystemExit(f"Estado inválido para {r['id']}: {estado!r}")
        fila = dict(r)
        fila["revision_estado"] = estado
        fila["revision_motivo"] = (rev.get("motivo") or "").strip()
        fila["revision_por"] = "simulacion_agente"
        fila["excluir_benchmark"] = "TRUE" if estado == "dudosa" else "FALSE"
        if estado == "corregir":
            # El número puede quedar vacío en una corrección de tipo/serie
            # (p. ej. un álbum sin número); serie y tipo sí son obligatorios.
            for campo in ("serie_revisada", "tipo_revisado"):
                if not (rev.get(campo) or "").strip():
                    raise SystemExit(f"Falta {campo} en corrección de {r['id']}")
            nuevo_tipo = rev["tipo_revisado"].strip().lower()
            if nuevo_tipo not in TIPOS:
                raise SystemExit(f"Tipo inválido en {r['id']}: {nuevo_tipo}")
            fila["serie_real"] = rev["serie_revisada"].strip()
            fila["numero_real"] = (rev.get("numero_revisado") or "").strip()
            fila["tipo_real"] = nuevo_tipo
            if (rev.get("requiere_contexto_revisado") or "").strip().upper() in {"TRUE", "FALSE"}:
                fila["requiere_contexto"] = rev["requiere_contexto_revisado"].strip().upper()
            cambios.append({
                "id": r["id"], "archivo": r["archivo"], "estado": estado,
                "serie_original": r["serie_real"], "numero_original": r["numero_real"],
                "tipo_original": r["tipo_real"],
                "serie_revisada": fila["serie_real"], "numero_revisado": fila["numero_real"],
                "tipo_revisado": fila["tipo_real"],
                "motivo": fila["revision_motivo"],
            })
        elif estado == "dudosa":
            cambios.append({
                "id": r["id"], "archivo": r["archivo"], "estado": estado,
                "serie_original": r["serie_real"], "numero_original": r["numero_real"],
                "tipo_original": r["tipo_real"],
                "serie_revisada": "", "numero_revisado": "", "tipo_revisado": "",
                "motivo": fila["revision_motivo"],
            })
        final.append(fila)

    out = Path(args.output)
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(final[0].keys()))
        w.writeheader()
        w.writerows(final)
    ch = Path(args.cambios)
    with ch.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cambios[0].keys()) if cambios else [
            "id", "archivo", "estado", "serie_original", "numero_original",
            "tipo_original", "serie_revisada", "numero_revisado",
            "tipo_revisado", "motivo"])
        w.writeheader()
        w.writerows(cambios)
    from collections import Counter
    print("estados:", dict(Counter(r["revision_estado"] for r in final)))
    print("output:", out.resolve())
    print("cambios:", ch.resolve())


if __name__ == "__main__":
    main()
