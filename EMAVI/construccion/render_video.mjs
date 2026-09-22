import {buildSubtitles} from './build_subtitles.mjs';
import fs from 'node:fs';import path from 'node:path';import{fileURLToPath}from'node:url';import{createRequire}from'node:module';import{spawnSync}from'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..'),req=createRequire(path.join(root,'webui/frontend/package.json'));const {chromium}=req('playwright');
const base=path.join(root,'EMAVI/video'),caps=path.join(base,'capturas'),build=path.join(root,'EMAVI/construccion/runtime/render');fs.mkdirSync(build,{recursive:true});
const probe=file=>Number(spawnSync('ffprobe',['-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',file],{encoding:'utf8',windowsHide:true}).stdout.trim());
function ff(args){const p=spawnSync('ffmpeg',['-hide_banner','-loglevel','error','-y',...args],{encoding:'utf8',windowsHide:true,maxBuffer:8e6});if(p.status!==0)throw Error(p.stderr);}
const script=JSON.parse(fs.readFileSync(path.join(base,'guion.json'),'utf8'));let cursor=0;
const chapters=script.map(c=>{const audio=path.join(base,'audio',c.id+'.wav'),duration=Math.ceil((probe(audio)+1.1)*30)/30;const item={...c,start:cursor,end:cursor+duration,duration,audio};cursor+=duration;return item;});
fs.writeFileSync(path.join(base,'chapters.json'),JSON.stringify(chapters.map(({audio,...c})=>c),null,2));
buildSubtitles(base,chapters);
const browser=await chromium.launch({channel:'chrome',headless:true}),page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
const esc=t=>t.replaceAll('&','&amp;').replaceAll('<','&lt;');
for(let i=0;i<chapters.length;i++){
 const c=chapters[i],plate=path.join(build,c.id+'-plate.png');
 if(process.env.EMAVI_RENDER_ONLY&&!process.env.EMAVI_RENDER_ONLY.split(',').includes(c.id))continue;
 await page.setContent(`<html><head><meta charset="utf-8"><style>*{box-sizing:border-box}body{margin:0;width:1920px;height:1080px;background:#07111f;font-family:Arial;color:#eef4fa}.top{position:absolute;left:80px;right:80px;top:27px;display:flex;align-items:center;justify-content:space-between}h1{font-size:35px;font-weight:500;margin:0}.tag{font-size:13px;letter-spacing:2px;color:#e6bb69}.slot{position:absolute;left:192px;top:106px;width:1536px;height:864px;background:transparent;border-radius:8px;border:1px solid #31485b}.num{position:absolute;left:45px;top:145px;color:#e6bb69;font-size:72px;font-weight:300}.rail{position:absolute;left:88px;top:268px;width:1px;height:620px;background:#294053}.progress{width:3px;background:#e6bb69;height:${(i+1)/chapters.length*620}px}.points{position:absolute;top:1000px;left:192px;right:192px;display:flex;justify-content:space-between;gap:25px;font-size:21px;color:#d1dce6}.point{border-left:3px solid #e6bb69;padding-left:14px}.mark{position:absolute;right:54px;top:170px;writing-mode:vertical-rl;font-size:12px;letter-spacing:2px;color:#91a8bd}</style></head><body><div class="top"><h1>${esc(c.title)}</h1><div class="tag">EMAVI · PÚBLICO CLASIFICADO</div></div><div class="num">${String(i+1).padStart(2,'0')}</div><div class="rail"><div class="progress"></div></div><div class="slot"></div><div class="mark">${esc(c.stage.toUpperCase())} · DATOS DE DEMOSTRACIÓN</div><div class="points">${c.points.map(p=>`<div class="point">${esc(p)}</div>`).join('')}</div></body></html>`);
 await page.screenshot({path:plate});
 let source,start=0,end;
 if(c.source==='scene'){source=path.join(caps,'scene.webm');end=probe(source);}
 else{source=path.join(caps,c.source+'.webm');const marks=JSON.parse(fs.readFileSync(path.join(caps,c.source+'-marcas.json')));const index=marks.findIndex(m=>m.name===c.marker);if(index<0)throw Error('Missing captured chapter '+c.id);start=marks[index].seconds;end=marks[index+1].seconds;
 if(c.id==='cognitiva')end=marks.find(m=>m.name==='prueba-3').seconds;
 if(c.id==='memoria')end=marks.at(-1).seconds-1;
 if(c.id==='kss')end=marks.find(m=>m.name==='instrucciones').seconds-2.2;
 if(c.id==='carga')start=marks.find(m=>m.name==='HIGH-escalas').seconds;
 if(c.source==='mission'&&c.id==='carga')end=marks.find(m=>m.name==='debrief').seconds;
 if(c.source==='evidence')end=marks.at(-1).seconds-.2;
 if(c.source==='overview')end=start+3.5;
 if(c.id==='suas')end=start+1.75;
 if(c.id==='operar')end-=2.2;
 }
 const available=Math.max(.5,end-start),d=c.duration;const speed=available>d?available/d:1;
 const output=path.join(build,c.id+'.mp4');
 const scene=c.source==='scene';
 let filter=scene?`[0:v]trim=duration=${Math.min(available,d)},setpts=PTS-STARTPTS,scale=1920:1080,tpad=stop_mode=clone:stop_duration=${d},fps=30:start_time=0,setpts=PTS-STARTPTS,setsar=1,fade=t=in:st=0:d=0.35,fade=t=out:st=${d-.4}:d=0.4[v]`:`[0:v]trim=duration=${available},setpts=(PTS-STARTPTS)/${speed},scale=1536:864:flags=lanczos,tpad=stop_mode=clone:stop_duration=${d},fps=30,setsar=1[screen];[1:v]fps=30[plate];[plate][screen]overlay=192:106,fps=30:start_time=0,setpts=PTS-STARTPTS,fade=t=in:st=0:d=0.30,fade=t=out:st=${d-.35}:d=0.35[v]`;
 const extra=[];
 if(c.source==='evidence'){
  extra.push('-loop','1','-i',path.join(root,'EMAVI/capturas/07_evento_detalle.png'));
  filter=`[0:v]trim=duration=${available},setpts=PTS-STARTPTS,scale=1536:864:flags=lanczos,tpad=stop_mode=clone:stop_duration=${d},fps=30,setsar=1[screen];[1:v]fps=30[plate];[plate][screen]overlay=192:106[base];[3:v]scale=1536:864:force_original_aspect_ratio=decrease,pad=1536:864:(ow-iw)/2:(oh-ih)/2:color=0x07111f[event];[base][event]overlay=192:106:enable='gte(t,9)',fps=30:start_time=0,setpts=PTS-STARTPTS,fade=t=in:st=0:d=0.30,fade=t=out:st=${d-.35}:d=0.35[v]`;
 }
 const holdFile=c.source==='overview'?path.join(caps,'overview-'+c.marker+'.png'):c.id==='kss'?path.join(caps,'pvt-kss.png'):c.id==='operar'?path.join(root,'EMAVI/capturas/05_suas_detalle.png'):c.id==='carga'?path.join(caps,'mission-HIGH-escalas.png'):null;
 if(holdFile){
  const holdAt=c.id==='operar'?8:2;
  extra.push('-loop','1','-i',holdFile);
  filter=`[0:v]trim=duration=${Math.min(available,holdAt)},setpts=PTS-STARTPTS,scale=1536:864:flags=lanczos,tpad=stop_mode=clone:stop_duration=${d},fps=30,setsar=1[screen];[1:v]fps=30[plate];[plate][screen]overlay=192:106[base];[3:v]scale=1536:864:force_original_aspect_ratio=decrease,pad=1536:864:(ow-iw)/2:(oh-ih)/2:color=0x07111f[detail];[base][detail]overlay=192:106:enable='gte(t,${holdAt})',fps=30:start_time=0,setpts=PTS-STARTPTS,fade=t=in:st=0:d=0.30,fade=t=out:st=${d-.35}:d=0.35[v]`;
 }
 filter+=';[2:a]loudnorm=I=-18:TP=-1.5:LRA=11,adelay=350|350,apad[a]';
 ff(['-ss',String(start),'-i',source,'-loop','1','-i',plate,'-i',c.audio,...extra,'-filter_complex_threads','2','-filter_complex',filter,'-map','[v]','-map','[a]','-t',String(d),'-frames:v',String(Math.round(d*30)),'-c:v','libx264','-threads','4','-preset','veryfast','-crf','20','-pix_fmt','yuv420p','-r','30','-video_track_timescale','90000','-c:a','aac','-b:a','160k','-ar','48000',output]);
 console.log(`${i+1}/${chapters.length} ${c.id} ${d.toFixed(1)}s`);
}
await browser.close();
const list=path.join(build,'concat.txt');fs.writeFileSync(list,chapters.map(c=>`file '${path.join(build,c.id+'.mp4').replaceAll('\\','/')}'`).join('\n'));
const metadata=path.join(build,'chapters.ffmeta');fs.writeFileSync(metadata,';FFMETADATA1\ntitle=EMAVI - Recorrido MATB y ASTRA\ncomment=Publico Clasificado. Datos de demostracion.\n'+chapters.map(c=>`[CHAPTER]\nTIMEBASE=1/1000\nSTART=${Math.round(c.start*1000)}\nEND=${Math.round(c.end*1000)}\ntitle=${c.title}\n`).join(''));
const final=path.join(root,'EMAVI/entregables/EMAVI_recorrido_es.mp4');
ff(['-f','concat','-safe','0','-i',list,'-i',path.join(base,'subtitulos.srt'),'-i',metadata,'-map','0:v','-map','0:a','-map','1:0','-map_metadata','2','-c:v','copy','-c:a','copy','-c:s','mov_text','-metadata:s:s:0','language=spa','-metadata:s:a:0','language=spa','-movflags','+faststart',final]);
console.log('FINAL '+final+' '+probe(final)+' seconds');
