import fs from 'node:fs';import path from 'node:path';import{fileURLToPath}from'node:url';import{createRequire}from'node:module';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..'),req=createRequire(path.join(root,'webui/frontend/package.json')),ts=req('typescript'),out=path.join(root,'EMAVI/video'),pkg=path.join(root,'webui/frontend/node_modules/three');
fs.mkdirSync(path.join(out,'vendor'),{recursive:true});
for(const [src,dest]of [['build/three.module.js','three.module.js'],['build/three.core.js','three.core.js'],['examples/jsm/controls/OrbitControls.js','OrbitControls.js'],['LICENSE','LICENSE-three.txt']])fs.copyFileSync(path.join(pkg,src),path.join(out,'vendor',dest));
fs.writeFileSync(path.join(out,'scene.js'),ts.transpileModule(fs.readFileSync(path.join(out,'scene.ts'),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022},reportDiagnostics:true}).outputText);
console.log('Three.js '+JSON.parse(fs.readFileSync(path.join(pkg,'package.json'))).version+' packaged locally.');
