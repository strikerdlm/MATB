import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const require=createRequire(path.join(root,'webui/frontend/package.json'));const ts=require('typescript');
const out=path.join(root,'EMAVI/construccion/runtime/video-helpers');fs.mkdirSync(out,{recursive:true});
for(const file of ['study-fixtures','fixtures']){
 let src=fs.readFileSync(path.join(root,`webui/frontend/e2e/${file}.ts`),'utf8').replaceAll('127.0.0.1:8000','127.0.0.1:8018').replaceAll("'./study-fixtures'","'./study-fixtures.mjs'").replaceAll("'@playwright/test'",JSON.stringify(pathToFileURL(require.resolve('@playwright/test').replace('index.js','index.mjs')).href)).replaceAll('"@playwright/test"',JSON.stringify(pathToFileURL(require.resolve('@playwright/test').replace('index.js','index.mjs')).href));
 src=src.replaceAll('Dr Browser Fixture','Operador de demostración EMAVI').replaceAll('Isolated browser assignment fixture','EMAVI · demostración técnica sintética').replaceAll("locale:'en'","locale:'es-419'").replaceAll('locale:"en"','locale:"es-419"');
 for(const[a,b]of [['start block','iniciar bloque'],['submit rating','enviar valoración'],['submit answer','enviar respuesta'],['submit measures','enviar medidas'],['post-block measures','medidas posteriores al bloque'],['situation awareness','conciencia situacional'],['ISA \\/ response required','ISA \\/ respuesta requerida'],['assign sector','asignar sector'],['transit|search|hold','transit|search|hold|tránsito|búsqueda|espera']])src=src.replaceAll(a,b);
 fs.writeFileSync(path.join(out,file+'.mjs'),ts.transpileModule(src,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText);
}
console.log('Local recording helpers prepared from repository browser acceptance sources.');
