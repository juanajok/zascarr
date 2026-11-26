# UXA-08b · Ronda 4 a 320 px (agentes sintéticos)

Comprueba la barra inferior del móvil a **320×568** con dos perfiles sintéticos
(Marta, lectora; Dani, operador del sistema) y las dos variantes de
`NAV_MOVIL_VARIANTE`:

- **A** (por defecto): Inicio · Revisar · Deseados · Estado · Más.
- **B** (prueba): Inicio · Revisar · Biblioteca · Deseados · Más.

**No es una prueba con personas y no vale para aceptar #1205.** Los agentes son
deterministas y sin LLM: recorren la ruta mínima que ven en la barra. No simulan
pulso, prisa, errores de puntería ni juicio humano. La prueba que decide sigue
siendo `docs/design/uxa08b-prueba-con-personas.md`.

## Qué mide

- Primer clic/toque y clics hasta la sección.
- Éxito al abrir la ficha de «Nebulosa de Papel» y al llegar a Estado.
- Desborde horizontal, etiquetas partidas en dos líneas y encaje del panel «Más»
  a 320 px.
- Dudas declaradas por el perfil sintético (texto guiado por lo que ve).

## Cómo se ejecuta

Requiere Docker y el Compose aislado de UXLab. **Nunca** se usa con el Compose de
producción. No publica puertos y no toca la Pi, la biblioteca real ni el catálogo.

```bash
export UXLAB_DB_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
export UXLAB_GIT_SHA="$(git rev-parse HEAD)"

docker compose -f uxlab/compose.uxlab.yml -f uxlab/compose.nav320.yml \
  down --volumes --remove-orphans
docker compose -f uxlab/compose.uxlab.yml -f uxlab/compose.nav320.yml \
  up -d --wait app-a app-b
docker compose -f uxlab/compose.uxlab.yml -f uxlab/compose.nav320.yml \
  run --rm --no-deps nav320
docker compose -f uxlab/compose.uxlab.yml -f uxlab/compose.nav320.yml \
  down --volumes --remove-orphans
```

El resultado queda en `docs/design/uxa08b-320/` (`resultado.json`, `resumen.md` y
`capturas/`). Las capturas y el JSON se pueden regenerar; no se editan a mano.

## Por qué no se usó el piloto DeepSeek

El piloto de `uxlab/agents/` exige una clave en
`uxlab/.secrets/deepseek_api_key` y no estaba disponible. Para no bloquear la
ronda ni enviar datos a un proveedor externo, se usó un agente determinista
local. La limitación se declara en el informe y en la documentación de #1205.
