import {test,expect} from "@playwright/test";
import {writeFileSync} from "node:fs";
const api=`http://127.0.0.1:${process.env.MATB_SWARM_API_PORT ?? "8000"}`;
for(const probe of [false,true]) test(`swarm v3 ${probe?"SAGAT concealment":"group control and third-person replay"}`,async({page,request},testInfo)=>{
  await page.setViewportSize({width:1920,height:1080});
  await page.route("https://**/*",r=>r.abort());
  const errors:string[]=[];page.on("pageerror",e=>errors.push(e.message));
  const scene=(await(await request.get(`${api}/simulation/scenes`)).json())[0];
  const response=await request.post(`${api}/simulation/technical-sessions`,{data:{execution_purpose:"practice",scenario_id:probe?"swarm_probe_test":"swarm_visual_test",block_id:"HIGH",locale:"en",presentation:{version:3,blocks:{HIGH:"3d"},scene_id:scene.id,scene_sha256:scene.sha256,camera:"swarm",controls:{smooth_camera:true,contact_cycling:true,adjustable_layers:true}}}});
  expect(response.status(),await response.text()).toBe(201);
  const prepared=await response.json(),headers={"X-Simulation-Controller":prepared.controller_lease};
  await page.addInitScript(({id,lease})=>sessionStorage.setItem(`matb.simulation.${id}.lease`,lease),{id:prepared.id,lease:prepared.controller_lease});
  try{
    const ready=page.waitForResponse(r=>r.url().endsWith("/presentation")&&r.request().postDataJSON()?.kind==="ready"&&r.status()===204);
    await page.goto(`/mission?session=${prepared.id}&metrics=1`);await ready;
    await page.getByRole("button",{name:/start block/i}).click();
    if(probe){
      const {visibleProbe,resolveVisibleProbe}=await import("./fixtures");
      // Software-rendered Windows runners can reach the probe after the default
      // 20s wall-clock budget; keep the concealment assertions below unchanged.
      await expect.poll(()=>visibleProbe(page),{timeout:60_000}).toBe("SAGAT");
      await expect(page.getByTestId("mission-three-view")).toHaveCount(0);
      await expect(page.getByRole("figure",{name:"North-up swarm overview"})).toHaveCount(0);
      await expect(page.getByRole("region",{name:"Swarm control"})).toHaveCount(0);
      await resolveVisibleProbe(page);
    }else{
      const control=page.getByRole("region",{name:"Swarm control"});
      await expect(control).toContainText("8 members");
      const observerCommand=await request.post(`${api}/simulation/sessions/${prepared.id}/commands`,{data:{command_id:crypto.randomUUID(),expected_state_version:0,kind:"SWARM_TASK",payload:{group_id:"ALPHA",action:"HOLD",target_id:""}}});
      expect(observerCommand.status()).toBe(403);
      await control.getByRole("button",{name:"Formation transit"}).click();
      await expect.poll(async()=> (await(await request.get(`${api}/simulation/sessions/${prepared.id}/state`)).json()).swarms.ALPHA.command_count).toBe(1);
      await expect(page.getByRole("figure",{name:"North-up swarm overview"})).toBeVisible();
      const camera=page.getByRole("combobox",{name:"Camera",exact:true});
      const switchCamera=async (mode:string)=>{
        const settled=page.waitForResponse(r=>r.url().endsWith("/presentation")&&r.request().postDataJSON()?.kind==="transition_end"&&r.request().postDataJSON()?.resolved?.camera===mode&&r.status()===204);
        await camera.selectOption(mode);await settled;
      };
      await switchCamera("follow");
      await expect(camera).toHaveValue("follow");
      await page.screenshot({path:testInfo.outputPath("swarm-chase.png")});
      await switchCamera("swarm");
      await page.screenshot({path:testInfo.outputPath("swarm-overview.png")});
      await control.getByRole("button",{name:"Cooperative search"}).click();
      await expect.poll(async()=> (await(await request.get(`${api}/simulation/sessions/${prepared.id}/state`)).json()).swarms.ALPHA.command_count).toBe(2);
      await page.waitForTimeout(2000);
      await page.evaluate(()=>Reflect.get(window,"__matbResetPresentationMetrics")?.());
      await page.waitForTimeout(10000);
      const metrics=await page.evaluate(()=>Reflect.get(window,"__matbPresentationMetrics")?.());
      writeFileSync(testInfo.outputPath("swarm-metrics.json"),JSON.stringify({browser:await page.context().browser()?.version(),viewport:page.viewportSize(),metrics},null,2));
      expect(metrics.triangles).toBeGreaterThan(0);
      expect(metrics.frameSamples).toBeGreaterThan(20);
      if (process.env.MATB_SWARM_REQUIRE_PERFORMANCE === "1") {
        expect(metrics.device).not.toMatch(/swiftshader|llvmpipe|software/i);
        expect(metrics.frameSamples).toBeGreaterThanOrEqual(120);
        expect(metrics.frameIntervalP95Ms).toBeLessThan(33.3);
      }
      expect(errors).toEqual([]);
      await request.post(`${api}/simulation/sessions/${prepared.id}/pause`,{headers});
      await page.waitForTimeout(1000);
      const finish=await request.post(`${api}/simulation/sessions/${prepared.id}/finish`,{headers,data:{disposition:"complete"}});expect(finish.status(),await finish.text()).toBe(200);
      const debrief=await(await request.get(`${api}/simulation/sessions/${prepared.id}/debrief`)).json();
      writeFileSync(testInfo.outputPath("swarm-debrief.json"),JSON.stringify(debrief,null,2));
      expect(JSON.stringify(debrief)).toContain("racing-quad-v1-scale80");
      expect(debrief.metrics.swarm.blocks[0].groups.ALPHA.group_command_count).toBe(2);
      expect(debrief.deterministic_replay_verified).toBe(true);
      await page.goto(`/mission/debrief?session=${prepared.id}`);
      const seek=page.getByRole("slider",{name:/replay time/i});
      await expect(seek).toBeVisible();await seek.press("End");
      await expect(page.getByRole("figure",{name:"North-up swarm overview"})).toBeVisible();
      await expect(page.getByText("Recorded viewport",{exact:false})).toBeVisible();
      await seek.press("Home");await seek.press("End");
      await expect(page.getByRole("figure",{name:"North-up swarm overview"})).toBeVisible();
      await expect(page.getByRole("combobox",{name:"Camera",exact:true})).toBeDisabled();
      const labels=page.getByTestId("mission-three-view").getByRole("button");
      for (const label of await labels.all()) await expect(label).toBeDisabled();
      await page.screenshot({path:testInfo.outputPath("swarm-replay.png")});
      expect(errors).toEqual([]);
    }
  }finally{await request.post(`${api}/simulation/sessions/${prepared.id}/finish`,{headers,data:{disposition:"abort"}});}
});
