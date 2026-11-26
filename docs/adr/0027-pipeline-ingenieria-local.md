# ADR 0026 — Pipeline de ingeniería local y separado de ZascArr

**Estado:** aceptado para piloto acotado; no sustituye las puertas de fusión o despliegue.
**Contexto:** necesitamos comprobar de forma independiente propuestas de ingeniería, sin instalar un runtime de agentes en la Pi y sin hacer depender QA del proveedor de IA. Véase la [SPEC y comparación](<../design/agentic-mvp.md>).

**Decisión:** adaptar Git, el patrón de checkpoint y Docker local. El núcleo Python posee estados, decisiones, presupuesto, almacenamiento y gates. Los agentes reciben sobres de datos y emiten JSON sin autoridad sobre estado. El manifiesto y el runner no se modifican desde respuestas de agentes. Un Git privado produce candidatos de texto delimitados con hash reproducible; nunca se escribe en la rama origen. Los controles deterministas y la revisión independiente se vinculan al mismo SHA, SPEC y política. El estado se mantiene en el puesto de trabajo o CI con atomicidad y un escritor, no en PostgreSQL de ZascArr ni en un servicio nuevo.

**Consecuencias:** no hay coste de RAM o dependencias en el runtime de la aplicación. El proyecto aporta oráculos y retiene la autoridad sobre permisos, datos y fusiones. La portabilidad del contrato no garantiza que los adaptadores tengan idéntico aislamiento. El adaptador DSH del piloto es supervisado; no procesa repos privados hasta verificar un perfil con herramientas restringidas de verdad y autorizar la transferencia. Docker es opcional y solo confía en imagen, daemon y manifiesto del operador. El proyecto pierde automatización para operaciones que no se pueden controlar con este MVP.

**Revisar cuando:** se necesiten varios hosts, pruebas de aplicaciones complejas en red aislada, workers autenticados, presupuestos reales, o snapshots de repos grandes. Una necesidad demostrada podrá justificar un runtime orquestador existente. Hasta entonces no añadir un broker, base externa o dependencia al producto.
