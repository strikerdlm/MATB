async (page) => {

  await page.screenshot({path:'EMAVI/capturas/03_openmatb_original.png',fullPage:true,animations:'disabled'});
  const source=await page.locator('.fac-preview-grid').screenshot({path:'EMAVI/capturas/03_openmatb_detalle.png',animations:'disabled'});
  const frame=await page.context().newPage();
  await frame.setContent('<html style="background:transparent"><body style="margin:0;padding:20px;background:transparent;display:inline-block"><img style="display:block" src="data:image/png;base64,'+source.toString('base64')+'"></body></html>');
  await frame.locator('img').evaluate(img=>img.decode());
  const dimensions=await frame.locator('img').evaluate(img=>({width:img.naturalWidth+40,height:img.naturalHeight+40}));
  await frame.setViewportSize(dimensions);
  await frame.screenshot({path:'EMAVI/capturas/03_openmatb.png',omitBackground:true,animations:'disabled'});
  await frame.close();
  await page.goto('http://127.0.0.1:3118/pvt?purpose=practice&fast=1');
}
