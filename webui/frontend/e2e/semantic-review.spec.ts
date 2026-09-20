import {test,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test('synthetic semantic workflow preserves blind labels and exact outbound preview',async({page})=>{
  const payload=JSON.stringify({model:'jev-1.13.0',state:{excerpt:'I focused on the tanks.',language:'en'},questions:{}});
  let labelsSubmitted=false;
  let submissions=0;
  const capture={id:'c',participant_id:null,condition:'LOW',execution_purpose:'practice',completion:'complete',
    block_instance_id:'b',manifest_sha256:'a'.repeat(64),capture_status:'reconciled',metrics:[],
    runs:[{id:'er',version:'1',status:'complete',reason:null}],
    manifest:{source_commit:'synthetic',scenario_sha256:'b'.repeat(64),profile_id:'synthetic',clocks:{}},
    reconciliation:{fingerprint:'c'.repeat(64),issues:[]}};
  await page.route('http://127.0.0.1:8331/**',async route=>{
    const url=new URL(route.request().url());
    let body:unknown={};
    if(url.pathname==='/capabilities')body={components:[{component_id:'matb-semantic-review'}]};
    else if(url.pathname==='/evidence/captures')body={total:0,items:[],offset:0,limit:25};
    else if(url.pathname==='/evidence/captures/c')body=capture;
    else if(url.pathname==='/inference/annotations')body={id:'n'};
    else if(url.pathname==='/inference/previews')body={id:'p',status:'queued'};
    else if(url.pathname==='/inference/previews/p')body={id:'p',status:'ready',preview_hash:'d'.repeat(64),payload,
      lineage:{payload_hash:'e'.repeat(64),exclusions_json:'[]',evidence_run_id:'er'}};
    else if(url.pathname==='/inference/runs' && route.request().method()==='POST'){
      submissions++;body={id:'r',job_id:'j',status:'queued',result_json:null};
    }else if(url.pathname==='/inference/runs/r/reviews'){
      labelsSubmitted=true;body={id:'review',activity:'blinded_reference'};
    }else if(url.pathname==='/inference/runs/r'){
      if(url.searchParams.get('include_answers')==='true')expect(labelsSubmitted).toBe(true);
      body={id:'r',job_id:'j',status:'valid',result_json:url.searchParams.get('include_answers')==='true'
        ?JSON.stringify({answers_json:'{"reported_task_tradeoff":{"type":"noul","noul":0.8}}',requested_model:'jev-1.13.0',resolved_model:'jev-1.13.0',raw_response_hash:'f'.repeat(64)}):null};
    }else if(url.pathname.startsWith('/station'))body={reservation:null,acquisitions:{},jobs:[],maintenance:false};
    await route.fulfill({json:body});
  });
  await page.goto('/evidence?capture=c');
  const panel=page.getByRole('region',{name:/Experimental semantic review|Revisión semántica experimental/});
  await expect(panel).toBeVisible();
  await panel.getByLabel(/Synthetic note|Nota sintética/).fill('I focused on the tanks.');
  await panel.getByRole('button',{name:/Create preview|Crear vista previa/}).click();
  await panel.getByRole('button',{name:/Refresh status|Actualizar estado/}).click();
  await expect(panel.getByText(payload,{exact:true})).toBeVisible();
  await panel.getByLabel(/^Reviewer$|^Revisor$/).fill('synthetic-rater');
  await panel.getByLabel(/Synthetic protocol authorization|Autorización del protocolo sintético/).fill('synthetic-only');
  await panel.getByLabel(/I reviewed this synthetic text|Revisé este texto sintético/).check();
  await panel.getByRole('button',{name:/Authorize and queue|Autorizar y poner en cola/}).click();
  const show=panel.getByRole('button',{name:/Show assessment|Mostrar evaluación/});
  await expect(show).toBeDisabled();
  await expect(panel.getByRole('button',{name:/Save labels|Guardar etiquetas/})).toBeDisabled();
  await panel.getByLabel(/Reported task tradeoff|Priorización declarada/).selectOption('present');
  await panel.getByLabel(/Automation belief|Expectativa de automatización/).selectOption('not_stated');
  await panel.getByLabel(/Instruction difficulty|Dificultad con instrucciones/).selectOption('unmentioned');
  await panel.getByRole('button',{name:/Save labels|Guardar etiquetas/}).click();
  await show.click();
  await expect(panel.getByText(/reported_task_tradeoff/)).toBeVisible();
  expect(submissions).toBe(1);
  await page.setViewportSize({width:390,height:844});
  await expect(panel).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  const accessibility=await new AxeBuilder({page}).include('section[aria-label="Experimental semantic review"], section[aria-label="Revisión semántica experimental"]').withTags(['wcag2a','wcag2aa']).analyze();
  expect(accessibility.violations).toEqual([]);
});
