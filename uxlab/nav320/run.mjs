/**
 * UXA-08b (#1205) — ronda 4: barra inferior a 320 px.
 *
 * Agentes sintéticos DETERMINISTAS (sin LLM): cada perfil recorre la ruta mínima
 * que ve en la barra. No simulan pulso, prisa ni errores humanos y NO sustituyen
 * la prueba con personas de docs/design/uxa08b-prueba-con-personas.md.
 *
 * Se ejecuta contra dos instancias aisladas de UXLab (A y B) con el mismo
 * fixture. No toca la Pi, la biblioteca real ni el catálogo.
 */
import { chromium } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = process.env.NAV320_OUT || path.join(HERE, 'out');
const A_URL = (process.env.NAV320_A_URL || 'http://app-a:8000').replace(/\/+$/, '');
const B_URL = (process.env.NAV320_B_URL || 'http://app-b:8000').replace(/\/+$/, '');
const TIMEOUT = Number(process.env.NAV320_TIMEOUT_MS || 15000);
const VARIANTS = { a: A_URL, b: B_URL };

const personas = JSON.parse(await readFile(path.join(HERE, 'personas.json'), 'utf8'));
const tasks = JSON.parse(await readFile(path.join(HERE, 'tasks.json'), 'utf8'));

await mkdir(path.join(OUT, 'capturas'), { recursive: true });

const taken = new Set();
async function shot(page, name) {
  if (taken.has(name)) return;
  taken.add(name);
  await page.screenshot({ path: path.join(OUT, 'capturas', name), animations: 'disabled' });
}

function clean(value) {
  return String(value ?? '').replace(/\s+/g, ' ').trim();
}

async function layout(page) {
  return page.evaluate(() => {
    const nav = document.querySelector('.nav');
    if (!nav) throw new Error('No hay barra de navegación');
    const rectOf = (el) => {
      const r = el.getBoundingClientRect();
      return {
        left: r.left, top: r.top, right: r.right, bottom: r.bottom,
        width: r.width, height: r.height,
      };
    };
    const visible = (el) => {
      const s = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
    };
    const items = [...nav.querySelectorAll('.nav-grupo .nav-enlace, .nav-mas > summary')]
      .filter(visible)
      .map((el) => {
        const textEl = el.querySelector('.nav-corto') || el.querySelector('.nav-texto') || el;
        const textRects = [...textEl.getClientRects()];
        const box = rectOf(el);
        return {
          tag: el.tagName.toLowerCase(),
          href: el.getAttribute('href'),
          label: (textEl.innerText || textEl.textContent || '').trim(),
          box,
          textLines: textRects.length,
          textOverflow: textEl.scrollWidth > textEl.clientWidth + 1,
          fontSize: getComputedStyle(textEl).fontSize,
        };
      });
    const details = nav.querySelector('details.nav-mas');
    const panel = details?.querySelector('.nav-mas-panel');
    const panelBox = panel && details.open ? rectOf(panel) : null;
    const viewport = { width: window.innerWidth, height: window.innerHeight };
    return {
      viewport,
      docScrollWidth: document.documentElement.scrollWidth,
      bodyScrollWidth: document.body.scrollWidth,
      horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth + 1,
      navBox: rectOf(nav),
      items,
      panelOpen: !!details?.open,
      panel: panelBox ? {
        ...panelBox,
        fitsViewport: panelBox.left >= 0
          && panelBox.right <= viewport.width + 1
          && panelBox.top >= 0
          && panelBox.bottom <= viewport.height + 1,
      } : null,
    };
  });
}

async function clickAndWait(page, locator, predicate) {
  await Promise.all([
    page.waitForURL(predicate, { timeout: TIMEOUT }),
    locator.click(),
  ]);
  await page.waitForLoadState('domcontentloaded');
}

function labelOf(state, href) {
  return state.items.find((item) => item.href === href)?.label || href;
}

