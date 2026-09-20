'use client';
import { useEffect, useRef, useState } from 'react';
import { getCapabilities } from '@/lib/api';
import { hasComponent } from '@/lib/capabilities';
import { useAppLocale } from '@/lib/i18n';
import type { EvidenceCapture } from '@/lib/evidence';
import { downloadInference, inferenceRequest, jsonRequest, type SemanticPreview, type SemanticRun } from '@/lib/inference';
import { Button } from '@/components/ui/button';

export function SemanticReviewPanel({ capture }: { capture: EvidenceCapture }) {
  const [enabled,setEnabled]=useState(false);
  useEffect(()=>{let active=true; getCapabilities().then(value=>{
    if(active) setEnabled(hasComponent(value,'matb-semantic-review'));
  }).catch(()=>{}); return ()=>{active=false;};},[]);
  return enabled ? <SemanticReviewForm key={capture.id} capture={capture}/> : null;
}

function SemanticReviewForm({capture}:{capture:EvidenceCapture}) {
  const {copy}=useAppLocale();
  const fieldClass='block w-full rounded border border-border bg-background px-2 py-1 text-foreground';
  const [text,setText]=useState('');
  const [language,setLanguage]=useState('en');
  const [events,setEvents]=useState('');
  const [reviewer,setReviewer]=useState('');
  const [protocol,setProtocol]=useState('');
  const [runSource,setRunSource]=useState(capture.runs[0]?.id ?? '');
  const [preview,setPreview]=useState<SemanticPreview|null>(null);
  const [run,setRun]=useState<SemanticRun|null>(null);
  const [approved,setApproved]=useState(false);
  const [labels,setLabels]=useState<Record<string,string>>({});
  const [blinded,setBlinded]=useState(true);
  const [labeled,setLabeled]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const alive=useRef(true);
  useEffect(()=>{alive.current=true;return ()=>{alive.current=false;};},[]);
  async function action(work:()=>Promise<void>) {
    if(busy)return;
    setBusy(true);setError('');
    try {await work();} catch(e){if(alive.current)setError(e instanceof Error?e.message:String(e));}
    finally {if(alive.current)setBusy(false);}
  }
  const blocked=!capture.reconciliation || !runSource;
  async function makePreview(){
    const note=await inferenceRequest<{id:string}>('/inference/annotations',jsonRequest({
      annotation_id:crypto.randomUUID(),capture_id:capture.id,source_event_ids:events.split(',').map(v=>v.trim()).filter(Boolean),
      language,author_role:'researcher',source_kind:'synthetic',original_text:text,
      created_at_ns:(BigInt(Date.now())*BigInt(1000000)).toString()}));
    const queued=await inferenceRequest<SemanticPreview>('/inference/previews',jsonRequest({
      capture_id:capture.id,evidence_run_id:runSource,annotation_id:note.id,pack_id:'matb-debrief-v1'}));
    if(alive.current){setPreview(queued);setApproved(false);setRun(null);setLabeled(false);setBlinded(true);setLabels({});}
  }
  async function refresh(){
    if(preview && !run){const value=await inferenceRequest<SemanticPreview>(`/inference/previews/${encodeURIComponent(preview.id)}`);if(alive.current)setPreview(value);}
    if(run){const value=await inferenceRequest<SemanticRun>(`/inference/runs/${encodeURIComponent(run.id)}`);if(alive.current)setRun(value);}
  }
  async function submit(){
    if(!preview?.lineage)return;
    const now=BigInt(Date.now())*BigInt(1000000);
    const value=await inferenceRequest<SemanticRun>('/inference/runs',jsonRequest({preview_id:preview.id,
      preview_hash:preview.preview_hash,question_pack_id:'matb-debrief-v1',authorization:{
      provider_id:'jev_ai_pro',purpose:'retrospective_annotation',payload_hash:preview.lineage.payload_hash,
      approved_by:reviewer,approved_at_ns:now.toString(),expires_at_ns:(now+BigInt(3600000000000)).toString(),
      revoked:false,redaction_reviewed:true,protocol_authorization:protocol,data_processing_authorization:'synthetic-only'}}));
    if(alive.current)setRun(value);
  }
  async function label(){
    if(!run)return;
    await inferenceRequest(`/inference/runs/${encodeURIComponent(run.id)}/reviews`,jsonRequest({
      reviewer,activity:blinded?'blinded_reference':'adjudication',labels_json:JSON.stringify(labels)}));
    if(alive.current)setLabeled(true);
  }
  async function reveal(){
    if(!run)return;
    const value=await inferenceRequest<SemanticRun>(`/inference/runs/${encodeURIComponent(run.id)}?include_answers=true&reviewer=${encodeURIComponent(reviewer)}`);
    if(alive.current){setRun(value);setBlinded(false);}
  }
  const result=run?.result_json ? JSON.parse(run.result_json) as {answers_json:string;requested_model:string;resolved_model:string;raw_response_hash:string} : null;
  return <section className="control-surface min-w-0 space-y-3" aria-label={copy('Revisión semántica experimental','Experimental semantic review')}>
    <h3 className="font-semibold">{copy('Revisión semántica experimental','Experimental semantic review')}</h3>
    <p>{copy('Solo material sintético. Los códigos describen el texto; no son mediciones fisiológicas ni decisiones operativas.','Synthetic material only. Codes describe text; they are not physiological measurements or operational decisions.')}</p>
    {blocked && <p role="status">{copy('Bloqueado: se requiere una conciliación terminada.','Blocked: completed reconciliation required.')}</p>}
    <label className="block">{copy('Conciliación fija','Frozen evidence run')}<select className={fieldClass} value={runSource} onChange={e=>{setRunSource(e.target.value);setPreview(null);}}>{capture.runs.map(r=><option key={r.id} value={r.id}>{r.id}</option>)}</select></label>
    <label className="block">{copy('Idioma del texto','Source language')}<select className={fieldClass} value={language} onChange={e=>{setLanguage(e.target.value);setPreview(null);}}><option value="en">English</option><option value="es">Español</option></select></label>
    <label className="block">{copy('Nota sintética','Synthetic note')}<textarea className={fieldClass} maxLength={8000} value={text} onChange={e=>{setText(e.target.value);setPreview(null);}}/></label>
    <label className="block">{copy('IDs de eventos separados por comas','Comma-separated source event IDs')}<input className={fieldClass} value={events} onChange={e=>{setEvents(e.target.value);setPreview(null);}}/></label>
    <Button disabled={blocked||busy||!text.trim()} onClick={()=>void action(makePreview)}>{copy('Crear vista previa','Create preview')}</Button>
    {(preview||run) && <><p role="status">{run?.status??preview?.status}</p><Button disabled={busy} onClick={()=>void action(refresh)}>{copy('Actualizar estado','Refresh status')}</Button></>}
    {preview?.payload && <><h4>{copy('Bytes de salida revisados','Reviewed outbound payload')}</h4><pre className="whitespace-pre-wrap break-all text-xs">{preview.payload}</pre><details><summary>{copy('Procedencia y exclusiones','Provenance and exclusions')}</summary><pre className="whitespace-pre-wrap break-all text-xs">{JSON.stringify(preview.lineage,null,2)}</pre></details>
      <label className="block">{copy('Revisor','Reviewer')}<input className={fieldClass} value={reviewer} onChange={e=>setReviewer(e.target.value)}/></label>
      <label className="block">{copy('Autorización del protocolo sintético','Synthetic protocol authorization')}<input className={fieldClass} value={protocol} onChange={e=>setProtocol(e.target.value)}/></label>
      <label className="block"><input type="checkbox" checked={approved} onChange={e=>setApproved(e.target.checked)}/>{copy('Revisé este texto sintético y autorizo estos bytes por una hora.','I reviewed this synthetic text and authorize these bytes for one hour.')}</label>
      <Button disabled={busy||!approved||!reviewer.trim()||!protocol.trim()||!!run} onClick={()=>void action(submit)}>{copy('Autorizar y poner en cola','Authorize and queue')}</Button></>}
    {run && <><label className="block"><input type="checkbox" checked={blinded} disabled={!!result} onChange={e=>setBlinded(e.target.checked)}/>{copy('Etiquetado independiente ciego','Independent blinded labeling')}</label>
      {[
        {id:'reported_task_tradeoff',title:copy('Priorización declarada','Reported task tradeoff'),options:['present','explicit_absence','unmentioned','insufficient_evidence']},
        {id:'automation_belief',title:copy('Expectativa de automatización','Automation belief'),options:['expected_active','expected_inactive','conflicting','not_stated','insufficient_evidence']},
        {id:'reported_instruction_difficulty',title:copy('Dificultad con instrucciones','Instruction difficulty'),options:['present','explicit_absence','unmentioned','insufficient_evidence']},
      ].map(question=><label className="block" key={question.id}>{question.title}<select className={fieldClass} value={labels[question.id]??''} onChange={e=>setLabels({...labels,[question.id]:e.target.value})}>
        <option value="">{copy('Seleccione una etiqueta','Select a label')}</option>
        {question.options.map(option=><option key={option} value={option}>{({present:copy('Presente','Present'),explicit_absence:copy('Ausencia explícita','Explicit absence'),unmentioned:copy('No mencionado','Unmentioned'),insufficient_evidence:copy('Evidencia insuficiente','Insufficient evidence'),expected_active:copy('Esperaba activa','Expected active'),expected_inactive:copy('Esperaba inactiva','Expected inactive'),conflicting:copy('Contradictoria','Conflicting'),not_stated:copy('No declarada','Not stated')} as Record<string,string>)[option]}</option>)}
      </select></label>)}
      <Button disabled={busy||!reviewer.trim()||Object.values(labels).filter(Boolean).length!==3||(blinded&&labeled)} onClick={()=>void action(label)}>{copy('Guardar etiquetas','Save labels')}</Button>
      <Button disabled={busy||!reviewer.trim()||(blinded&&!labeled)} onClick={()=>void action(reveal)}>{copy('Mostrar evaluación','Show assessment')}</Button>
    </>}
    {result && <><p>{result.requested_model} / {result.resolved_model}</p><pre className="whitespace-pre-wrap break-all">{JSON.stringify(JSON.parse(result.answers_json),null,2)}</pre><p className="break-all text-xs">{result.raw_response_hash}</p><Button disabled={busy} onClick={()=>void action(()=>downloadInference(run!.id,reviewer))}>{copy('Exportar inferencia separada','Export separate inference')}</Button></>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
