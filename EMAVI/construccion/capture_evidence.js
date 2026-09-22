async (page) => {

  await page.screenshot({path:'EMAVI/capturas/06_evidencia_original.png',fullPage:true,animations:'disabled'});
  const source=await page.getByRole('region',{name:'Inspector de evidencia',exact:true}).screenshot({path:'EMAVI/capturas/06_evidencia_detalle.png',animations:'disabled'});
  const frame=await page.context().newPage();
  await frame.setContent('<html style="background:transparent"><body style="margin:0;padding:20px;background:transparent;display:inline-block"><img style="display:block" src="data:image/png;base64,'+source.toString('base64')+'"></body></html>');
  await frame.locator('img').evaluate(img=>img.decode());
  const dimensions=await frame.locator('img').evaluate(img=>({width:img.naturalWidth+40,height:img.naturalHeight+40}));
  await frame.setViewportSize(dimensions);
  await frame.screenshot({path:'EMAVI/capturas/06_evidencia.png',omitBackground:true,animations:'disabled'});
  await frame.close();
  await page.getByRole('button',{name:'track.sample · center_deviation',exact:true}).first().click();
}
