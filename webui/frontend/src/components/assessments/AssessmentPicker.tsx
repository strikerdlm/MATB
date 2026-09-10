"use client";
import Link from 'next/link';
import { useAssignedAttempt } from '@/lib/assigned-attempt';
import { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { useAppLocale } from '@/lib/i18n';
import { createAttempt, createOccasion, getAttemptRaw, interruptAttempt, listAttempts, listOccasions, repeatAttempt, type Attempt, type Instrument, type Occasion, type InterruptionCategory } from '@/lib/assessments';

/** Admission is deliberately outside stimulus timing. The parent awaits startAttempt. */
export function AssessmentPicker({participantId, visitId, instrument, purpose, onSelect, disabled = false}: {participantId: string; visitId: number | null; instrument: Instrument; purpose: 'study' | 'practice' | null; onSelect: (attempt: Attempt | null) => void; disabled?: boolean}) {
  const {copy} = useAppLocale();
  const assigned = useAssignedAttempt();
  const context = `${participantId}:${visitId}:${instrument}:${purpose}`;
  const contextRef = useRef(context);
  contextRef.current = context;
  const current = () => contextRef.current === context;
  const [occasions, setOccasions] = useState<Occasion[]>([]);
  const [occasionId, setOccasionId] = useState('');
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [phase, setPhase] = useState('');
  const [order, setOrder] = useState(1);
  const [reason, setReason] = useState('');
  const [interruptionCause, setInterruptionCause] = useState<InterruptionCategory | ''>('');
  const [raw, setRaw] = useState<unknown>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { let active = true; setOccasionId(''); setAttempts([]); setRaw(null); setInterruptionCause(''); onSelect(null);
    if (participantId) void listOccasions(participantId, instrument).then(rows => {if(active) setOccasions(rows);}).catch(e => {if(active) setError(String(e));});
    else setOccasions([]);
    return () => {active = false;};
    // The callback is a React state setter; context changes invalidate the selection.
  }, [participantId, visitId, instrument, purpose, onSelect]);
  useEffect(() => {if (assigned.attempt && assigned.context?.participant_id === participantId && assigned.context.visit_id === visitId && assigned.context.instrument === instrument && purpose === 'study') onSelect(assigned.attempt);}, [assigned.attempt, assigned.context, participantId, visitId, instrument, purpose, onSelect]);
  async function run(action: () => Promise<void>) {setBusy(true); setError(''); try {await action();} catch(e) {setError(e instanceof Error ? e.message : String(e));} finally {setBusy(false);}}
  async function open(value: string) {setInterruptionCause(''); setOccasionId(value); onSelect(null); setRaw(null); const rows = value ? await listAttempts(value) : []; if (current()) setAttempts(rows);}
  return <fieldset disabled={disabled || busy} className="space-y-3 rounded border border-white/15 p-4">
    <label className="block">{copy('Ocasión', 'Occasion')}
      <select aria-label={copy('Ocasión', 'Occasion')} className="native-select w-full" value={occasionId} disabled={busy} onChange={e => void run(() => open(e.target.value))}>
        <option value="">{copy('Nueva ocasión', 'New occasion')}</option>
        {occasions.filter(o => o.visit_id === visitId || o.visit_id === null).map(o => <option key={o.id} value={o.id}>{o.phase ?? copy('Histórica sin clasificar', 'Unclassified historical')} · {o.order ?? '—'} · {o.id.slice(0, 8)}</option>)}
      </select>
    </label>
    {purpose === 'study' && <Link href="/study/assignments" className="underline">{copy('Seleccionar una evaluación asignada', 'Select an assigned assessment')}</Link>}
    {!occasionId && purpose !== 'study' && <div className="flex flex-wrap gap-3">
      <label>{copy('Fase definida por el investigador', 'Researcher-defined phase')}<input aria-label="Phase" className="native-input block" value={phase} onChange={e => setPhase(e.target.value)} /></label>
      <label>{copy('Orden', 'Order')}<input aria-label="Order" type="number" min={1} className="native-input block" value={order} onChange={e => setOrder(Number(e.target.value))} /></label>
      <Button disabled={busy || !purpose || !participantId || !visitId || !phase.trim() || order < 1} onClick={() => void run(async () => {const o = await createOccasion({participant_id: participantId, visit_id: visitId!, instrument, phase, order}); if (!current()) return; setOccasions(prev => [...prev, o]); setOccasionId(o.id); const a = await createAttempt(o.id, purpose!); if (!current()) return; setAttempts([a]); onSelect(a);})}>{copy('Preparar ocasión', 'Prepare occasion')}</Button>
    </div>}
    {occasionId && attempts.length === 0 && <Button disabled={busy || !purpose} onClick={() => void run(async () => {const a = await createAttempt(occasionId, purpose!); if (!current()) return; setAttempts([a]); onSelect(a);})}>{copy('Preparar intento', 'Prepare attempt')}</Button>}
    {attempts.some(a => ['created', 'started'].includes(a.acquisition_state)) && <label className="block">{copy('Causa de la interrupción', 'Interruption cause')}
      <select className="native-select block" value={interruptionCause} onChange={e => setInterruptionCause(e.target.value as InterruptionCategory | '')}>
        <option value="">{copy('Seleccione la causa conocida', 'Select the known cause')}</option>
        <option value="withdrawal">{copy('Retiro del participante', 'Participant withdrawal')}</option>
        <option value="operator_stop">{copy('Detención por el operador', 'Operator stop')}</option>
        <option value="hardware_failure">{copy('Fallo del equipo', 'Hardware failure')}</option>
        <option value="software_failure">{copy('Fallo del software', 'Software failure')}</option>
        <option value="planned_interruption">{copy('Interrupción planificada', 'Planned interruption')}</option>
        <option value="unknown">{copy('Causa desconocida o no establecida', 'Cause unknown or not established')}</option>
      </select>
    </label>}
    {attempts.map(a => <div key={a.id} className="flex flex-wrap items-center gap-3">
      <span>{copy('Intento', 'Attempt')} {a.ordinal} · {a.acquisition_state} · {a.execution_purpose}</span>
      <Button variant="outline" disabled={busy} onClick={() => void run(async () => {const evidence = await getAttemptRaw(a.id); if (!current()) return; setRaw(evidence); onSelect(a.acquisition_state === 'created' && a.execution_purpose === purpose ? a : null);})}>{copy('Reabrir', 'Reopen')}</Button>
      {a.acquisition_state === 'created' && a.execution_purpose === purpose && <Button disabled={busy} onClick={() => onSelect(a)}>{copy('Usar intento', 'Use attempt')}</Button>}
      {['created', 'started'].includes(a.acquisition_state) && <Button variant="outline" disabled={busy || !interruptionCause} onClick={() => void run(async () => {if (!interruptionCause) return; await interruptAttempt(a.id, interruptionCause); if (!current()) return; await open(occasionId);})}>{copy('Registrar interrupción', 'Record interruption')}</Button>}
      {['finished', 'interrupted', 'unknown'].includes(a.acquisition_state) && <Button disabled={busy || !reason.trim() || !purpose} onClick={() => void run(async () => {const next = await repeatAttempt(a.id, purpose!, reason); const rows = await listAttempts(occasionId); if (!current()) return; setAttempts(rows); onSelect(next); setRaw(null);})}>{copy('Repetir con motivo', 'Repeat with reason')}</Button>}
    </div>)}
    {attempts.length > 0 && <label className="block">{copy('Motivo de repetición', 'Repeat reason')}<input className="native-input block w-full" value={reason} onChange={e => setReason(e.target.value)} /></label>}
    {raw !== null && <details open><summary>{copy('Evidencia guardada', 'Saved evidence')}</summary><pre className="max-h-80 overflow-auto text-xs">{JSON.stringify(raw, null, 2)}</pre></details>}
    {error && <p role="alert">{error}</p>}
  </fieldset>;
}
