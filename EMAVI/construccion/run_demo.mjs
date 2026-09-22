import {spawn} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const runtime=path.join(root,'EMAVI/construccion/runtime');
fs.mkdirSync(runtime,{recursive:true});
const env={...process.env,PYTHONDONTWRITEBYTECODE:'1',PYTHONUTF8:'1',MATB_DB_PATH:path.join(runtime,'emavi-demo.sqlite'),MATB_SIMULATION_OUTPUT_DIR:path.join(runtime,'exports'),MATB_SIMULATION_SCENARIO_DIR:path.join(root,'tests/suas/fixtures'),MATB_SIMULATION_TEST_MODE:'1',MATB_SIMULATION_WALL_TIME_SCALE:process.env.MATB_SIMULATION_WALL_TIME_SCALE||'1',MATB_GEOGRAPHY_DIR:path.join(runtime,'geography'),MATB_NEXT_DIST_DIR:'.next/emavi',MATB_BACKEND_PORT:'8018',MATB_FRONTEND_ORIGINS:'http://127.0.0.1:3118',NEXT_TELEMETRY_DISABLED:'1'};
const children=[];
function start(exe,args,cwd,name){const log=fs.openSync(path.join(runtime,name+'.log'),'a'); const p=spawn(exe,args,{cwd,env,windowsHide:true,stdio:['ignore',log,log]}); children.push(p); console.log(name+' PID '+p.pid);}
start(process.env.MATB_PYTHON || 'C:/Users/User/Miniconda3/envs/matb/python.exe',['-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8018'],path.join(root,'webui/backend'),'backend');
start(process.execPath,[path.join(root,'webui/frontend/node_modules/next/dist/bin/next'),'start','--hostname','127.0.0.1','--port','3118'],path.join(root,'webui/frontend'),'frontend');
for(const sig of ['SIGINT','SIGTERM']) process.on(sig,()=>{for(const p of children)p.kill();process.exit(0)});
setInterval(()=>{},1000);
