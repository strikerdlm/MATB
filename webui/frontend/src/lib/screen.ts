// Pure, seeded, timing-independent logic for the neurocognitive screen.
// All participant-visible STRINGS live in components/screen/strings_es.ts;
// all SCORING lives in matb_integration/screen (Python). This module only
// generates reproducible trial sequences and assembles the raw payload.

export interface ScreenConfig {
  simpleRtTrials: number;
  choiceRtTrials: number;
  nbackTrials: number;
  nbackTargets: number;
  nbackSoaMs: number;
  trackingSeconds: number;
  practiceTrials: number;
}

export const SCREEN_CONFIG: ScreenConfig = {
  simpleRtTrials: 30, choiceRtTrials: 30,
  nbackTrials: 60, nbackTargets: 18, nbackSoaMs: 2500,
  trackingSeconds: 90, practiceTrials: 5,
};

// e2e/dev only: same logic, fewer trials (enabled via /screen?fast=1)
export const FAST_CONFIG: ScreenConfig = {
  simpleRtTrials: 6, choiceRtTrials: 6,
  nbackTrials: 12, nbackTargets: 4, nbackSoaMs: 1200,
  trackingSeconds: 8, practiceTrials: 2,
};

export const NBACK_LETTERS = ["B", "C", "D", "F", "G", "H", "J", "K", "L", "M"];

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function genSimpleRtIsis(n: number, rng: () => number): number[] {
  return Array.from({ length: n }, () => 1000 + Math.floor(rng() * 2001));
}

export function genChoiceSides(n: number, rng: () => number): ("left" | "right")[] {
  // balanced half/half, shuffled (Fisher-Yates with the seeded rng)
  const sides: ("left" | "right")[] = Array.from(
    { length: n }, (_, i) => (i < Math.ceil(n / 2) ? "left" : "right"));
  for (let i = sides.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [sides[i], sides[j]] = [sides[j], sides[i]];
  }
  return sides;
}

export function genNbackSequence(
  n: number, targets: number, rng: () => number,
): { letters: string[]; isTarget: boolean[] } {
  // choose target indices (>= 2, non-adjacent to keep runs controllable)
  const candidates = Array.from({ length: n - 2 }, (_, i) => i + 2);
  const targetIdx = new Set<number>();
  while (targetIdx.size < targets && candidates.length > 0) {
    const k = candidates.splice(Math.floor(rng() * candidates.length), 1)[0];
    if (!targetIdx.has(k - 1) && !targetIdx.has(k + 1)) targetIdx.add(k);
  }
  const letters: string[] = [];
  for (let i = 0; i < n; i++) {
    if (targetIdx.has(i)) {
      letters.push(letters[i - 2]);
    } else {
      let pick: string;
      do {
        pick = NBACK_LETTERS[Math.floor(rng() * NBACK_LETTERS.length)];
        // avoid accidental targets and 3-letter runs
      } while ((i >= 2 && pick === letters[i - 2]) || (i >= 1 && pick === letters[i - 1]));
      letters.push(pick);
    }
  }
  const isTarget = letters.map((l, i) => i >= 2 && l === letters[i - 2]);
  return { letters, isTarget };
}

// Sum-of-sines pursuit path, bounded by |amplitude| on each axis.
export function targetPosition(tSeconds: number, amplitude: number): { x: number; y: number } {
  const x = amplitude * (0.5 * Math.sin(2 * Math.PI * 0.07 * tSeconds)
    + 0.35 * Math.sin(2 * Math.PI * 0.15 * tSeconds + 1.3)
    + 0.15 * Math.sin(2 * Math.PI * 0.31 * tSeconds + 2.1));
  const y = amplitude * (0.5 * Math.sin(2 * Math.PI * 0.09 * tSeconds + 0.7)
    + 0.35 * Math.sin(2 * Math.PI * 0.19 * tSeconds + 2.6)
    + 0.15 * Math.sin(2 * Math.PI * 0.27 * tSeconds + 4.0));
  return { x, y };
}

// --- raw payload types (mirror matb_integration/screen/scoring.py inputs) ---
export interface RtTrial { rt_ms: number | null; responded: boolean; }
export interface ChoiceTrial extends RtTrial { correct: boolean; }
export interface NbackTrial { is_target: boolean; responded: boolean; shown_at_ms: number | null; }

export interface ScreenPayload {
  seed: number;
  administered_at: string;
  fast_mode: boolean;
  simple_rt: { trials: RtTrial[] };
  choice_rt: { trials: ChoiceTrial[] };
  nback: { trials: NbackTrial[]; soa_ms: number };
  tracking: {
    samples: number[][];           // [t_ms, mouse_x, mouse_y, target_x, target_y]
    n_expected_samples: number;
    path_amplitude_px: number;
  };
}
