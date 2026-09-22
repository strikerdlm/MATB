async page => {
 const headers={Origin:'http://127.0.0.1:3118'};
 const id='sim-20260922T003049-6d131082';
 const lease=await page.evaluate(id=>sessionStorage.getItem('matb.simulation.'+id+'.lease'),id);
 const stop=await page.request.post('http://127.0.0.1:8018/simulation/sessions/'+id+'/finish',{headers:{...headers,'X-Simulation-Controller':lease},data:{disposition:'abort',reason:'EMAVI synthetic demo retry after ended KSS practice'}});
 const recovery=await page.request.post('http://127.0.0.1:8018/station/recover-idle',{headers,data:{actor:'EMAVI demo automation',reason:'Synthetic KSS practice has ended and prepared synthetic mission aborted; no participant and no active acquisition.'}});
 for (const role of ['capture_manifest','scenario_manifest','events','timing']) await page.locator('#evidence-'+role).setInputFiles('EMAVI/construccion/runtime/synthetic-reference/'+role+'.upload');
 await page.getByRole('button',{name:'Importar evidencia',exact:true}).click();
 await page.locator('button[data-metric=track_rmse_deviation]').waitFor();
 return {missionAbortStatus:stop.status(),recoveryStatus:recovery.status()};
}
