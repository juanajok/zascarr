import test from 'node:test';
import assert from 'node:assert/strict';
import { allowedRequest,publicUrl,accessibleText,validateAction } from './guards.mjs';
import { classify } from './oracles.mjs';
import { DeepSeekFlash } from './deepseek.mjs';
import { readFileSync } from 'node:fs';

test('el agente nunca recibe UUID, query ni fragmentos de URL', () => {
  const url = publicUrl('http://app:8000/ui/series/123e4567-e89b-12d3-a456-426614174000?author_id=secret#fragment');
  assert.equal(url,'/ui/series/:id');
  assert.equal(accessibleText('id 123e4567-e89b-12d3-a456-426614174000'), 'id [id]');
});

test('ninguna petición del navegador accede a API DeepSeek o a otro dominio', () => {
  assert.equal(allowedRequest('https://api.deepseek.com/chat/completions','POST'),false);
  assert.equal(allowedRequest('http://app:8000/ui/biblioteca','GET'),true);
  assert.equal(allowedRequest('http://app:8000/ui/series/123e4567-e89b-12d3-a456-426614174000/retirar','POST'),false);
  assert.equal(allowedRequest('http://app:8000/ui/leer/123e4567-e89b-12d3-a456-426614174000/progreso','POST'),true);
  assert.equal(allowedRequest('http://app:8000/api/admin','DELETE'),false);
});

test('teclado rechaza clic y pulsaciones fuera de whitelist', () => {
  assert.throws(()=>validateAction({action:'click',role:'link',name:'Continuar'},'keyboard'));
  assert.throws(()=>validateAction({action:'press',value:'Control+L'},'keyboard'));
  assert.equal(validateAction({action:'press',value:'Tab'},'keyboard').action,'press');
  assert.throws(()=>validateAction({action:'goto',url:'/ui/leer/UUID'},'mouse'));
  assert.equal(validateAction({action:'finish',status:'done',reason:'x'.repeat(300)},'mouse').reason.length,300);
});

test('el oráculo separa éxito declarado de objetivo y registra falso éxito', () => {
  assert.deepEqual(classify({agentSaidDone:true,objectiveSuccess:false}),{
    declared_success:true, objective_success:false, false_success:true,
  });
  assert.equal(classify({agentSaidDone:false,objectiveSuccess:true}).false_success,false);
});

test('el foco se sanea y el contexto no se usa como selector', () => {
  assert.equal(accessibleText('A:serie 123e4567-e89b-12d3-a456-426614174000'), 'A:serie [id]');
  assert.equal(validateAction({action:'click',role:'link',name:'Abrir',context:'fila 2'},'mouse').context, 'fila 2');
});

test('presupuesto por defecto coherente y modelo permitido', () => {
  const compose = readFileSync(new URL('../compose.agents.yml', import.meta.url), 'utf8');
  assert.match(compose, /DEEPSEEK_MAX_USD: \$\{DEEPSEEK_MAX_USD:-0\.05\}/);
  delete process.env.DEEPSEEK_MODEL;
  assert.equal(new DeepSeekFlash({maxUSD:0.05}).model, 'deepseek-flash');
});
