"use client";

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { createAttempt } from '@/lib/assessments';
import { assignmentDetail, studyCall, type AssignmentDetail, type StudyOccasion } from '@/lib/study';
import { getPolarCapture } from '@/lib/physiology/api';

/** Open only the authored companion for this exact native occasion. */
export function StudyPolarAccompaniment({ detail, companion, onReady, copy }: {
  detail: AssignmentDetail; companion: StudyOccasion; onReady: (state: { key: string; ready: boolean }) => void;
  copy: (es: string, en: string) => string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [recording, setRecording] = useState(false);
  const source = detail.attempts[companion.accompanying_key!]?.flatMap(a => a.sources)
    .filter(s => s.source_table === 'openmatb_suite_session') ?? [];
  const nativeSessionId = source.length === 1 ? source[0].source_id : null;
  useEffect(() => {
    let active = true;
    async function refresh() {
      try {
        const latest = await assignmentDetail(detail.assignment.id);
        const attempts = latest.attempts[companion.key] ?? [];
        const ids = attempts.flatMap(a => a.sources).filter(s => s.source_table === 'polar_capture');
        const capture = ids.length === 1 ? await getPolarCapture(ids[0].source_id) : null;
        const ready = capture?.lifecycle === 'capturing' && capture.participant_pseudonym === detail.assignment.participant_id
          && nativeSessionId !== null && capture.matb_session_id === nativeSessionId;
        if (active) { setRecording(ready); onReady({ key: companion.key, ready }); }
      } catch { if (active) { setRecording(false); onReady({ key: companion.key, ready: false }); } }
    }
    void refresh();
    const timer = setInterval(() => void refresh(), 2000);
    return () => { active = false; clearInterval(timer); };
  }, [detail.assignment.id, detail.assignment.participant_id, companion.key, onReady, nativeSessionId]);
  async function open() {
    setBusy(true); setError('');
    try {
      const latest = await assignmentDetail(detail.assignment.id);
      const rows = latest.attempts[companion.key] ?? [];
      if (rows.length > 1) throw new Error(copy('Seleccione el intento Polar exacto en Evaluaciones asignadas.', 'Select the exact Polar attempt in Assigned assessments.'));
      const attempt = rows[0] ?? await createAttempt(latest.occasions[companion.key], 'study');
      if (attempt.acquisition_state === 'created' && companion.prerequisite_keys.length) {
        const selections: Record<string, string> = {};
        for (const key of companion.prerequisite_keys) {
          const previous = latest.attempts[key]?.filter(a => a.acquisition_state === 'finished') ?? [];
          if (previous.length !== 1) throw new Error(copy('Revise el intento previo exacto antes de captar Polar.', 'Review the exact previous attempt before recording Polar.'));
          selections[key] = previous[0].id;
        }
        await studyCall(`/attempts/${attempt.id}/prerequisites`, { selections });
      }
      router.push(`/physiology/polar-h10?purpose=study&attempt=${encodeURIComponent(attempt.id)}`);
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }
  return <section className="space-y-3 rounded border border-info/30 p-4">
    <h3 className="font-semibold">Polar H10 · {recording ? copy('Capturando', 'Recording') : copy('Preparar captura del bloque', 'Prepare block recording')}</h3>
    <p className="text-sm">{copy('Inicie el Polar de esta persona antes de liberar la tarea. En el primer bloque, complete 5 min de reposo pre-tarea. Mantenga la captura durante el bloque y sus valoraciones; deténgala antes de la pausa.', 'Start this person’s Polar before releasing the task. Before the first block, complete 5 min of pre-task rest. Keep recording during the block and its ratings; stop before the break.')}</p>
    <Button variant="outline" disabled={busy || source.length !== 1} onClick={() => void open()}>{copy('Abrir captura Polar del bloque', 'Open block Polar recording')}</Button>
    {error && <p role="alert">{error}</p>}
  </section>;
}
