import { chromium } from '@playwright/test';
import { accessibleText, allowedRequest, publicUrl, validateAction } from './guards.mjs';

export async function openBrowser(persona, baseUrl, blocked) {
  const browser = await chromium.connect(process.env.PLAYWRIGHT_WS || 'ws://browser:3000/', {
    timeout:15000,
  });
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
  return {
    url:publicUrl(page.url()),
    tree:accessibleText(tree),
    screenshot:await page.screenshot({type:'jpeg',quality:55,fullPage:false,animations:'disabled'}),
  };
}
function findControl(page, a) {
  const root = a.context
    ? page.getByRole('listitem').filter({hasText:a.context})
    : page.locator('body');
  return root.getByRole(a.role, {name:a.name,exact:true});
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
    const focused = page.locator(':focus');
    if (await focused.count() !== 1) throw Error('No hay campo enfocado');
    const tag = await focused.evaluate(el=>el.tagName.toLowerCase());
    if (!['input','textarea'].includes(tag)) throw Error('Foco actual no es campo editable');
    await page.keyboard.insertText(a.value);
    await page.waitForTimeout(600);
    return 'type';
  }
  const target = findControl(page,a);
  const count = await target.count();
  if (count !== 1) throw Error('Control ausente o ambiguo: '+a.role+' «'+a.name+'» ('+count+')');
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
