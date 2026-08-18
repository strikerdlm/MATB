import type { TrackerCell } from "@/types";

export const LEVELS = ["LOW", "MEDIUM", "HIGH"] as const;

export interface Summary { filled: number; total: number; }

export function summarize(cells: TrackerCell[]): Summary {
  return { filled: cells.filter((c) => c.present).length, total: cells.length };
}

export interface ParticipantRow {
  participantId: string;
  cells: TrackerCell[];   // ordered by protocol visit, then LOW/MEDIUM/HIGH
  filled: number;
  total: number;
}

const levelRank: Record<string, number> = { LOW: 0, MEDIUM: 1, HIGH: 2 };

export function byParticipant(cells: TrackerCell[]): ParticipantRow[] {
  const groups = new Map<string, TrackerCell[]>();
  for (const c of cells) {
    if (!groups.has(c.participant_id)) groups.set(c.participant_id, []);
    groups.get(c.participant_id)!.push(c);
  }
  const ids = Array.from(groups.keys()).sort();
  return ids.map((participantId) => {
    const sorted = groups.get(participantId)!.slice().sort((a, b) =>
      a.visit_ordinal - b.visit_ordinal || levelRank[a.workload_level] - levelRank[b.workload_level]
    );
    return {
      participantId,
      cells: sorted,
      filled: sorted.filter((c) => c.present).length,
      total: sorted.length,
    };
  });
}
