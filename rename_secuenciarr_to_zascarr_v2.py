#!/usr/bin/env python3
"""
Renombrado masivo: SecuenciArr -> ZascArr  (v2)

Correcciones respecto a v1 (detectadas en dry-run 2026-09-22):
  - El script se autoexcluye: ya no se renombra a sí mismo.
  - rename_paths() respeta EXCLUDED_DIRS y excluye *.egg-info y build/.
  - El egg-info viejo y build/ NO se renombran: se borran y se regeneran
    con `pip install -e .` posterior (ver checklist).

Uso:
    python3 rename_secuenciarr_to_zascarr_v2.py --dry-run
    python3 rename_secuenciarr_to_zascarr_v2.py

Requisitos: raíz del repo, git limpio (commit previo).
"""

import os
import re
import sys
import shutil
from pathlib import Path

DRY_RUN = "--dry-run" in sys.argv
SELF = Path(__file__).resolve()

EXCLUDED_DIRS = {".git", ".venv", "venv", "__pycache__", ".mypy_cache",
                 ".pytest_cache", "node_modules", "dist", "build", ".idea"}

BINARY_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
                     ".cbz", ".cbr", ".zip", ".whl", ".db", ".sqlite", ".pyc",
                     ".woff", ".woff2", ".ttf"}

SUBSTITUTIONS = [
    (re.compile(r"SecuenciArr"), "ZascArr"),
    (re.compile(r"secuenciarr"), "zascarr"),
    (re.compile(r"SECUENCIARR"), "ZASCARR"),
]

changed_files = []
renamed_paths = []
deleted_artifacts = []


def is_excluded_path(p: Path) -> bool:
    parts = set(p.parts)
    if parts & EXCLUDED_DIRS:
        return True
    if p.name.endswith(".egg-info"):
        return True
    if p.resolve() == SELF:
        return True
    if "_dump_" in p.name:
        return True
    if "alembic" in p.parts and "versions" in p.parts:
        return True
    return False


def process_file(path: Path):
    if path.suffix.lower() in BINARY_EXTENSIONS or is_excluded_path(path):
        return
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return
    new = text
    for pattern, repl in SUBSTITUTIONS:
        new = pattern.sub(repl, new)
    if new != text:
        changed_files.append(path)
        if not DRY_RUN:
            path.write_text(new, encoding="utf-8")


def rename_paths(root: Path):
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        current = Path(dirpath)
        if is_excluded_path(current):
            continue
        for name in filenames + dirnames:
            old = current / name
            if "secuenciarr" not in name.lower():
                continue
            if is_excluded_path(old):
                continue
            new_name = re.sub(r"secuenciarr", "zascarr", name,
                              flags=re.IGNORECASE)
            if new_name == name:
                continue
            new = current / new_name
            renamed_paths.append((old, new))
            if not DRY_RUN:
                shutil.move(str(old), str(new))


def clean_stale_artifacts(root: Path):
    """Borra build/ y *.egg-info (se regeneran con pip install -e .)."""
    for rel in ["build", "dist"]:
        target = root / rel
        if target.exists():
            deleted_artifacts.append(target)
            if not DRY_RUN:
                shutil.rmtree(target)
    for egginfo in (root / "src").glob("*.egg-info"):
        deleted_artifacts.append(egginfo)
        if not DRY_RUN:
            shutil.rmtree(egginfo)


def main():
    root = Path(".").resolve()
    print(f"{'DRY-RUN: ' if DRY_RUN else ''}escaneando {root}\n")

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not is_excluded_path(Path(dirpath) / d)]
        for fname in filenames:
            process_file(Path(dirpath) / fname)

    rename_paths(root)
    clean_stale_artifacts(root)

    if changed_files:
        print(f"Contenido modificado en {len(changed_files)} ficheros:")
        for f in sorted(changed_files):
            print(f"  - {f.relative_to(root)}")
    if renamed_paths:
        print(f"\nRutas renombradas ({len(renamed_paths)}):")
        for old, new in renamed_paths:
            print(f"  - {old.relative_to(root)}  ->  {new.relative_to(root)}")
    if deleted_artifacts:
        print(f"\nArtefactos eliminados ({len(deleted_artifacts)}):")
        for a in deleted_artifacts:
            print(f"  - {a.relative_to(root)}")

    print("""
================ CHECKLIST MANUAL OBLIGATORIO ================
0. Reinstalar el paquete (egg-info eliminado, nuevo nombre):
     source venv/bin/activate
     pip install -e .
     python3 -c "import zascarr"   # verificación de imports

1. Base de datos:
     sudo -u postgres psql -c "ALTER DATABASE secuenciarr RENAME TO zascarr;"
     sudo -u postgres psql -c "ALTER USER secuenciarr RENAME TO zascarr;"
   (y actualizar en .env: DATABASE_URL u host/user/db si aplica)

2. Docker:
     docker compose down
     docker volume ls | grep secuenciarr   # crear zascarr_* y restaurar
     docker compose up -d

3. systemd:
     sudo systemctl stop 'secuenciarr*'
     sudo systemctl disable 'secuenciarr*'
     # renombrar unit files a zascarr_*.service/.timer en /etc/systemd/system/
     sudo systemctl daemon-reload && sudo systemctl enable --now zascarr*

4. GitHub: Settings -> Rename repository; luego:
     git remote set-url origin git@github.com:juanajok/zascarr.git

5. Ejecutar tests:
     pytest -x

6. grep final (solo deberían quedar: alembic/versions/, backups y dumps):
     grep -ri "secuenciarr" --exclude-dir=.git . | grep -v _dump_
===============================================================
""")

    if not (changed_files or renamed_paths):
        print("Ninguna referencia encontrada. ¿Ya estaba renombrado?")


if __name__ == "__main__":
    if DRY_RUN:
        print("MODO DRY-RUN: ningún fichero ha sido modificado.\n")
    main()
