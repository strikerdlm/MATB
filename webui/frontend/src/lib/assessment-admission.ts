"use client";
import {useEffect, useRef, useState} from 'react';
import {startAttempt} from './assessments';

/** Owns the immutable context admitted before any acquisition UI starts. */
export function useAssessmentAdmission<T extends {attemptId: string}>(context: T | null) {
  const current = useRef({context, key: JSON.stringify(context)});
  current.current = {context, key: JSON.stringify(context)};
  const active = useRef(true);
  const pendingRef = useRef(false);
  const [pending, setPending] = useState(false);
  const [admitted, setAdmitted] = useState<Readonly<T> | null>(null);
  useEffect(() => {active.current = true; return () => {active.current = false;};}, []);

  async function admit(): Promise<Readonly<T> | null> {
    if (pendingRef.current || !current.current.context) return null;
    const {context: candidate, key} = current.current;
    const snapshot = Object.freeze({...candidate});
    pendingRef.current = true;
    setPending(true);
    try {
      const response = await startAttempt(snapshot.attemptId);
      if (!active.current || current.current.key !== key) return null;
      if (response.id !== snapshot.attemptId) throw new Error('Admission returned a different attempt identity');
      const requested = snapshot as Readonly<T> & {purpose?: string; locale?: string; participantId?: string; visitId?: number};
      if (requested.purpose === 'study') {
        const bound = response.assignment_context;
        if (!bound || bound.participant_id !== requested.participantId || bound.visit_id !== requested.visitId || (requested.locale && bound.locale !== requested.locale)) throw new Error('Study admission context differs from the selected frozen assignment');
      }
      setAdmitted(snapshot);
      return snapshot;
    } finally {
      pendingRef.current = false;
      if (active.current) setPending(false);
    }
  }
  return {pending, admitted, admit};
}
