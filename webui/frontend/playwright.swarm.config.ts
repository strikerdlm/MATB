import {defineConfig,devices} from "@playwright/test";
import path from "node:path";
import fs from "node:fs";
import {resolvePythonExecutable,shellCommand} from "./scripts/e2e-runtime.mjs";
const root=__dirname,repo=path.resolve(root,"../..");
const apiPort=process.env.MATB_SWARM_API_PORT??"8186",uiPort=process.env.MATB_SWARM_UI_PORT??"3186";
process.env.MATB_SWARM_API_PORT=apiPort;
const origin=`http://127.0.0.1:${uiPort}`;
const output=path.join(repo,".test-tmp",`swarm-browser-${Date.now()}`);
fs.mkdirSync(output,{recursive:true});
const env={...process.env,PYTHONNOUSERSITE:"1",PYTHONDONTWRITEBYTECODE:"1",PYTHONUTF8:"1",MATB_DB_PATH:path.join(output,"test.db"),MATB_SIMULATION_OUTPUT_DIR:path.join(output,"exports"),MATB_SIMULATION_SCENARIO_DIR:path.join(repo,"tests/suas/fixtures"),MATB_SIMULATION_TEST_MODE:"1",MATB_SIMULATION_WALL_TIME_SCALE:"1",MATB_GEOGRAPHY_DIR:path.join(output,"geography"),MATB_BACKEND_PORT:apiPort,MATB_FRONTEND_ORIGINS:origin,NEXT_TELEMETRY_DISABLED:"1"};
export default defineConfig({testDir:"./e2e",testMatch:"swarm.spec.ts",workers:1,timeout:180000,expect:{timeout:20000},reporter:"list",outputDir:".next/swarm-acceptance",use:{...devices["Desktop Chrome"],baseURL:origin,launchOptions:process.env.MATB_SWARM_GPU === "1" ? {args:["--use-angle=d3d11"]} : {},extraHTTPHeaders:{Origin:origin},screenshot:"only-on-failure",trace:"retain-on-failure"},webServer:[
  {command:shellCommand(resolvePythonExecutable(),["-m","uvicorn","app.main:app","--host","127.0.0.1","--port",apiPort]),cwd:path.join(repo,"webui/backend"),url:`http://127.0.0.1:${apiPort}/health`,env,timeout:120000},
  {command:shellCommand(process.execPath,[path.join(root,"node_modules/next/dist/bin/next"),"start","--hostname","127.0.0.1","--port",uiPort]),cwd:root,url:origin+"/mission/setup",env,timeout:120000}
]});
