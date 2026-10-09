# Cruce del tablero MIT con lo fusionado en `main` (2026-10-09)

> **Estado: propuesta documental.** No cambia estados, etiquetas ni comentarios
> del tablero ni de las issues #104–#135. Es una lectura de `main` en
> `fa91566` (merge de la PR #103) para que quien decida pueda mover tarjetas
> con datos delante.

## Cómo leer este documento

- **Cubierta** significa: hay código y pruebas en `main` que cumplen los
  criterios de la historia *en el alcance indicado*. **No** significa
  aceptada por quien revisa, ni desplegada, ni ensayada en la Raspberry Pi.
  Las migraciones 0018 y 0019 siguen sin aplicarse en producción.
- **Parcial** indica qué parte existe y qué evidencia falta.
- **Nueva** significa que no hay nada en `main` que la cubra.
- Las evidencias son PRs fusionadas y ficheros del repositorio. Nada de lo de
  este documento se ha comprobado contra fuentes reales ni en una Pi.

Resumen: **3 cubiertas** (todas de M2, con la salvedad de §2), **8 parciales**,
**13 nuevas**, sobre las 24 historias. Las 8 funcionalidades (M1–M8) heredan el
estado de sus historias.

## 1. Referencias que sostienen el cruce

| PR | Contenido | Límite explícito |
|---|---|---|
| #95 | `search_detallada`: `ok`, `apagada`, `sin_clave`, `error` | No distingue límite de uso |
| #96 | Cortesía compartida de Tebeosfera (`utils/cortesia.py`, redirecciones acotadas) | No se extiende a Comic Vine, AniList ni GCD |
| #97 | Alta de serie como servicio/API, comprobante `alta_operaciones` (migración 0018), deshacer | Sin interfaz ni caminos heredados |
| #98 | El enricher excluye cualquier identidad externa, incluido `gcd_id` | — |
| #101 | Vista previa de vinculación (solo lectura) | Sin interfaz ni confirmación |
| #102 | Contrato técnico de 2d | Documento |
| #103 | Vinculación (2d): transacción única, informe inmutable `vinculacion_operaciones` (migración 0019), `resultado_incierto`, token v2 | Sin interfaz (2e); migración sin aplicar en producción |

## 2. Historias

| Issue | Historia | Estado | Evidencia y lo que falta |
|---|---|---|---|
| #112 | M1-US01 Identificar entradas y garantías | Parcial | El ADR 0007 nombra los dos caminos que mueven archivos. Falta el inventario formal de UI, API y tareas |
| #113 | M1-US02 Centralizar decisiones de dominio | Parcial | Alta, vista previa y vinculación viven en servicios (#97, #101, #103). Los caminos heredados no delegan en ellos (ver §3) |
| #114 | M1-US03 Adaptar o retirar caminos heredados | Nueva | Requiere decisión de producto (§3) |
| #115 | M2-US01 Alinear límites productor/consumidor | Cubierta para vinculación | #103: `MAX_TOKEN_VINCULACION = 56021` calculado en el peor caso, con prueba de extremo a extremo de 100 archivos y conflictos. **Hueco separado:** candidata y alta usan `max_length=8000` sin calcular (ver §3) |
| #116 | M2-US02 Informar honestamente tras errores | Cubierta para vinculación | #103: respuesta preparada antes del commit; tras el commit un fallo da `503 resultado_incierto`, nunca «no se ha cambiado nada». Alta y deshacer no usan el mismo patrón |
| #117 | M2-US03 Probar recuperación y fronteras | Cubierta para vinculación y alta | Fallos inyectados por etapa, caducidad, purga y bloqueo en #97 y #103. No hay una matriz única entre operaciones |
| #118 | M3-US01 Descubrir o crear desde un grupo | Nueva | Es 2e. Los servicios ya cumplen los criterios de comportamiento; falta la interfaz |
| #119 | M3-US02 Revisar selección y números | Nueva | Idem: vista previa (#101) sin pantalla |
| #120 | M3-US03 Confirmar y resolver pendientes | Nueva | Idem: vinculación (#103) sin pantalla |
| #121 | M4-US01 Validar instalación y actualización | Nueva | Existen `update.sh`, `backup.sh`, `rollback.sh` e instalador. No se han ensayado con la cabeza actual ni con 0018/0019 |
| #122 | M4-US02 Medir coste operativo y esfuerzo | Nueva | Hay `scripts/medicion/medir_asignacion.*` y el benchmark del parser; no hay medición de la ruta nueva |
| #123 | M4-US03 Ensayar restauración y aceptación | Nueva | Sin ensayo en la Pi |
| #124 | M5-US01 Acordar vocabulario y modelo mínimo | Parcial | ADR 0003 y `benchmark-identidad-editorial.md`; sin reconciliar con la tarjeta |
| #125 | M5-US02 Elegir una publicación identificada | Nueva | Hoy `Issue` se identifica por serie y número; `volume` admite NULL. La vinculación trata los homónimos como `numero_ambiguo` y no elige |
| #126 | M5-US03 Migrar sin confundir recuentos | Nueva | — |
| #127 | M6-US01 Mostrar procedencia y bloqueo | Parcial | Los datos existen (`Series.metadata_["alta"]`, `File.metadata_["vinculo"]`, `locked_fields`, `metadata_source`); falta mostrarlos. #98 cerró un hueco con GCD |
| #128 | M6-US02 Previsualizar enriquecimiento | Nueva | El enricher aplica directamente: rellena huecos y no borra, pero no hay plan previo |
| #129 | M6-US03 Asociar otra fuente explícitamente | Nueva | #98 impide la asociación automática; la acción explícita no existe |
| #130 | M7-US01 Declarar el significado de una carpeta | Nueva | Solo hay señales de carpeta calculadas (rebanada 1) |
| #131 | M7-US02 Declarar una correspondencia local | Parcial | Existe el alias aprendido (B13), pero asigna sin preguntar; la tarjeta pide proponer sin ejecutar |
| #132 | M7-US03 Revisar y retirar decisiones reutilizables | Nueva | Sin pantalla ni API que liste los alias |
| #133 | M8-US01 Distinguir resultados y errores por capacidad | Parcial | #95 separa cuatro estados; falta el límite de uso |
| #134 | M8-US02 Compartir cortesía y política de peticiones | Parcial | #96 cubre Tebeosfera. Comic Vine, AniList y GCD siguen con espaciado por instancia |
| #135 | M8-US03 Validar cobertura española con evidencia | Nueva | Exige consultas reales, no autorizadas |

## 3. Decisiones abiertas antes de mover tarjetas

1. **Alcance de M2-US01 (#115).** El criterio puede leerse solo para la
   vinculación (cubierto) o para todos los tokens firmados. Los de candidata y
   alta tienen `max_length=8000` sin cálculo del peor caso. Con ASCII máximo
   miden 4 625 y 5 889; con caracteres de 4 bytes llegan a 14 625 y 15 889.
   Un texto largo no latino podría rechazarse siendo legítimo. Es una medición,
   no una incidencia reproducida con datos reales. Decidir: ¿entra en #115 o se
   abre aparte? Mientras no se decida, no se debería cerrar #115 sin esta nota.
2. **Caminos heredados (M1).** Dos siguen sin pasar por los servicios nuevos:
   el botón de «Por revisar» (`web/pendientes.py`) llama a
   `AsignacionService.asignar`, que **mueve** el archivo; y la creación desde
   Descubrir (`web/discovery.py`) usa `get_or_create_series`, sin las
   colisiones del alta. Decidir si se retiran, se adaptan o se renombran como
   «Organizar» (ADR 0007). Condiciona a 2e: el asistente nuevo convivirá con
   ellos.
3. **Alias aprendidos (M7-US02).** Hoy asignan automáticamente. La tarjeta
   pide proponer sin ejecutar; es un cambio de comportamiento, no de interfaz.

## 4. Sin tocar

Siguen sin autorización: 2e, aplicar 0018/0019 en producción, consultas a
fuentes reales, despliegue, cambios de parser, y organizar/reubicar
(rebanada 3). Este documento no los adelanta.
