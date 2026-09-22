async page => {
 const id='sim-20260922T003838-4e537726';
 const lease=await page.evaluate(id=>sessionStorage.getItem('matb.simulation.'+id+'.lease'),id);
 const r=await page.request.post('http://127.0.0.1:8018/simulation/sessions/'+id+'/finish',{headers:{Origin:'http://127.0.0.1:3118','X-Simulation-Controller':lease},data:{disposition:'abort',reason:'EMAVI screenshot demonstration complete'}});
 return {status:r.status()};
}
