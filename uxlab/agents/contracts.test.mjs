import test from 'node:test';
import assert from 'node:assert/strict';
import { allowedRequest,publicUrl,accessibleText,validateAction } from './guards.mjs';
import { classify } from './oracles.mjs';

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
});

test('el oráculo separa éxito declarado de objetivo y registra falso éxito', () => {
  assert.deepEqual(classify({agentSaidDone:true,objectiveSuccess:false}),{
    declared_success:true, objective_success:false, false_success:true,
  });
  assert.equal(classify({agentSaidDone:false,objectiveSuccess:true}).false_success,false);
});
