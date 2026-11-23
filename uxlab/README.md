# ZascArr UX Lab — POC L1 (Playwright determinista)

Laboratorio **aislado** para pruebas funcionales reproducibles. No modifica la instalación ni la biblioteca de producción.

## Estado de esta POC

- Compose autónomo `zascarr-uxlab` con red Docker `internal`, sin puertos publicados.
- PostgreSQL y volúmenes exclusivos, con contraseña aleatoria por ejecución.
- Migraciones existentes de ZascArr y semilla ORM con cuatro series inventadas y archivos CBZ de seis páginas generados localmente.
- Seis escenarios que comprueban comportamiento real en desktop y móvil.
- Resultados JSON, HTML y trazas en `uxlab/results/`.
- **Aún no hay agentes LLM ni SSR**: se incorporarán después de validar la base determinista.

## Ejecución

Requisitos: Docker Engine + Compose v2 y Python 3. Desde la raíz de una copia de este repositorio:

```bash
bash uxlab/run.sh                 # pasada funcional (12 casos)
bash uxlab/run.sh --stability     # 3 pasadas por caso (36 ejecuciones)
# Opcional: 1..10 repeticiones
bash uxlab/run.sh --repeat-each 5
```

El script inicializa una contraseña efímera, borra solo los volúmenes del proyecto `zascarr-uxlab` antes/después de ejecutar y conserva los informes en `uxlab/results/`. La ruta es distinta del Compose normal. No se emplean `HOST_LIBRARY_DIR`, `ZASCARR_DATA_DIR` ni credenciales de la aplicación instalada.

El resumen agregado se guarda en `uxlab/results/stability-summary.md` y `.json`, además del informe HTML/JSON de Playwright. El script restaura la propiedad del árbol `results/` al UID/GID del usuario que invoca el script, también en caso de error, mediante BusyBox sin red y con la única capacidad `CHOWN`. Si Docker rootless o un montaje remoto impiden cambiar el propietario, se emite un error y se conserva el diagnóstico.

**No mezclar** `docker-compose.yml` de producción con `uxlab/compose.uxlab.yml`. El laboratorio se inicia por separado.

## Diagnóstico si falla la preparación

Si el contenedor `seed` termina con código 1, no significa que falle Playwright ni que el portátil no sea apto. `uxlab/run.sh` recoge **antes de limpiar** los logs y el estado de los servicios en:

- `uxlab/results/bootstrap.log` (errores y traceback de `seed`, PostgreSQL y app).
- `uxlab/results/compose-ps.txt` (estado de los contenedores).

Ejecutar de nuevo después de actualizar la rama y consultar `bootstrap.log`. El traceback indica si ha fallado Alembic, la inserción de fixtures o los permisos. No se recomienda inferir la causa solo a partir de `service "seed" didn't complete successfully: exit 1`.

## Escenarios y oráculos

| ID | Comprobación determinista |
| --- | --- |
| UX-01 | Buscar ciencia ficción por etiqueta y abrir resultados correctos |
| UX-02 | Combinar tradición, editorial y lectura; preservar URL, chips y resultados |
| UX-03 | Abrir portada HD y cerrar con restauración del foco |
| UX-04 | Continuar desde Escaparate hasta la página 3 del lector |
| UX-05 | Buscar por autor y por personaje; validar enlaces y resultado |
| UX-06 | Marcar favorita, recargar y comprobar persistencia; deshacer |

Nota: ZascArr dispone de géneros en sus metadatos pero no expone un selector específico de «género» en el panel de biblioteca; UX-01 usa etiquetas sin afirmar que ambos conceptos sean equivalentes. La evaluación de *descubribilidad* se reserva a los agentes y usuarios reales.

## Seguridad y datos

- El catálogo y las portadas son 100% sintéticos. Los CBZ contienen PNG creados por el script.
- La base no se exporta ni publica a la red. Los contenedores no tienen salida a Internet a través de la red `internal`.
- No se montan `/var/lib/zascarr`, `/media/DiscoDuro` ni carpetas de bibliotecas reales.
- No se habilitan integraciones de descarga externas.
- La semilla se detiene si encuentra el registro centinela: no reutiliza deliberadamente una base de una ejecución previa.
- Evitar ejecutar otro proyecto Compose con el nombre `zascarr-uxlab` en el mismo daemon.

## Interpretación de fallos

Una prueba fallida puede significar fallo real de UX, incompatibilidad de fixture o fallo del entorno. Revisar siempre trazas y registros antes de abrir un issue.

**Evidencia de primera ejecución:** un portátil Linux ejecutó satisfactoriamente los 12 casos, sin fallos ni omitidos, según el resumen compartido por el operador. **Una sola pasada no permite afirmar estabilidad**; para medir intermitencias se ha añadido el modo `--stability`. `0 flaky` en una ejecución y `0 intermitentes` en tres repeticiones son evidencias diferentes, pero ninguna demuestra ausencia permanente de fallos. No se han ejecutado los contenedores desde este entorno de autoría.

## Próximas iteraciones

1. Completar y revisar `bash uxlab/run.sh --stability` y comprobar los propietarios con `stat -c '%U:%G %n' uxlab/results/results.json`.
2. Implementar únicamente los dos escenarios y tres perfiles del piloto de agentes descrito en la SPEC de fase 2.
3. Añadir análisis SSR offline con anclas en español y versiones registradas **después del piloto**.
4. Calibrar contra pruebas humanas y crear un dashboard comparativo por commit.
