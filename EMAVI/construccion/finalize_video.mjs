import fs from 'node:fs';import path from 'node:path';import{fileURLToPath}from'node:url';import{spawnSync}from'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..'),base=path.join(root,'EMAVI/video'),build=path.join(root,'EMAVI/construccion/runtime/render');
const chapters=JSON.parse(fs.readFileSync(path.join(base,'chapters.json')));
const stamp=t=>{const ms=Math.round(t*1000);return `${String(Math.floor(ms/3600000)).padStart(2,'0')}:${String(Math.floor(ms/60000)%60).padStart(2,'0')}:${String(Math.floor(ms/1000)%60).padStart(2,'0')}.${String(ms%1000).padStart(3,'0')}`;};
const cues=[];
for(const c of chapters){const file=path.join(base,'audio',c.id+'.timing.json');const words=JSON.parse(fs.readFileSync(file,'utf8').replace(/^\uFEFF/,''));
 for(const w of words){if(w.sapi_audio_position_ms===undefined){w.sapi_audio_position_ms=w.start_ms;w.start_ms*=16000/22050;w.event_clock_hz=16000;w.wav_sample_rate=22050;}}
 fs.writeFileSync(file,JSON.stringify(words,null,2));let group=[];
 for(let i=0;i<words.length;i++){group.push(words[i]);const a=group[0].position,b=words[i].position+words[i].length;if(b-a>60||i===words.length-1){const start=c.start+.35+group[0].start_ms/1000,end=i+1<words.length?c.start+.35+words[i+1].start_ms/1000-.035:c.end-.45;if(end<=start||end>c.end)throw Error('Invalid caption timing '+c.id);cues.push({start,end,text:c.text.slice(a,b).trim()});group=[];}}
}
for(let i=1;i<cues.length;i++)if(cues[i].start<cues[i-1].end)throw Error('Overlapping captions');
fs.writeFileSync(path.join(base,'subtitulos.vtt'),'WEBVTT\n\n'+cues.map(c=>`${stamp(c.start)} --> ${stamp(c.end)}\n${c.text}\n`).join('\n'));
fs.writeFileSync(path.join(base,'subtitulos.srt'),cues.map((c,i)=>`${i+1}\n${stamp(c.start).replace('.',',')} --> ${stamp(c.end).replace('.',',')}\n${c.text}\n`).join('\n'));
const output=path.join(root,'EMAVI/entregables/EMAVI_recorrido_es.mp4');const args=['-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',path.join(build,'concat.txt'),'-i',path.join(base,'subtitulos.srt'),'-i',path.join(build,'chapters.ffmeta'),'-map','0:v','-map','0:a','-map','1:0','-map_metadata','2','-c:v','copy','-c:a','copy','-c:s','mov_text','-metadata:s:s:0','language=spa','-metadata:s:a:0','language=spa','-movflags','+faststart',output];
const p=spawnSync('ffmpeg',args,{encoding:'utf8',windowsHide:true});if(p.status!==0)throw Error(p.stderr);const meta=spawnSync('ffprobe',['-v','error','-show_format','-show_streams','-show_chapters','-of','json',output],{encoding:'utf8',windowsHide:true}).stdout;fs.writeFileSync(path.join(root,'EMAVI/revision/ffprobe-video.json'),meta);
fs.writeFileSync(path.join(root,'EMAVI/revision/subtitulos.json'),JSON.stringify({cues:cues.length,nonOverlapping:true,lastEnd:cues.at(-1).end,chapterEnd:chapters.at(-1).end,clockCheck:{test22kLastSeconds:29.016125,test16kLastSeconds:21.06,scale:16000/22050,normalized22kLastSeconds:29.016125*16000/22050}},null,2));
console.log('Final MP4: '+output+'; '+JSON.parse(meta).format.duration+' seconds; '+cues.length+' Spanish cues');
