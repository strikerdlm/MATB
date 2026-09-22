async (page) => {

  await page.screenshot({path:'EMAVI/capturas/07_evento_original.png',fullPage:true,animations:'disabled'});
  const source=await page.getByRole('region',{name:'Revisión de evento',exact:true}).screenshot({path:'EMAVI/capturas/07_evento_detalle.png',animations:'disabled'});
  const frame=await page.context().newPage();
  await frame.setContent('<html style="background:transparent"><body style="margin:0;padding:20px;background:transparent;display:inline-block"><img style="display:block" src="data:image/png;base64,'+source.toString('base64')+'"></body></html>');
  await frame.locator('img').evaluate(img=>img.decode());
  const dimensions=await frame.locator('img').evaluate(img=>({width:img.naturalWidth+40,height:img.naturalHeight+40}));
  await frame.setViewportSize(dimensions);
  await frame.screenshot({path:'EMAVI/capturas/07_evento.png',omitBackground:true,animations:'disabled'});
  await frame.close();
  const downloadPromise=page.waitForEvent('download');
  await page.getByRole('button',{name:'Exportar evidencia verificable',exact:true}).click();
  const download=await downloadPromise;
  await download.saveAs('EMAVI/construccion/runtime/evidencia_demo.zip');
  await page.goto('http://127.0.0.1:3118/mission/test?purpose=practice');
}
