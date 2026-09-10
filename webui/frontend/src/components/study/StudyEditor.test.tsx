import {render, screen, fireEvent, waitFor} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import {StudyEditor} from './StudyEditor';
vi.mock('@/lib/study',()=>({studyVersions:vi.fn(async()=>({versions:[],active_version_id:null})),studyCall:vi.fn(async(path:string)=>path==='/bindings'?{pvt:[{binding_id:'pvt-browser-v1'}]}:({study:{study_id:'test-study',title:'Draft',synthetic:true,arms:['A'],visits:[{ordinal:1,code:'T0',scheduled_day:0}],occasions:[{key:'pre',visit_ordinal:1,instrument:'pvt',phase:'pre',order:1,locale:'en',condition_by_arm:{A:'rest'},config:{},prerequisite_keys:[]}],recovery_intervals:[],rules:{preparation:'',repeat:'',interruption:''}},analysis:{unit:'participant',outcomes:[{key:'primary',metric:'pvt.median_rt_ms',occasion_keys:['pre'],summary:'individual'}],contrasts:[],rules:{exclusions:'',denominators:'',qualification:'',pooling:'',historical_unknowns:'exclude'}}}))}));
describe('constrained authoring',()=>{it('exposes occasion and required authored rule controls without JSON-only editing',async()=>{render(<StudyEditor/>);fireEvent.click(screen.getByRole('button',{name:/Load template|Cargar plantilla/}));await waitFor(()=>expect(screen.getByLabelText(/Preparation rule|Regla de preparación/)).toBeTruthy());expect(screen.getByLabelText(/Instrument|Instrumento/)).toBeTruthy();expect(screen.getByLabelText(/Named researcher|Investigador responsable/)).toBeTruthy();expect(screen.getByRole('button',{name:/Freeze|Congelar/}).hasAttribute('disabled')).toBe(true);});});

it('binds approval to the saved rehearsal hash and invalidates it when a form field changes',async()=>{
 const api=await import('@/lib/study');
 const template=await api.studyCall('/templates/pre-post-recovery');
 vi.mocked(api.studyCall).mockImplementation(async(path,body)=>{
  if(path==='/bindings')return {pvt:[{binding_id:'pvt-browser-v1'}]} as never;
  if(path.startsWith('/templates'))return structuredClone(template) as never;
  if(path.endsWith('/rehearse'))return {id:'rehearsal-current'} as never;
  if(path==='/drafts'||path==='/drafts/draft-current')return {id:'draft-current',sha256:'saved-hash',payload_json:JSON.stringify(body),frozen_version_id:null} as never;
  return {} as never;
 });
 render(<StudyEditor/>);
 fireEvent.click(screen.getByRole('button',{name:/Load template|Cargar plantilla/}));
 await screen.findByLabelText(/This draft is synthetic|Este borrador es sintético/);
 fireEvent.click(screen.getByLabelText(/This draft is synthetic|Este borrador es sintético/));
 fireEvent.change(screen.getByLabelText(/Named researcher|Investigador responsable/),{target:{value:'Dr Author'}});
 fireEvent.change(screen.getByLabelText(/Reason and review|Motivo y declaración/),{target:{value:'Reviewed authored criteria'}});
 fireEvent.click(screen.getByRole('button',{name:/^Rehearse$|^Ensayar$/}));
 await waitFor(()=>expect(screen.getByRole('button',{name:/Freeze|Congelar/})).toBeEnabled());
 fireEvent.change(screen.getByLabelText(/^Title$|^Título$/),{target:{value:'Amended title'}});
 expect(screen.getByRole('button',{name:/Freeze|Congelar/})).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:/^Rehearse$|^Ensayar$/}));
 await waitFor(()=>expect(screen.getByRole('button',{name:/Freeze|Congelar/})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:/Freeze|Congelar/}));
 await waitFor(()=>expect(api.studyCall).toHaveBeenCalledWith('/drafts/draft-current/freeze',{sha256:'saved-hash',rehearsal_id:'rehearsal-current',actor:'Dr Author',reason:'Reviewed authored criteria'}));
});
