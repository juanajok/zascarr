// Los criterios de éxito JAMÁS se envían a DeepSeek.
// Son datos de comprobación propios de Playwright y del catálogo fijo UXLab.
const TITLE_SCIFI = 'UXLAB-Nebulosa de Papel';

export async function checkGoal(page, scenario) {
  const path = new URL(page.url()).pathname;
  if (scenario.oracle === 'genre') {
    if (!/^\/ui\/series\/[0-9a-f-]{36}$/.test(path)) return false;
    const h1 = page.locator('.series-header h1');
    return await h1.count() === 1 && (await h1.innerText()).toLowerCase().includes(TITLE_SCIFI.toLowerCase());
  }
  if (scenario.oracle === 'resume') {
    if (!/^\/ui\/leer\/[0-9a-f-]{36}$/.test(path)) return false;
    const reader = page.locator('[data-lector]');
    if (await reader.count() !== 1) return false;
    return (await reader.getAttribute('data-pagina')) === '3' &&
      (await page.locator('#lector-contador').innerText()).includes('Página 3 de 6');
  }
  throw Error('Oráculo desconocido ' + scenario.oracle);
}

export function classify({agentSaidDone,objectiveSuccess}) {
  return {
    declared_success: Boolean(agentSaidDone),
    objective_success: Boolean(objectiveSuccess),
    false_success: Boolean(agentSaidDone && !objectiveSuccess),
  };
}
