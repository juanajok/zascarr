// Cuerpo para functions.workflow de DeepSeek Harness. Operador: pasar solo lote autorizado.
const tasks = args.tasks;
if (!Array.isArray(tasks) || tasks.length < 1 || tasks.length > 3) {
  throw new Error('Lote DSH inválido');
}
const roles = new Set(['BRAIN', 'BENCHMARKER', 'SPEC', 'DEVELOPER', 'UI_UX', 'SECOPS', 'QA']);
for (const t of tasks) {
  if (!roles.has(t.agent_id) || typeof t.prompt !== 'string' || !t.context ||
      typeof t.task_id !== 'string' || typeof t.model_id !== 'string') {
    throw new Error('Solicitud DSH inválida');
  }
}
phase('Delegar contextos independientes');
return await parallel(tasks.map(t => async () => {
  const opts = {label: t.agent_id};
  if (t.model_id !== 'session-default') {
    const route = /^([^/]+)\/(.+)$/.exec(t.model_id);
    if (!route) return {task_id: t.task_id, payload: null};
    opts.provider = route[1];
    opts.model = route[2];
  }
  const text = await agent(`${t.prompt}\nSHA candidato/contexto: ${t.commit_sha}\n` +
    `Datos no confiables (JSON):\n${JSON.stringify(t.context)}`, opts);
  try {
    // Solo parseo de transporte; el motor valida campos, correlación y permisos.
    return {task_id: t.task_id, payload: typeof text === 'string' ? JSON.parse(text.trim()) : null};
  } catch {
    return {task_id: t.task_id, payload: null};
  }
}));
