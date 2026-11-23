import { appendFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { openBrowser, getObservation, act } from './browser.mjs';
import { DeepSeekFlash } from './deepseek.mjs';
import { checkGoal, classify } from './oracles.mjs';

const DEFAULT_SESSION_LIMIT_STEPS = 18;
const SESSION_LIMIT_STEPS = Number(process.env.UXLAB_MAX_STEPS || DEFAULT_SESSION_LIMIT_STEPS);
if (!Number.isInteger(SESSION_LIMIT_STEPS) || SESSION_LIMIT_STEPS < 1 || SESSION_LIMIT_STEPS > 60) {
  throw Error('UXLAB_MAX_STEPS debe ser un entero entre 1 y 60');
}
const SESSION_LIMIT_MS = 240_000;

function getConfig() {
  const personaId = process.env.UXLAB_PERSONA;
  const scenarioId = process.env.UXLAB_SCENARIO;
  const runId = process.env.UXLAB_RUN_ID;
  if (![personaId,scenarioId,runId].every(x => /^[a-zA-Z0-9_-]{1,48}$/.test(x || ''))) {
    throw Error('Configuración de sesión incompleta o insegura');
  }
  return {personaId,scenarioId,runId};
}
function digest(s) { return createHash('sha256').update(s).digest('hex').slice(0,12); }
const safeError = err => String(err?.message || err).replace(/sk-[a-zA-Z0-9_-]+/g, '[redactado]').slice(0,320);

async function main() {
  const {personaId,scenarioId,runId} = getConfig();
  const personas = JSON.parse(await readFile(new URL('./personas.json',import.meta.url),'utf8'));
  const scenarios = JSON.parse(await readFile(new URL('./scenarios.json',import.meta.url),'utf8'));
  const persona = personas.find(p => p.id === personaId);
  const scenario = scenarios.find(s => s.id === scenarioId);
  if (!persona || !scenario) throw Error('Identificador de perfil/escenario desconocido');
  const dir = path.resolve('results/agents',runId,scenarioId+'-'+personaId);
  await mkdir(path.join(dir,'screenshots'),{recursive:true});
  const eventsFile = path.join(dir,'steps.jsonl');
  const baseUrl = process.env.BASE_URL || 'http://app:8000';
  if (baseUrl !== 'http://app:8000') throw Error('Origen app inesperado: solo UXLab');
  const ds = new DeepSeekFlash({maxUSD:Number(process.env.DEEPSEEK_MAX_USD || '0.05'), maxCalls:SESSION_LIMIT_STEPS, maxInputTokens:Number(process.env.UXLAB_MAX_INPUT_TOKENS || '60000')});
  let infraError = false, started = Date.now(), finished = false, declared = false;
  let reason='max_steps', invalids=0, repeated=0, backtracks=0;
  let blocked = [], history = [], steps=0, everAchieved=false, helpRequests=0;
  let browser,ctx,page;
  let finalSuccess = false;
  try {
    await ds.init();
    ({browser,context:ctx,page} = await openBrowser(persona,baseUrl,blocked));
    await ctx.tracing.start({screenshots:true,snapshots:true,sources:false});
    const response = await page.goto(baseUrl+scenario.start,{waitUntil:'domcontentloaded'});
    if (!response || response.status() !== 200) throw Error('Página de inicio no disponible');
    let lastHash = '';
    for (let index=0; index<SESSION_LIMIT_STEPS; index++) {
      if (Date.now()-started > SESSION_LIMIT_MS) {reason='max_time';break;}
      const obs = await getObservation(page);
      await writeFile(path.join(dir,'screenshots','step-'+String(index+1).padStart(2,'0')+'.jpg'),obs.screenshot);
      steps++;
      let action, outcome='', error='';
      try {
        action = await ds.decide({
          screenshot:obs.screenshot,tree:obs.tree,url:obs.url,
          persona, objective:scenario.objective, history,
          timeout:Math.max(1000,Math.min(30000,SESSION_LIMIT_MS-(Date.now()-started))),
        });
        if (action.action === 'finish') {
          finished=true;
          declared=action.status==='done';
          if (action.status==='help') helpRequests++;
          reason='agent_'+action.status;
          outcome='finished';
        } else {
          if (action.action==='back') backtracks++;
          outcome=await act(page,action,persona);
          invalids=0;
          const next = await getObservation(page);
          const hash = digest(next.url+next.tree+next.focus);
          repeated = lastHash && hash===lastHash ? repeated+1 : 0;
          lastHash=hash;
          if (await checkGoal(page,scenario)) everAchieved=true;
        }
      } catch (err) {
        error=safeError(err);
        if (/^budget:/.test(error)) {reason=error;finished=true;}
        else if (/^deepseek_|fetch failed|abort|timeout|Clave API/.test(error)) {
          reason='infrastructure:'+error;
          infraError=true;
          finished=true;
        } else {
          invalids++;
          if (invalids>=3) {reason='invalid_action_limit';finished=true;}
        }
      }
      const record = {
        step:index+1, timeMs:Date.now()-started, url:obs.url,
        ariaHash:digest(obs.tree),
        screenshot:'screenshots/step-'+String(index+1).padStart(2,'0')+'.jpg',
        action:action || null, outcome, error,
      };
      history.push({action:action?.action || 'error',outcome,error});
      await appendFile(eventsFile,JSON.stringify(record)+'\n');
      if (finished) break;
      if (repeated>=2) { reason='navigation_loop';break; }
    }
    finalSuccess=await checkGoal(page,scenario);
  } catch(err) {
    reason='infrastructure:'+safeError(err);
    infraError=true;
  } finally {
    if (ctx) {
      try { await ctx.tracing.stop({path:path.join(dir,'trace.zip')}); }
      catch (err) { console.error('No se pudo guardar trace: '+safeError(err)); }
      await ctx.close().catch(()=>{});
    }
    if (browser) await browser.close().catch(()=>{});
    const summary = {
      scenario_id:scenario.id,persona_id:persona.id,profile:persona.name,
      started_at:new Date(started).toISOString(),
      ...classify({agentSaidDone:declared,objectiveSuccess:finalSuccess}),
      goal_reached_before_finish:everAchieved,steps,max_steps:SESSION_LIMIT_STEPS,
      elapsed_ms:Date.now()-started,backtracks, repeated_states:repeated,
      invalid_actions:invalids,blocked_requests:blocked.length,
      blocked_paths:blocked.slice(0,20),help_requests:helpRequests,
      stop_reason:reason,
      git_sha:process.env.UXLAB_GIT_SHA || null,
      fixture_version:'uxlab-fixtures-v1',
      model:ds.usage(),
      network_policy:'browser: internal only; orchestrator: DeepSeek API via egress',
      infrastructure_error:infraError,
    };
    await writeFile(path.join(dir,'session.json'),JSON.stringify(summary,null,2)+'\n');
    console.log(JSON.stringify({
      session:scenario.id+'/'+persona.id,success:finalSuccess,
      declared_success:declared,steps,reason,estimated_usd:summary.model.estimatedUSD,
      dir,
    }));
  }
  if (infraError) process.exitCode=2;
}

main().catch(err => {console.error('UXLab agent error: '+safeError(err));process.exitCode=2;});
