import { test, expect, type Page } from '@playwright/test';

const TITLE = 'UXLAB-Nebulosa de Papel';
const DETECTIVE = 'UXLAB-El Caso del Lince';

async function openLibrary(page: Page) {
  const response = await page.goto('/ui/biblioteca?modo=gestion');
  expect(response?.status()).toBe(200);
  await expect(page.locator('#rejilla')).toBeVisible();
  await expect(page.getByRole('link', { name: TITLE, exact: true })).toBeVisible();
}

async function openFilters(page: Page) {
  const panel = page.locator('#panel-filtros');
  if (!(await panel.evaluate(el => (el as HTMLDetailsElement).open))) {
    await panel.locator('summary').click();
  }
  await expect(panel.locator('#f-tradition')).toBeVisible();
}

test('UX-01: encuentra ciencia ficción por etiquetas visibles', async ({ page }) => {
  await openLibrary(page);
  await openFilters(page);
  await page.locator('#f-etiquetas').fill('ciencia');
  const sug = page.locator('#sugerencias-etiquetas').getByRole('link', { name: 'Añadir' });
  await expect(sug).toBeVisible();
  await sug.click();
  await expect(page).toHaveURL(/etiquetas=cienciaficcion/);
  await expect(page.locator('#rejilla')).toContainText(TITLE);
  await expect(page.locator('#rejilla')).not.toContainText(DETECTIVE);
  await expect(page.locator('#filtros-activos')).toContainText('cienciaficcion');
});

test('UX-02: conserva tres filtros tras intercambios HTMX', async ({ page }) => {
  await openLibrary(page);
  await openFilters(page);
  await page.locator('#f-tradition').selectOption('american');
  await expect(page).toHaveURL(/tradition=american/);
  await page.locator('#f-publisher').selectOption({ label: 'UXLAB-Editorial Horizonte-nebula' });
  await expect(page).toHaveURL(/publisher_id=/);
  await page.locator('#f-leido').selectOption('leyendo');
  await expect(page).toHaveURL(/leido=leyendo/);
  const url = new URL(page.url());
  expect(url.searchParams.get('tradition')).toBe('american');
  expect(url.searchParams.get('publisher_id')).toBeTruthy();
  expect(url.searchParams.get('leido')).toBe('leyendo');
  await expect(page.locator('#filtros-activos .filtro-activo')).toHaveCount(3);
  await expect(page.locator('#rejilla')).toContainText(TITLE);
  await expect(page.locator('#rejilla')).not.toContainText(DETECTIVE);
});

test('UX-03: abre portada HD, cierra y recupera foco', async ({ page }) => {
  await openLibrary(page);
  const button = page.getByRole('link', { name: 'Ver portada ampliada de ' + TITLE });
  await button.click();
  const dialog = page.locator('#visor-portada');
  await expect(dialog).toBeVisible();
  await expect(dialog.locator('img')).toHaveAttribute('src', /portada-hd\.jpg/);
  await expect(dialog).toContainText(TITLE);
  await dialog.getByRole('button', { name: 'Cerrar el visor' }).click();
  await expect(dialog).not.toBeVisible();
  await expect(button).toBeFocused();
});

test('UX-04: Escaparate permite continuar en página guardada', async ({ page }) => {
  await page.goto('/ui/biblioteca?modo=escaparate');
  const card = page.locator('.escaparate-bloque')
    .filter({ has: page.locator('#escaparate-continuar') })
    .getByRole('link', { name: /Nebulosa de Papel/ });
  await expect(card).toBeVisible();
  await card.click();
  const resume = page.getByRole('link', { name: /Continuar.*pág\. 3/ });
  await expect(resume).toBeVisible();
  await resume.click();
  await expect(page.locator('[data-lector]')).toHaveAttribute('data-pagina', '3');
  await expect(page.locator('#lector-contador')).toContainText('Página 3 de 6');
});

test('UX-05: busca por autor y por personaje usando sugerencias', async ({ page }) => {
  await openLibrary(page);
  await openFilters(page);
  await page.locator('#f-autor').fill('Ada Solís');
  const author = page.locator('#resultados-autor').getByRole('link', { name: 'Ada Solís' });
  await expect(author).toBeVisible();
  await author.click();
  await expect(page).toHaveURL(/author_id=/);
  await expect(page.locator('#rejilla')).toContainText(TITLE);

  await openLibrary(page);
  await openFilters(page);
  await page.locator('#f-personaje').fill('Detective Lince');
  const character = page.locator('#resultados-personaje').getByRole('link', { name: 'Detective Lince' });
  await expect(character).toBeVisible();
  await character.click();
  await expect(page).toHaveURL(/character_id=/);
  await expect(page.locator('#rejilla')).toContainText(DETECTIVE);
  await expect(page.locator('#rejilla')).not.toContainText(TITLE);
});

test('UX-06: favorita persiste tras recargar y permite deshacer', async ({ page }) => {
  await openLibrary(page);
  const favorite = page.locator('.library-card-wrap')
    .filter({ has: page.getByRole('link', { name: TITLE, exact: true }) })
    .locator('button.favorito-btn');
  await expect(favorite).toHaveAttribute('aria-pressed', 'false');
  await favorite.click();
  await expect(favorite).toHaveAttribute('aria-pressed', 'true');
  await page.reload();
  await expect(favorite).toHaveAttribute('aria-pressed', 'true');
  await favorite.click();
  await expect(favorite).toHaveAttribute('aria-pressed', 'false');
  await page.reload();
  await expect(favorite).toHaveAttribute('aria-pressed', 'false');
});
