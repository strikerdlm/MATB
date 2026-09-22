import {buildSubtitles} from './build_subtitles.mjs';
import fs from 'node:fs';import path from 'node:path';import{fileURLToPath}from'node:url';import{spawnSync}from'node:child_process';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..'),base=path.join(root,'EMAVI/video'),build=path.join(root,'EMAVI/construccion/runtime/render');
const chapters=JSON.parse(fs.readFileSync(path.join(base,'chapters.json')));
const subtitleReport=buildSubtitles(base,chapters);
const output=path.join(root,'EMAVI/entregables/EMAVI_recorrido_es.mp4');const args=['-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',path.join(build,'concat.txt'),'-i',path.join(base,'subtitulos.srt'),'-i',path.join(build,'chapters.ffmeta'),'-map','0:v','-map','0:a','-map','1:0','-map_metadata','2','-c:v','copy','-c:a','copy','-c:s','mov_text','-metadata:s:s:0','language=spa','-metadata:s:a:0','language=spa','-movflags','+faststart',output];
const p=spawnSync('ffmpeg',args,{encoding:'utf8',windowsHide:true});if(p.status!==0)throw Error(p.stderr);const meta=spawnSync('ffprobe',['-v','error','-show_format','-show_streams','-show_chapters','-of','json',output],{encoding:'utf8',windowsHide:true}).stdout;fs.writeFileSync(path.join(root,'EMAVI/revision/ffprobe-video.json'),meta);
fs.writeFileSync(path.join(root,'EMAVI/revision/subtitulos.json'),JSON.stringify(subtitleReport,null,2));
console.log('Final MP4: '+output+'; '+JSON.parse(meta).format.duration+' seconds; '+subtitleReport.cues+' Spanish sentence cues');
