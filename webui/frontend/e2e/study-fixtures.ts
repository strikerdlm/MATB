import {expect,type APIRequestContext} from '@playwright/test';
import type {StudyOccasion,StudyPayload} from '../src/lib/study';
const base='http://127.0.0.1:8000';
export async function post(request:APIRequestContext,path:string,data?:unknown){const response=await request.post(base+path,{data});expect(response.ok(),await response.text()).toBe(true);return response.json();}
/** Real local approval workflow in the runner's isolated DB; never production approval. */
export async function approveStudyFixture(request:APIRequestContext,participant:string,occasions:StudyOccasion[],visitSchedule?:StudyPayload['study']['visits'], modify?: (payload:StudyPayload)=>void){
 const payload:StudyPayload=await (await request.get(base+'/study/templates/pre-post-recovery')).json();
 if(visitSchedule)payload.study.visits=visitSchedule;
 payload.study.synthetic=false;payload.study.title='Isolated browser assignment fixture';payload.study.occasions=occasions;payload.study.enabled_instruments=[...new Set(occasions.map(o=>o.instrument))];
 payload.study.rules={preparation:'No preparation required in isolated transport fixture.',repeat:'Retain explicit fixture repeats.',interruption:'Retain available fixture evidence.'};
 payload.study.preparation_policy=occasions.map(o=>({occasion_key:o.key,placement:'before_baseline',demonstration_required:false,acknowledgement_required:false,comprehension:[],practice:[],rationale:'Isolated transport acceptance; no participant competence is prescribed or claimed.'}));
 payload.study.repeat_policy={permitted_causes:['intentional_repeat'],max_attempts:2,selection:'explicit',rationale:'Explicit fixture repeats only.'};payload.study.interruption_policy={available_outcomes:'retain_available',rationale:'Keep fixture evidence.'};
 payload.analysis.outcomes=[{key:'observed',metric:occasions[0].instrument==='liftoff'?'liftoff.performance':'pvt.median_rt_ms',occasion_keys:[occasions[0].key],summary:'individual'}];
 payload.analysis.rules={exclusions:'None for transport inspection.',denominators:'All assigned fixtures.',qualification:'Report fixture status.',pooling:'Identical configurations only.',historical_unknowns:'exclude'};
 payload.analysis.eligibility_policy={repeat_selection:'explicit',incomplete_denominator:'assigned',missing_handling:'exclude_outcome',source_requirement:'report_status',physical_requirement:'report_status',human_calibration_requirement:'report_status',participant_preparation_requirement:'report_status',protocol_requirement:'report_status',configuration_pooling:'identical_only',pooling_review:null,hcf_enabled:false,hcf_screen_keys:[],hcf_attempt_selection:'explicit',rationale:'No scientific analysis is executed by this browser fixture.'};
 if(modify)modify(payload);
 const draft=await post(request,'/study/drafts',payload);const rehearsal=await post(request,`/study/drafts/${draft.id}/rehearse`,{});
 const version=await post(request,`/study/drafts/${draft.id}/freeze`,{actor:'Dr Browser Fixture',reason:'Isolated transport acceptance only',sha256:draft.sha256,rehearsal_id:rehearsal.id});
 await post(request,`/study/versions/${version.id}/activate`,{actor:'Dr Browser Fixture',reason:'Isolated browser fixture'});
 if(visitSchedule)await post(request,'/participants',{id:participant,enrollment_date:'2026-09-10'});
 const visits=await (await request.get(base+`/participants/${participant}/visits`)).json();
 const assignment=await post(request,`/study/versions/${version.id}/assign`,{participant_id:participant,visit_id:visits.find((v:{visit_ordinal:number})=>v.visit_ordinal===occasions[0].visit_ordinal).id,arm:'A',actor:'Dr Browser Fixture'});
 return {...assignment,occasions:JSON.parse(assignment.occasions_json) as Record<string,string>};
}
export async function baseOccasion(request:APIRequestContext):Promise<StudyOccasion>{const payload=await (await request.get(base+'/study/templates/pre-post-recovery')).json();return {...payload.study.occasions[0],locale:'en'};}
