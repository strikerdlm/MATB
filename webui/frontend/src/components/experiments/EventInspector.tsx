import { Trash2 } from "lucide-react";
import React from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EXPERIMENT_TASKS, MAX_EXPERIMENT_DURATION_SECONDS } from "@/lib/experiment-designer";
import type { ExperimentTimelineEvent } from "@/types";

interface EventInspectorProps {
  event: ExperimentTimelineEvent | null;
  onChange: (event: ExperimentTimelineEvent) => void;
  onRemove: (eventKey: string) => void;
}

function parseValue(value: string): string | boolean | number | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  if (trimmed === "true") return true;
  if (trimmed === "false") return false;
  const numeric = Number(trimmed);
  return Number.isFinite(numeric) ? numeric : trimmed;
}

export function EventInspector({ event, onChange, onRemove }: EventInspectorProps) {
  if (event === null) {
    return (
      <aside className="border border-white/15 bg-black/30 p-5" aria-label="Event inspector">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Event inspector</p>
        <p className="mt-5 text-sm leading-6 text-muted-foreground">
          Select a timeline event to edit its deterministic source specification.
        </p>
      </aside>
    );
  }

  return (
    <aside className="border border-white/15 bg-black/30 p-5" aria-label="Event inspector">
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Event inspector</p>
      <div className="mt-5 space-y-4">
        <div className="space-y-2">
          <Label htmlFor="event-time">Time (seconds)</Label>
          <Input
            id="event-time"
            type="number"
            min={0}
            max={MAX_EXPERIMENT_DURATION_SECONDS}
            step={1}
            value={event.atSeconds}
            onChange={(change) => onChange({ ...event, atSeconds: Number(change.target.value) })}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="event-duration">Duration (seconds)</Label>
          <Input
            id="event-duration"
            type="number"
            min={1}
            max={MAX_EXPERIMENT_DURATION_SECONDS}
            step={1}
            value={event.durationSeconds ?? ""}
            placeholder="Instantaneous"
            onChange={(change) => onChange({
              ...event,
              durationSeconds: change.target.value === "" ? null : Number(change.target.value),
            })}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="event-task">Task</Label>
          <select
            id="event-task"
            className="native-select w-full"
            value={event.task}
            onChange={(change) => onChange({ ...event, task: change.target.value })}
          >
            {EXPERIMENT_TASKS.map((task) => <option key={task} value={task}>{task}</option>)}
          </select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="event-command">Event command</Label>
          <Input
            id="event-command"
            value={event.command}
            onChange={(change) => onChange({ ...event, command: change.target.value })}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="event-value">Value (optional)</Label>
          <Input
            id="event-value"
            value={event.value === undefined ? "" : String(event.value)}
            onChange={(change) => onChange({ ...event, value: parseValue(change.target.value) })}
          />
        </div>
      </div>
      <Button
        type="button"
        variant="outline"
        className="mt-6 w-full border-danger/70 text-danger hover:border-danger hover:bg-danger/10"
        onClick={() => onRemove(event.eventKey)}
      >
        <Trash2 className="mr-2 h-4 w-4" />
        Remove event
      </Button>
    </aside>
  );
}
