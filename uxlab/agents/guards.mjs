// Barreras de seguridad: acciones de nombre accesible, nunca selectores ni rutas.
const ROLES = new Set(['link','button','textbox','searchbox','combobox','checkbox','radio','tab','option']);
const TYPES = new Set(['click','type','select','scroll','back','wait','press','finish']);
const KEYS = new Set(['Tab','Shift+Tab','Enter','Space','Escape','ArrowUp','ArrowDown','ArrowLeft','ArrowRight','PageDown','PageUp']);
const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi;

export function publicUrl(raw) {
  const url = new URL(raw);
  return url.pathname
    .replace(UUID, ':id')
    .replace(/\/[0-9a-f]{24,}(?=\/|$)/ig, '/:id')
    .replace(/\/[0-9a-f]{8,}(?=\/|$)/ig, '/:id');
}

export function accessibleText(tree) {
  // Además de sanear la URL, ningún UUID ni URL completa llega al modelo.
  return String(tree).replace(UUID, '[id]').replace(/https?:\/\/[^\s"')]+/g, '[enlace]').slice(0, 11500);
}

export function allowedRequest(raw, method, appOrigin='http://app:8000') {
  let url;
  try { url = new URL(raw); } catch { return false; }
  if (url.origin !== new URL(appOrigin).origin) return false;
  const path = url.pathname;
  const m = method.toUpperCase();
  if (m === 'GET' || m === 'HEAD') return /^\/(ui(?:\/|$)|static\/|api\/health$)/.test(path);
  if (m !== 'POST') return false;
  return /^\/ui\/series\/[0-9a-f-]{36}\/vista$/.test(path) ||
         /^\/ui\/leer\/[0-9a-f-]{36}\/(progreso|sentido)$/.test(path);
}
function short(v, max=140) { return typeof v === 'string' && v.length <= max; }
export function validateAction(a, mode) {
  if (a === null || typeof a !== 'object' || Array.isArray(a) || !TYPES.has(a.action)) {
    throw Error('Acción fuera de whitelist');
  }
  const { action, role='', name='', value='', context='', direction='', status='', reason='' } = a;
  if (![role,name,value,context,direction,status,reason].every(x=>short(x))) throw Error('Campos inválidos');
  if (mode === 'keyboard' && !['press','type','wait','finish','back','scroll'].includes(action)) {
    throw Error('Perfil teclado: prohibida interacción con ratón o clic');
  }
  if (action === 'finish' && !['done','blocked','help'].includes(status)) throw Error('Estado final inválido');
  if (action === 'click' || action === 'type' || action === 'select') {
    if (mode !== 'keyboard' || action === 'click' || action === 'select') {
      if (!ROLES.has(role) || !name.trim()) throw Error('Falta rol y nombre accesible');
    }
  }
  if (action === 'select' && role !== 'combobox') throw Error('Solo se puede seleccionar un combobox');
  if (action === 'press' && (mode !== 'keyboard' || !KEYS.has(value))) throw Error('Tecla no permitida');
  if (action === 'scroll' && !['up','down'].includes(direction)) throw Error('Desplazamiento no permitido');
  if (action === 'wait' && value && !/^(250|500|750|1000)$/.test(value)) throw Error('Espera fuera de rango');
  if (action === 'type' && !value) throw Error('Texto vacío');
  return {action,role,name,value,context,direction,status,reason};
}
