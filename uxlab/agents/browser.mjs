import { chromium } from '@playwright/test';
import { accessibleText, allowedRequest, publicUrl, validateAction } from './guards.mjs';

export async function openBrowser(persona, baseUrl, blocked) {
  let browser;
  let lastError;
  for (let intento = 0; intento < 10; intento++) {
    try {
      browser = await chromium.connect(process.env.PLAYWRIGHT_WS || 'ws://browser:3000/', {
        timeout:15000,
      });
      break;
    } catch (error) {
      lastError = error;
      await new Promise(resolve => setTimeout(resolve, 500));
    }
  }
  if (!browser) throw lastError || new Error('No se pudo conectar con el servidor Playwright');
  const context = await browser.newContext({
    viewport:persona.viewport,
    isMobile:persona.isMobile,
    hasTouch:persona.touch,
    locale:'es-ES',
    serviceWorkers:'block',
    acceptDownloads:false,
  });
  context.setDefaultTimeout(3500);
  context.setDefaultNavigationTimeout(10000);
  await context.route('**/*', async route => {
    const request = route.request();
    if (!allowedRequest(request.url(), request.method(), baseUrl)) {
      blocked.push({
        method:request.method(),
        path:publicUrl(request.url()),
        category:'request_blocked',
      });
      await route.abort('blockedbyclient');
      return;
    }
    await route.continue();
  });
  const page = await context.newPage();
  return { browser,context,page };
}

export async function getObservation(page) {
  const tree = await page.locator('body').ariaSnapshot();
  const focus = await page.evaluate(() => {
    const el = document.activeElement;
    if (!el) return '';
    return (el.tagName + ':' + (el.getAttribute('aria-label') || el.innerText || el.getAttribute('name') || '')).slice(0,160);
  });
  return {
    url:publicUrl(page.url()),
    tree:accessibleText(tree),
    focus,
    screenshot:await page.screenshot({type:'jpeg',quality:55,fullPage:false,animations:'disabled'}),
  };
}
async function findControl(page, a) {
  // `context` es una pista del modelo, no un selector: se busca en toda la página
  // y solo se acepta si hay una coincidencia única por nombre visible/accesible.
  const root = page.locator('body');
  const exact = root.getByRole(a.role, {name:a.name,exact:true});
  if (await exact.count() === 1) return exact;
  // El nombre accesible puede incluir un prefijo de estado (p. ej. «0 0% leído · …»).
  // Aceptar el título visible sólo si hay una coincidencia única; nunca elegir al azar.
  const all = root.getByRole(a.role);
  const total = await all.count();
  const norm = (value) => String(value).replace(/\s+/g, ' ').trim().toLowerCase();
  const wanted = norm(a.name);
  const matches = [];
  for (let i = 0; i < total; i++) {
    const candidate = all.nth(i);
    const label = (await candidate.getAttribute('aria-label')) ||
      (await candidate.innerText().catch(() => '')) || '';
    if (norm(label).includes(wanted)) matches.push(candidate);
  }
  if (matches.length === 1) return matches[0];
  if (matches.length === 0) {
    // Fallback final: controles nativos cuyo rol calculado no coincide con el
    // que el modelo dedujo de la captura (p. ej. <summary> «Filtros»).
    const porTexto = root.getByText(a.name, {exact:true});
    if (await porTexto.count() === 1) return porTexto;
  }
  throw Error('Control ausente o ambiguo: '+a.role+' «'+a.name+'» ('+matches.length+')');
}
export async function act(page, raw, persona) {
  const a = validateAction(raw,persona.mode);
  if (a.action === 'finish') return 'finish';
  if (a.action === 'wait') {
    await page.waitForTimeout(Number(a.value || 500));
    return 'wait';
  }
  if (a.action === 'back') {
    await page.goBack({waitUntil:'domcontentloaded', timeout:8000});
    return 'back';
  }
  if (a.action === 'scroll') {
    if (persona.mode === 'keyboard') {
      await page.keyboard.press(a.direction === 'down' ? 'PageDown' : 'PageUp');
    } else {
      await page.mouse.wheel(0,a.direction === 'down' ? 580 : -580);
    }
    await page.waitForTimeout(200);
    return 'scroll';
  }
  if (a.action === 'press') {
    await page.keyboard.press(a.value);
    await page.waitForTimeout(220);
    return 'press';
  }
  if (persona.mode === 'keyboard' && a.action === 'type') {
    const focused = page.locator('input:focus, textarea:focus');
    if (await focused.count() !== 1) throw Error('Foco actual no es campo editable');
    await page.keyboard.insertText(a.value);
    await page.waitForTimeout(600);
    return 'type';
  }
  const target = await findControl(page,a);
  if (!(await target.isVisible())) throw Error('Control no visible');
  if (a.action === 'click') await target.click({timeout:3500});
  else if (a.action === 'type') await target.fill(a.value,{timeout:3500});
  else if (a.action === 'select') {
    try { await target.selectOption({label:a.value},{timeout:3500}); }
    catch { await target.selectOption(a.value,{timeout:3500}); }
  } else throw Error('Acción no permitida');
  await page.waitForTimeout(a.action === 'type' ? 650 : 400);
  return a.action;
}
