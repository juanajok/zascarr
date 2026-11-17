# Dictamen OCTA-E3 — rastro de la aceptación del aviso legal

- **Estado:** dictamen del PO (2026-11-17).
- **Historia:** [#938](https://github.com/juanajok/zascarr/issues/938), épica OCTA-E [#918](https://github.com/juanajok/zascarr/issues/918).
- **Cambio de código:** ninguno.

## Situación actual

`legal_acknowledgments` guarda `id`, `accepted_at` y `legal_version`. `legal_version` es el
sha256 de `LEGAL.md`; si el aviso cambia, la aceptación anterior deja de valer sin tocar una
constante a mano (`services/legal.py`). No hay usuario porque ZascArr es de un solo operador y
la aceptación es única para el sistema.

## Dictamen

**Se mantiene el rastro actual.** Es suficiente para acreditar *qué versión del aviso* aceptó el
operador y *cuándo*, sin recoger datos personales innecesarios:

- no se añade IP, user-agent, correo ni identificador de dispositivo;
- no se añade una cadena de hashes ni una auditoría externa: no hay terceros ni multiusuario que
  lo justifiquen;
- la tabla es **append-only** por contrato de la app: no hay ruta que borre ni actualice
  aceptaciones; solo se insertan filas y se leen;
- `legal_version` cambia automáticamente con el hash de `LEGAL.md`, así que una edición del aviso
  invalida las aceptaciones anteriores.

## Límites honestos

- El registro prueba que **en esa instalación** se aceptó esa versión; no prueba la identidad de
  quien pulsó, porque no hay cuentas.
- Si en el futuro se añade multiusuario o acceso remoto con varias personas, este dictamen hay
  que revisarlo.

## Verificación

- `services/legal.py::acknowledge` solo inserta (`db.add`) y no borra.
- Las pruebas de `/api/legal/accept` y de la puerta legal siguen pasando.
- No se toca el esquema ni se necesita migración.