function addLayoutDoubts(record, initial, panelState, variant, persona, task, targetVisible) {
  const doubts = record.doubts;
  if (initial.horizontalOverflow) {
    doubts.push('La página desborda a lo ancho en 320 px.');
  }
  const targetItem = initial.items.find((item) => item.href === task.targetHref);
  if (targetItem && targetItem.textLines > 1) {
    doubts.push(`La etiqueta «${targetItem.label}» ocupa ${targetItem.textLines} líneas en la barra a 320 px.`);
  }
  if (panelState?.panel && !panelState.panel.fitsViewport) {
    doubts.push('El panel «Más» no cabe entero en la pantalla.');
  }
  if (!targetVisible) {
    doubts.push(persona.role === 'reader'
      ? `No veo «${task.target}» en la barra; tengo que abrir «Más» y buscarlo.`
      : `«${task.target}» no está en la barra; lo busco en «Más».`);
  }
  if (variant === 'b' && task.id === 'estado') {
    doubts.push('No hay ninguna señal de Estado a la vista; «Más» no dice si algo falla.');
  }
  if (variant === 'a' && task.id === 'biblioteca' && persona.role === 'reader') {
    doubts.push('Biblioteca, lo que más uso, no está en la barra.');
  }
}

async function runSession(browser, variant, persona, task) {
  const base = VARIANTS[variant];
  const context = await browser.newContext({
    viewport: persona.viewport,
    isMobile: persona.isMobile,
    hasTouch: persona.touch,
    locale: 'es-ES',
    serviceWorkers: 'block',
    acceptDownloads: false,
  });
  context.setDefaultTimeout(TIMEOUT);
  context.setDefaultNavigationTimeout(TIMEOUT);
  const page = await context.newPage();
  const started = Date.now();
  const record = {
    variant,
    persona: persona.id,
    persona_name: persona.name,
    persona_role: persona.role,
    task: task.id,
    task_name: task.name,
    objective: task.objective,
    start_url: base + task.start,
    first_click: null,
    target_visible_in_bar: null,
    clicks_to_section: null,
    total_clicks: null,
    success: false,
    stop_reason: null,
    doubts: [],
    layout_initial: null,
    layout_panel: null,
    layout_section: null,
    elapsed_ms: null,
    error: null,
  };
  try {
    const response = await page.goto(base + task.start, { waitUntil: 'domcontentloaded' });
    if (!response || response.status() !== 200) {
      throw new Error(`inicio HTTP ${response?.status()}`);
    }
    await page.locator('.nav').waitFor({ state: 'visible' });
    await page.locator('#main').waitFor({ state: 'visible' });

    const initial = await layout(page);
    record.layout_initial = initial;
    await shot(page, `inicio-${variant}-${persona.id}.png`);

    const targetBar = page.locator(`.nav-grupo a.nav-enlace[href="${task.targetHref}"]`);
    const targetVisible = await targetBar.isVisible().catch(() => false);
    record.target_visible_in_bar = targetVisible;
    let panelState = null;

    if (targetVisible) {
      record.first_click = labelOf(initial, task.targetHref);
      record.clicks_to_section = 1;
      await clickAndWait(page, targetBar, (url) => url.pathname === task.sectionPath);
    } else {
      const summary = page.locator('.nav > details.nav-mas > summary');
      if (!(await summary.isVisible().catch(() => false))) {
        throw new Error('no se ve «Más» en la barra');
      }
      record.first_click = 'Más';
      record.clicks_to_section = 2;
      const details = page.locator('.nav > details.nav-mas');
      if (!(await details.evaluate((el) => el.open))) {
        await summary.click();
      }
      await page.locator('.nav > details.nav-mas[open]').waitFor({ timeout: TIMEOUT });
      panelState = await layout(page);
      record.layout_panel = panelState;
      await shot(page, `panel-${variant}-${task.id}.png`);

      const targetPanel = page.locator(`.nav-mas-panel a.nav-enlace[href="${task.targetHref}"]`);
      if (!(await targetPanel.isVisible().catch(() => false))) {
        record.stop_reason = 'target_not_visible_in_mas';
        record.doubts.push(`«${task.target}» no aparece en «Más».`);
        return record;
      }
      await clickAndWait(page, targetPanel, (url) => url.pathname === task.sectionPath);
    }

    if (task.id === 'biblioteca') {
      await page.locator('#rejilla').waitFor({ state: 'visible' });
      const card = page.locator('a.library-card').filter({
        has: page.locator('.library-card-title', { hasText: task.seriesTitle }),
      }).first();
      await card.waitFor({ state: 'visible' });
      record.layout_section = await layout(page);
      await shot(page, `biblioteca-${variant}.png`);
      await clickAndWait(page, card, (url) => url.pathname.startsWith('/ui/series/'));
      const body = await page.locator('body').innerText();
      record.total_clicks = record.clicks_to_section + 1;
      record.success = clean(body).includes(task.seriesTitle);
      if (!record.success) {
        record.stop_reason = 'series_detail_without_title';
        record.doubts.push('La ficha se abrió, pero no veo el título de la serie.');
      }
      await shot(page, `serie-${variant}.png`);
    } else {
      await page.locator('h1', { hasText: 'Estado' }).first().waitFor({ state: 'visible' });
      record.layout_section = await layout(page);
      record.total_clicks = record.clicks_to_section;
      record.success = new URL(page.url()).pathname === task.sectionPath;
      if (!record.success) record.stop_reason = 'estado_path_mismatch';
      await shot(page, `estado-${variant}.png`);
    }

    addLayoutDoubts(record, initial, panelState, variant, persona, task, targetVisible);
  } catch (error) {
    record.error = clean(error?.message || error).slice(0, 500);
    record.stop_reason = 'error';
  } finally {
    record.elapsed_ms = Date.now() - started;
    await context.close().catch(() => {});
  }
  return record;
}

