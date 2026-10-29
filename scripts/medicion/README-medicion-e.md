# Medición E de #326 — herramienta de ventana

Herramienta de **solo medición**: no cambia la app, no escribe en la biblioteca
real y no escribe en el catálogo de producción. El plan y los presupuestos
están en #334; este directorio solo contiene el cómo.

## Piezas

- `preparar_sinteticos.py`: genera CBZ sintéticos (ruido determinista) en un
  directorio temporal, fuera de la biblioteca.
- `medir_registro_incremental_pi.py`: mide inventario y registro contra una BD
  `*_test_*`; la biblioteca debe estar montada en solo lectura. Modos:
  `seed`, `synthetic`, `search`, `register`.
- `ventana_e.sh`: orquesta las bases desechables, los sintéticos, las fases y
  la limpieza. `--dry-run` enseña el plan; `--yes` ejecuta.

## Uso

```bash
sudo bash scripts/medicion/ventana_e.sh --dry-run
sudo bash scripts/medicion/ventana_e.sh --yes
```

La ventana crea:

- `zascarr_medicion_sint_test_<TS>`: solo esquema, sin datos reales.
- `zascarr_medicion_ref_test_<TS>`: clon de producción, **solo lectura** para
  el medidor (transacción `READ ONLY`), usado en E3.
- `zascarr_medicion_reg_test_<TS>`: copia del clon, escribible, usada solo en
  E4. No es producción.
- Un directorio temporal en el mismo USB, **fuera** de la biblioteca, para los
  sintéticos.
- Resultados saneados en `/var/lib/zascarr/medicion-e/<TS>`; los `.err` pueden
  contener rutas y se quedan en la Pi, root-only.

Al terminar se borran las tres bases, el directorio sintético y los
contenedores. La biblioteca real solo se monta `:ro`.

## Reglas

- `pg_dump` de producción y `psql` de restauración usan el mismo usuario
  administrador de PostgreSQL.
- El medidor se conecta a los clones, nunca a la base de producción.
- `E3c` (cobertura) es independiente de `E3` (coste): si `ilegibles > 0`,
  E3c falla y E4 queda NOT RUN, aunque E3 haya cumplido el presupuesto.
- Si E1/E2 o E3 fallan el presupuesto, no se pasa al USB real.
- La guardia de «Registrar» no se toca: E no la levanta por sí sola; faltan
  los residuales 3 y 4 de #332.
