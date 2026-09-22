import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const require=createRequire(path.join(root,'webui/frontend/package.json'));
const {chromium}=require('playwright');
const out=path.join(root,'EMAVI/video/capturas'); fs.mkdirSync(out,{recursive:true});
const mode=process.argv[2] || 'pvt';
const browser=await chromium.launch({channel:'chrome',headless:true});
const frame=mode==='scene'?{width:1920,height:1080}:{width:1600,height:900};
const context=await browser.newContext({viewport:frame,recordVideo:{dir:out,size:frame},extraHTTPHeaders:{Origin:'http://127.0.0.1:3118'}});
await context.addInitScript(()=>localStorage.setItem('matb-fac.locale','es-419'));
const page=await context.newPage(); page.setDefaultTimeout(20000);
const marks=[]; let t0=Date.now();
const mark=async(name)=>{marks.push({name,seconds:(Date.now()-t0)/1000,url:page.url()});console.log(name);await page.screenshot({path:path.join(out,mode+'-'+name+'.png')});};
const hold=ms=>page.waitForTimeout(ms);
async function go(url){await page.goto('http://127.0.0.1:3118'+url);await hold(1500);}
async function prepare(instrument){await page.locator('#'+instrument+'-participant').selectOption('P02');await page.getByLabel('Phase',{exact:true}).fill('EMAVI-video-'+Date.now());await page.getByRole('button',{name:'Preparar ocasión',exact:true}).click();await hold(700);}
try{
 await page.request.post('http://127.0.0.1:8018/participants',{data:{id:'P02',enrollment_date:'2026-09-21'}});
 if(mode==='pvt'){
  await go('/pvt?purpose=practice');await mark('preparar');await prepare('pvt');await hold(1800);
  await page.getByRole('button',{name:'Continuar a KSS',exact:true}).click();await hold(1400);await mark('kss');
  await page.getByRole('radio').nth(3).check();await hold(2200);
  await page.getByRole('button',{name:'Confirmar KSS y ver instrucciones PVT',exact:true}).click();await hold(1800);await mark('instrucciones');
  await page.getByRole('button',{name:'Estoy listo',exact:true}).click();await hold(1300);
  await page.getByRole('button',{name:/Iniciar.*PVT/}).click();await mark('prueba');
  const until=Date.now()+75000;let last=0;
  while(Date.now()<until){
   if(await page.getByText('KSS y PVT completadas',{exact:true}).isVisible().catch(()=>false))break;
   const text=await page.locator('main').innerText();
   // Respond through the visible input, never inject a timing/result payload.
   if(await page.locator('span.text-7xl').isVisible().catch(()=>false)&&Date.now()-last>700){await hold(200);await page.keyboard.press('Space');last=Date.now();}
   await hold(80);
  }
  await page.getByText('KSS y PVT completadas',{exact:true}).waitFor();await mark('completadas');await hold(6000);
 } else if(mode==='overview'){
  const pages=[['catalogo','/start'],['asignaciones','/study/assignments'],['participantes','/participants'],['estudios','/study'],['diseno','/experiments'],['openmatb','/openmatb/appearance'],['configuracion','/openmatb/settings'],['liftoff','/liftoff/setup?purpose=practice'],['polar','/physiology/polar-h10?purpose=practice'],['analisis','/analysis'],['evidencia','/evidence'],['estacion','/station']];
  for(const[name,url]of pages){await go(url);await mark(name);await hold(3500);await page.mouse.wheel(0,410);await hold(1800);await page.mouse.wheel(0,-410);await hold(1000);}
 } else if(mode==='evidence'){
  await go('/upload');await page.getByRole('combobox',{name:'Tipo de registro'}).selectOption('evidence');
  for(const role of ['capture_manifest','scenario_manifest','events','timing'])await page.locator('#evidence-'+role).setInputFiles(path.join(root,'EMAVI/construccion/runtime/synthetic-reference',role+'.upload'));
  await page.getByRole('button',{name:'Importar evidencia',exact:true}).click();await page.locator('button[data-metric=track_rmse_deviation]').waitFor({timeout:45000});
  await mark('metricas');await hold(3000);await page.locator('button[data-metric=track_rmse_deviation]').click();await hold(2500);
  await page.getByRole('button',{name:'track.sample · center_deviation',exact:true}).first().click();await hold(1700);await mark('evento');await hold(4500);
 } else if(mode==='scene'){
  await page.setViewportSize({width:1920,height:1080});await page.goto('http://127.0.0.1:3128/video/intro.html');await page.waitForFunction(()=>window.ready);await hold(1800);
  await page.screenshot({path:path.join(root,'EMAVI/video/portada.png')});await mark('intro');await hold(29000);
  fs.writeFileSync(path.join(root,'EMAVI/revision/metricas-3d.json'),JSON.stringify(await page.evaluate(()=>window.station.metrics()),null,2));
 } else if(mode==='mission'){
  const {seedStudyPvt}=await import('./runtime/video-helpers/fixtures.mjs');
  const participant='P18';await page.request.post('http://127.0.0.1:8018/participants',{data:{id:participant,enrollment_date:'2026-09-21'}});
  const attempt=await seedStudyPvt(page.request,participant,'e2e_area_search');
  await go('/mission/setup?purpose=study&attempt='+attempt);await mark('preparar');
  await page.getByRole('checkbox').check({force:true});await hold(1700);
  await page.getByRole('button',{name:/Preparar sesión/}).click();await page.waitForURL(/\/mission\?session=/,{timeout:60000});
  const sessionId=new URL(page.url()).searchParams.get('session');
  fs.writeFileSync(path.join(root,'EMAVI/construccion/runtime/recording-session.json'),JSON.stringify({sessionId,lease:await page.evaluate(id=>sessionStorage.getItem('matb.simulation.'+id+'.lease'),sessionId)}));
  for(const block of ['PRACTICE','LOW','MEDIUM','HIGH']){
   const start=page.getByRole('button',{name:/Iniciar bloque/i});await start.waitFor({timeout:45000});await mark(block);await hold(1500);await start.click();await hold(1400);
   const assigned=new Set();const until=Date.now()+300000;let complete=false;
   while(Date.now()<until){
    const d=page.getByRole('dialog');
    if(await d.isVisible().catch(()=>false)){
     const text=await d.innerText();await hold(1600);
     if(await d.locator('input[type="range"]').count()){
      await mark(block+'-escalas');const ranges=d.locator('input[type="range"]');
      for(let i=0;i<await ranges.count();i++){await ranges.nth(i).focus();await ranges.nth(i).press('Home');for(let j=0;j<4;j++)await ranges.nth(i).press('ArrowRight');await hold(150);}
      await d.getByRole('button').last().click();await d.waitFor({state:'hidden'});complete=true;break;
     }
     const radios=d.getByRole('radio');if(await radios.count()){await radios.nth(1).check({force:true});await d.getByRole('button').last().click();await hold(1100);}
    } else {for(const[id,n]of [['UAS-01',0],['UAS-02',1]]){if(assigned.has(id))continue;const row=page.getByRole('listitem',{name:new RegExp('^'+id+'\\b')});try{await row.getByRole('button').click({timeout:400});await page.getByRole('button',{name:/Asignar sector/i}).nth(n).click({timeout:400});assigned.add(id);}catch{break;}}}
    await hold(200);
   }
   if(!complete)throw new Error('Block did not reach post-block completion: '+block);
  }
  await page.getByRole('button',{name:/Finalizar sesión/i}).click();await hold(1000);
  await page.getByRole('button',{name:'Confirmar',exact:true}).click();
  await page.waitForURL(/\/mission\/debrief/,{timeout:90000});await hold(3000);await mark('debrief');await hold(5000);await page.mouse.wheel(0,580);await hold(4500);
 } else if(mode==='screen'){
  await go('/screen?purpose=practice');await prepare('screen');await mark('preparar');
  console.log((await page.locator('main').innerText()).slice(-1600));
  const begin=page.getByRole('button',{name:'Ver instrucciones y comenzar',exact:true});await begin.click();
  let lastTitle='',lastLetter='',letters=[],lastResponse=0;
  const until=Date.now()+210000;
  while(Date.now()<until){
   const h=await page.locator('h3').allTextContents();const title=h.join(' ');
   if(title&&title!==lastTitle){lastTitle=title;await mark('prueba-'+marks.length);await hold(2000);}
   const start=page.getByRole('button',{name:/^(Comenzar|Continuar)$/});
   if(await start.isVisible().catch(()=>false)){await start.click();await hold(500);continue;}
   if(await page.getByText(/Ha completado todas las pruebas/).isVisible().catch(()=>false)){await mark('final');break;}
   if(await page.getByText(/Resultados guardados|Práctica completada/).isVisible().catch(()=>false)){await mark('final');break;}
   const green=page.locator('div.h-24.w-24.bg-emerald-500');
   if(await green.isVisible().catch(()=>false)){await hold(240);await page.keyboard.press('Space');}
   const left=page.locator('svg.lucide-arrow-left[width="96"]'),right=page.locator('svg.lucide-arrow-right[width="96"]');
   if(await left.isVisible().catch(()=>false)){await hold(240);await page.keyboard.press('ArrowLeft');}
   if(await right.isVisible().catch(()=>false)){await hold(240);await page.keyboard.press('ArrowRight');}
   const letterNode=page.locator('span.text-8xl');const letter=await letterNode.count()?await letterNode.textContent():'';
   if(letter &&letter!==lastLetter){letters.push(letter);if(letters.length>=3&&letter===letters.at(-3)){await hold(230);await page.keyboard.press('Space');}lastLetter=letter;}
   if(!letter)lastLetter='';
   const dot=page.locator('div.pointer-events-none.rounded-full.bg-emerald-500');
   if(await dot.isVisible().catch(()=>false)){const b=await dot.boundingBox();if(b)await page.mouse.move(b.x+8,b.y+8,{steps:2});}
   await hold(80);
  }
  await mark('resultado');console.log((await page.locator('main').innerText()).slice(-1400));await hold(6000);
 }
}catch(e){await page.screenshot({path:path.join(out,mode+'-error.png')});fs.writeFileSync(path.join(out,mode+'-error.txt'),await page.locator('body').innerText());console.error(e);process.exitCode=1;}
finally{marks.push({name:'end',seconds:(Date.now()-t0)/1000});const video=page.video();await context.close();await video.saveAs(path.join(out,mode+'.webm'));fs.writeFileSync(path.join(out,mode+'-marcas.json'),JSON.stringify(marks,null,2));await browser.close();}