function summaryMarkdown(sessions) {
  const lines = [
    '# UXA-08b · Ronda 4 a 320 px (agentes sintéticos)',
    '',
    'Generado por `uxlab/nav320/run.mjs`. **No es una prueba con personas ni vale para la aceptación de #1205.**',
    '',
    '| Perfil · variante | Tarea | Primer clic | Clics hasta la sección | Clics totales | Éxito | Dudas |',
    '|---|---|---|---:|---:|---:|---|',
  ];
  for (const s of sessions) {
    const doubts = s.doubts.length ? s.doubts.join(' ') : '—';
    lines.push(`| ${s.persona_name} · ${s.variant.toUpperCase()} | ${s.task_name} | ${s.first_click ?? '—'} | ${s.clicks_to_section ?? '—'} | ${s.total_clicks ?? '—'} | ${s.success ? 'Sí' : 'No'} | ${doubts} |`);
  }
  lines.push('', '## Barra a 320 px', '', '| Variante | Etiquetas visibles | Desborde horizontal | Etiquetas en 2 líneas | Panel «Más» |', '|---|---|---|---|---|');
  for (const variant of ['a', 'b']) {
    const sample = sessions.find((s) => s.variant === variant && s.layout_initial)?.layout_initial;
    if (!sample) continue;
    const labels = sample.items.map((item) => item.label).join(' · ');
    const wrapped = sample.items.filter((item) => item.textLines > 1).map((item) => item.label).join(', ') || '—';
    const panel = sessions.find((s) => s.variant === variant && s.layout_panel)?.layout_panel?.panel;
    const panelText = panel
      ? `${Math.round(panel.width)}×${Math.round(panel.height)} px, ${panel.fitsViewport ? 'cabe' : 'no cabe'}`
      : 'no se abrió';
    lines.push(`| ${variant.toUpperCase()} | ${labels} | ${sample.horizontalOverflow ? 'Sí' : 'No'} | ${wrapped} | ${panelText} |`);
  }
  lines.push('', `Sesiones: ${sessions.length} · Éxitos: ${sessions.filter((s) => s.success).length} · Errores: ${sessions.filter((s) => s.error).length}`, '');
  return lines.join('\n');
}

const browser = await chromium.launch();
const sessions = [];
try {
  for (const [variant, base] of Object.entries(VARIANTS)) {
    for (const persona of personas) {
      for (const task of tasks) {
        console.log(`Sesión ${variant.toUpperCase()} / ${persona.name} / ${task.name}`);
        const record = await runSession(browser, variant, persona, task);
        sessions.push(record);
        console.log(`  → ${record.success ? 'éxito' : 'sin éxito'} · ${record.stop_reason ?? 'ok'} · ${record.elapsed_ms} ms`);
      }
    }
  }
} finally {
  await browser.close().catch(() => {});
}

const result = {
  generated_at: new Date().toISOString(),
  git_sha: process.env.UXLAB_GIT_SHA || null,
  method: 'Agentes sintéticos deterministas (sin LLM) con Playwright; no es una prueba con personas ni vale para la aceptación de #1205.',
  viewport: { width: 320, height: 568 },
  variants: { a: A_URL, b: B_URL },
  personas,
  tasks,
  sessions,
};
await writeFile(path.join(OUT, 'resultado.json'), JSON.stringify(result, null, 2) + '\n');
await writeFile(path.join(OUT, 'resumen.md'), summaryMarkdown(sessions) + '\n');
console.log(`Informe: ${path.join(OUT, 'resultado.json')}`);
if (sessions.some((s) => s.error)) process.exitCode = 1;
