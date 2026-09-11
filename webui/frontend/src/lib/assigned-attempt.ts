"use client";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { getAttempt, type Attempt } from "./assessments";
/** Reactive exact identity; stale responses cannot select an earlier URL's attempt. */
export function useAssignedAttempt() {
  const params = useSearchParams();
  const identity = params.get("attempt");
  const [loaded, setLoaded] = useState<{
    identity: string;
    attempt: Attempt;
  } | null>(null);
  const [failure, setFailure] = useState<{
    identity: string;
    message: string;
  } | null>(null);
  useEffect(() => {
    let active = true;
    if (identity)
      void getAttempt(identity)
        .then((attempt) => {
          if (attempt.id !== identity)
            throw new Error("Attempt response identity mismatch");
          if (active) setLoaded({ identity, attempt });
        })
        .catch((error) => {
          if (active) setFailure({ identity, message: String(error) });
        });
    return () => {
      active = false;
    };
  }, [identity]);
  const attempt = loaded?.identity === identity ? loaded.attempt : null;
  return {
    identity,
    attempt,
    context:
      attempt?.assignment_context ?? attempt?.preparation_context ?? null,
    error: failure?.identity === identity ? failure.message : "",
  };
}
