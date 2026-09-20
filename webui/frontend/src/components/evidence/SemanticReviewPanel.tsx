'use client';
import { useEffect, useRef, useState } from 'react';
import { getCapabilities } from '@/lib/api';
import { hasComponent } from '@/lib/capabilities';
import { useAppLocale } from '@/lib/i18n';
import type { EvidenceCapture } from '@/lib/evidence';
import { downloadInference, inferenceRequest, jsonRequest, type SemanticPreview, type SemanticRun, type SemanticNote, type SemanticReview, type SemanticPage } from '@/lib/inference';
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
  const [notice,setNotice]=useState('');
  const [reason,setReason]=useState('');
  const [notes,setNotes]=useState<SemanticNote[]>([]);
  const [savedRuns,setSavedRuns]=useState<SemanticRun[]>([]);
  const [noteOffset,setNoteOffset]=useState<number|null>(0);
  const [runOffset,setRunOffset]=useState<number|null>(0);
  const [selectedNote,setSelectedNote]=useState<SemanticNote|null>(null);
  const [history,setHistory]=useState<SemanticReview[]>([]);
  const [reviewOffset,setReviewOffset]=useState<number|null>(0);
  const [intervalStart,setIntervalStart]=useState('');
  const [intervalEnd,setIntervalEnd]=useState('');
  const [timerStart,setTimerStart]=useState<number|null>(null);
  const alive=useRef(true);
  const reviewerContext=useRef('');
  useEffect(()=>{alive.current=true;return ()=>{alive.current=false;};},[]);
  async function action(work:()=>Promise<void>) {
    if(busy)return;
    setBusy(true);setError('');
    try {await work();} catch(e){if(alive.current)setError(e instanceof Error?e.message:String(e));}
    finally {if(alive.current)setBusy(false);}
  }
  const blocked=!capture.reconciliation || !runSource;
  function clearAssessment(){setPreview(null);setRun(null);setApproved(false);setLabeled(false);setBlinded(true);setLabels({});setHistory([]);setReviewOffset(0);setNotice('');setTimerStart(null);}
  async function loadSaved(append=false){
    const outcomes=await Promise.allSettled([
      !append||noteOffset!==null?inferenceRequest<SemanticPage<SemanticNote>>(`/inference/annotations?capture_id=${encodeURIComponent(capture.id)}&offset=${append?noteOffset:0}`):null,
      !append||runOffset!==null?inferenceRequest<SemanticPage<SemanticRun>>(`/inference/runs?capture_id=${encodeURIComponent(capture.id)}&offset=${append?runOffset:0}`):null,
    ]);
    const failed=outcomes.find(outcome=>outcome.status==='rejected');
    if(failed?.status==='rejected')throw failed.reason;
    const [n,r]=outcomes.map(outcome=>outcome.status==='fulfilled'?outcome.value:null) as [SemanticPage<SemanticNote>|null,SemanticPage<SemanticRun>|null];
    if(!alive.current)return;
    if(n){setNotes(old=>append?[...old,...n.items]:n.items);setNoteOffset(n.next_offset);}
    if(r){setSavedRuns(old=>append?[...old,...r.items]:r.items);setRunOffset(r.next_offset);}
  }
  function chooseNote(note:SemanticNote|null){
    clearAssessment();setSelectedNote(note);setText(note?.original_text??'');setLanguage(note?.language??'en');
    setEvents(note?.source_event_ids.join(',')??'');setIntervalStart(note?.observation_start_ns??'');setIntervalEnd(note?.observation_end_ns??'');
  }
  async function openRun(id:string){
    const value=await inferenceRequest<SemanticRun>(`/inference/runs/${encodeURIComponent(id)}`);
    if(!value.preview_id)throw new Error('Missing frozen preview');
    const frozen=await inferenceRequest<SemanticPreview>(`/inference/previews/${encodeURIComponent(value.preview_id)}`);
    if(frozen.lineage?.capture_id && frozen.lineage.capture_id!==capture.id)throw new Error('Capture mismatch');
    const note=frozen.lineage?.annotation_id?await inferenceRequest<SemanticNote>(`/inference/annotations/${encodeURIComponent(String(frozen.lineage.annotation_id))}`):null;
    if(note&&note.capture_id!==capture.id)throw new Error('Annotation capture mismatch');
    if(!alive.current)return;
    chooseNote(note);setRun(value);setPreview(frozen);setRunSource(frozen.lineage?.evidence_run_id??'');
  }
  async function makePreview(){
    const unchanged=selectedNote && text===selectedNote.original_text && language===selectedNote.language &&
      events===selectedNote.source_event_ids.join(',') && intervalStart===(selectedNote.observation_start_ns??'') && intervalEnd===(selectedNote.observation_end_ns??'');
    const note=unchanged?{id:selectedNote.annotation_id}:await inferenceRequest<{id:string}>('/inference/annotations',jsonRequest({
      annotation_id:crypto.randomUUID(),capture_id:capture.id,source_event_ids:events.split(',').map(v=>v.trim()).filter(Boolean),
      language,author_role:selectedNote?.author_role??'researcher',source_kind:selectedNote?.source_kind??'synthetic',original_text:text,
      created_at_ns:(BigInt(Date.now())*BigInt(1000000)).toString(),supersedes_annotation_id:selectedNote?.annotation_id??null,
      observation_start_ns:intervalStart||null,observation_end_ns:intervalEnd||null}));
    if(!alive.current)return;
    const queued=await inferenceRequest<SemanticPreview>('/inference/previews',jsonRequest({
      capture_id:capture.id,evidence_run_id:runSource,annotation_id:note.id,pack_id:'matb-debrief-v1'}));
    if(alive.current){clearAssessment();setPreview(queued);}
  }
  async function refresh(){
    if(preview && !run){const value=await inferenceRequest<SemanticPreview>(`/inference/previews/${encodeURIComponent(preview.id)}`);if(alive.current)setPreview(value);}
    if(run){const query=!blinded?`?include_answers=true&reviewer=${encodeURIComponent(reviewer)}`:'';const value=await inferenceRequest<SemanticRun>(`/inference/runs/${encodeURIComponent(run.id)}${query}`);if(alive.current)setRun(value);}
  }
  async function submit(retry=false){
    if(!preview?.lineage)return;
    const now=BigInt(Date.now())*BigInt(1000000);
    const endpoint=retry&&run?`/inference/runs/${encodeURIComponent(run.id)}/retry`:'/inference/runs';
    const value=await inferenceRequest<SemanticRun>(endpoint,jsonRequest({preview_id:preview.id,
      preview_hash:preview.preview_hash,question_pack_id:'matb-debrief-v1',authorization:{
      provider_id:'jev_ai_pro',purpose:'retrospective_annotation',payload_hash:preview.lineage.payload_hash,
      approved_by:reviewer,approved_at_ns:now.toString(),expires_at_ns:(now+BigInt(3600000000000)).toString(),
      revoked:false,redaction_reviewed:true,protocol_authorization:protocol,data_processing_authorization:'synthetic-only'}}));
    if(alive.current){setRun(value);setApproved(false);setNotice('');}
  }
  async function revoke(){
    if(!run)return;
    const value=await inferenceRequest<{prevented_dispatch:boolean}>(`/inference/runs/${encodeURIComponent(run.id)}/revoke`,jsonRequest({reviewer,reason}));
    if(alive.current){setApproved(false);setNotice(value.prevented_dispatch?copy('Autorización revocada antes del envío.','Approval revoked before dispatch.'):copy('Autorización revocada; el envío puede haber ocurrido.','Approval revoked; delivery may already have occurred.'));}
    await refresh();
  }
  async function loadReviews(){
    if(!run||reviewOffset===null)return;
    const context=reviewer;
    const value=await inferenceRequest<SemanticPage<SemanticReview>>(`/inference/runs/${encodeURIComponent(run.id)}/reviews?reviewer=${encodeURIComponent(reviewer)}&offset=${reviewOffset}`);
    if(alive.current&&reviewerContext.current===context){setHistory(old=>[...old,...value.items]);setReviewOffset(value.next_offset);}
  }
  async function label(){
    if(!run)return;
    await inferenceRequest(`/inference/runs/${encodeURIComponent(run.id)}/reviews`,jsonRequest({
      reviewer,activity:blinded?'blinded_reference':'adjudication',labels_json:JSON.stringify(labels),
      elapsed_seconds:timerStart===null?null:(performance.now()-timerStart)/1000}));
    if(alive.current){setLabeled(true);setNotice(copy('Etiquetas guardadas.','Labels saved.'));setHistory([]);setReviewOffset(0);setTimerStart(null);}
  }
  async function reveal(){
    if(!run)return;
    const context=reviewer;
    const value=await inferenceRequest<SemanticRun>(`/inference/runs/${encodeURIComponent(run.id)}?include_answers=true&reviewer=${encodeURIComponent(reviewer)}`);
    if(alive.current&&reviewerContext.current===context){setRun(value);setBlinded(false);}
  }
  const result=run?.result_json ? JSON.parse(run.result_json) as {answers_json:string;requested_model:string;resolved_model:string;raw_response_hash:string;outcome:string;error_code?:string;latency_ms:number;usage_json:string} : null;
  const terminal=run&&!['queued','sending'].includes(run.status);
  const retryReady=!run?.earliest_retry_ns || BigInt(run.earliest_retry_ns)<=BigInt(Date.now())*BigInt(1000000);
  const statusText:Record<string,string>={queued:copy('En cola','Queued'),sending:copy('Enviando','Sending'),valid:copy('Evaluación disponible','Assessment available'),blocked:copy('Bloqueado','Blocked'),invalid:copy('Respuesta inválida','Invalid response'),unavailable:copy('Proveedor no disponible','Provider unavailable'),outcome_unknown:copy('Resultado desconocido: el proveedor pudo recibir la solicitud','Unknown outcome: the provider may have received the request'),throttled:copy('Límite del proveedor; espere antes de reintentar','Provider rate limit; wait before retrying'),late:copy('Respuesta tardía; no es evaluación activa','Late response; not an active assessment'),cancelled:copy('Cancelado','Cancelled')};
  return <section className="control-surface min-w-0 space-y-3" aria-label={copy('Revisión semántica experimental','Experimental semantic review')}>
    <h3 className="font-semibold">{copy('Revisión semántica experimental','Experimental semantic review')}</h3>
    <p>{copy('Solo material sintético. Los códigos describen el texto; no son mediciones fisiológicas ni decisiones operativas.','Synthetic material only. Codes describe text; they are not physiological measurements or operational decisions.')}</p>
    <Button disabled={busy} onClick={()=>void action(()=>loadSaved())}>{copy('Cargar revisiones guardadas','Load saved reviews')}</Button>
    {(notes.length>0||savedRuns.length>0)&&<div className="space-y-2">
      <label className="block">{copy('Versión de la nota','Note version')}<select className={fieldClass} value={selectedNote?.annotation_id??''} onChange={e=>chooseNote(notes.find(n=>n.annotation_id===e.target.value)??null)}><option value="">{copy('Nueva nota','New note')}</option>{notes.map(n=><option key={n.annotation_id} value={n.annotation_id}>{n.annotation_id} · {n.language} · {n.created_at_ns}</option>)}</select></label>
      {savedRuns.map(r=><Button className="max-w-full h-auto whitespace-normal break-all py-2" key={r.id} disabled={busy} onClick={()=>void action(()=>openRun(r.id))}>{copy('Abrir intento','Open attempt')} {r.id} · {statusText[r.status]??r.status}</Button>)}
      {(noteOffset!==null||runOffset!==null)&&<Button disabled={busy} onClick={()=>void action(()=>loadSaved(true))}>{copy('Más registros','More records')}</Button>}
    </div>}
    {blocked && <p role="status">{copy('Bloqueado: se requiere una conciliación terminada.','Blocked: completed reconciliation required.')}</p>}
    <label className="block">{copy('Conciliación fija','Frozen evidence run')}<select className={fieldClass} value={runSource} onChange={e=>{setRunSource(e.target.value);clearAssessment();}}>{capture.runs.map(r=><option key={r.id} value={r.id}>{r.id}</option>)}</select></label>
    <label className="block">{copy('Idioma del texto','Source language')}<select className={fieldClass} value={language} onChange={e=>{setLanguage(e.target.value);clearAssessment();}}><option value="en">English</option><option value="es">Español</option></select></label>
    <label className="block">{copy('Nota sintética','Synthetic note')}<textarea className={fieldClass} maxLength={8000} value={text} onChange={e=>{setText(e.target.value);clearAssessment();}}/></label>
    <label className="block">{copy('IDs de eventos separados por comas','Comma-separated source event IDs')}<input className={fieldClass} value={events} onChange={e=>{setEvents(e.target.value);clearAssessment();}}/></label>
    <label className="block">{copy('Inicio observado (ns, opcional)','Observed start (ns, optional)')}<input className={fieldClass} inputMode="numeric" value={intervalStart} onChange={e=>{setIntervalStart(e.target.value);clearAssessment();}}/></label>
    <label className="block">{copy('Fin observado (ns, opcional)','Observed end (ns, optional)')}<input className={fieldClass} inputMode="numeric" value={intervalEnd} onChange={e=>{setIntervalEnd(e.target.value);clearAssessment();}}/></label>
    <Button disabled={blocked||busy||!text.trim()} onClick={()=>void action(makePreview)}>{copy('Crear vista previa','Create preview')}</Button>
    <p role="status">{statusText[run?.status??preview?.status??'']??preview?.status??copy('No ejecutado','Not run')}</p>
    {(preview||run) && <Button disabled={busy} onClick={()=>void action(refresh)}>{copy('Actualizar estado','Refresh status')}</Button>}
    {(run?.error_code||preview?.error_code)&&<p>{copy('Motivo','Reason')}: {run?.error_code??preview?.error_code}</p>}
    {run?.earliest_retry_ns&&<p>{copy('Reintento permitido desde (ns)','Retry permitted after (ns)')}: {run.earliest_retry_ns}</p>}
    {preview?.payload && <><h4>{copy('Bytes de salida revisados','Reviewed outbound payload')}</h4><pre className="whitespace-pre-wrap break-all text-xs">{preview.payload}</pre><details><summary>{copy('Procedencia y exclusiones','Provenance and exclusions')}</summary><pre className="whitespace-pre-wrap break-all text-xs">{JSON.stringify(preview.lineage,null,2)}</pre></details>
      <label className="block">{copy('Revisor','Reviewer')}<input className={fieldClass} disabled={busy} value={reviewer} onChange={e=>{reviewerContext.current=e.target.value;setReviewer(e.target.value);setLabeled(false);setLabels({});setHistory([]);setReviewOffset(0);setBlinded(true);setNotice('');setApproved(false);setTimerStart(null);setRun(old=>old?{...old,result_json:null}:null);}}/></label>
      <label className="block">{copy('Autorización del protocolo sintético','Synthetic protocol authorization')}<input className={fieldClass} value={protocol} onChange={e=>setProtocol(e.target.value)}/></label>
      <label className="block"><input type="checkbox" checked={approved} onChange={e=>setApproved(e.target.checked)}/>{copy('Revisé este texto sintético y autorizo estos bytes por una hora.','I reviewed this synthetic text and authorize these bytes for one hour.')}</label>
      <Button disabled={busy||!approved||!reviewer.trim()||!protocol.trim()||!!run} onClick={()=>void action(()=>submit())}>{copy('Autorizar y poner en cola','Authorize and queue')}</Button>
      {terminal&&<Button disabled={busy||!approved||!reviewer.trim()||!protocol.trim()||!retryReady} onClick={()=>void action(()=>submit(true))}>{copy('Autorizar nuevo intento','Authorize new attempt')}</Button>}
    </>}
    {run&&<><label className="block">{copy('Motivo de revocación','Revocation reason')}<input className={fieldClass} maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/></label><Button disabled={busy||!reviewer.trim()||!reason.trim()} onClick={()=>void action(revoke)}>{copy('Revocar autorización','Revoke approval')}</Button></>}
    {run && <><label className="block"><input type="checkbox" checked={blinded} disabled={!!result||busy} onChange={e=>{setBlinded(e.target.checked);setTimerStart(null);}}/>{copy('Etiquetado independiente ciego','Independent blinded labeling')}</label>
      <Button disabled={busy||timerStart!==null||!reviewer.trim()} onClick={()=>setTimerStart(performance.now())}>{copy('Iniciar cronómetro de codificación','Start coding timer')}</Button>
      {timerStart!==null&&<p role="status">{copy('Cronómetro activo; guardar etiquetas lo detiene. Incluye pausas.','Timer running; saving labels stops it. Includes idle time.')}</p>}
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
    {result && <><p>{result.requested_model} / {result.resolved_model??copy('Modelo no confirmado','Model not confirmed')}</p>
      {Object.entries(JSON.parse(result.answers_json) as Record<string,{type:string;noul?:number;choice?:string;confidence?:number;probabilities?:Record<string,number>}>).map(([id,answer])=><article key={id} className="rounded border border-border p-3 space-y-2"><h4 className="font-semibold">{id==='reported_task_tradeoff'?copy('Priorización declarada','Reported task tradeoff'):id==='automation_belief'?copy('Expectativa de automatización','Automation belief'):copy('Dificultad con instrucciones','Instruction difficulty')}</h4><code className="text-xs">{id}</code>
        {answer.type==='noul'?<p>{copy('Probabilidad asignada a la afirmación textual','Model-assigned probability of the textual statement')}: {answer.noul}</p>:<><p>{copy('Categoría','Category')}: {answer.choice}</p><p>{copy('Confianza informada por el modelo','Model-reported confidence')}: {answer.confidence}</p><table className="w-full text-left"><caption>{copy('Distribución completa','Complete distribution')}</caption><thead><tr><th>{copy('Categoría','Category')}</th><th>{copy('Probabilidad','Probability')}</th></tr></thead><tbody>{Object.entries(answer.probabilities??{}).map(([key,p])=><tr key={key}><th scope="row">{key}</th><td>{p}</td></tr>)}</tbody></table></>}
      </article>)}
      <p>{copy('Latencia (ms)','Latency (ms)')}: {result.latency_ms}</p><p className="break-all text-xs">{result.raw_response_hash}</p>
      <Button disabled={busy||!reviewer.trim()} onClick={()=>void action(()=>downloadInference(run!.id,reviewer))}>{copy('Exportar inferencia separada','Export separate inference')}</Button>
    </>}
    {run&&!blinded&&<><Button disabled={busy||!reviewer.trim()||reviewOffset===null} onClick={()=>void action(loadReviews)}>{copy('Ver historial de etiquetas y desacuerdos','View label and disagreement history')}</Button>{history.map(h=><article className="rounded border border-border p-2" key={h.id}><p>{h.reviewer} · {h.activity==='blinded_reference'?copy('Referencia ciega','Blinded reference'):copy('Adjudicación','Adjudication')} · {h.created_at_ns}</p><dl>{Object.entries(JSON.parse(h.content_json) as Record<string,string>).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl></article>)}</>}
    {notice&&<p role="status">{notice}</p>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
