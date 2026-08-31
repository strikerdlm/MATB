import type {
  ExperimentSpec,
  ExperimentSummary,
  ExperimentTimelineEvent,
  TimelineConstraint,
} from "@/types";

const NANOSECONDS_PER_SECOND = 1_000_000_000;
export const MAX_EXPERIMENT_DURATION_SECONDS = 86_400;
export const MAX_SAFE_EXPERIMENT_SEED = Number.MAX_SAFE_INTEGER;
const COMM_RESPONSE_AVAILABILITY_SECONDS = 44;
const COMM_MIN_ONSET_SEPARATION_SECONDS = 45;

const LIFECYCLE_COMMANDS = new Set(["start", "stop"]);
const SYSMON_FAILURE_COMMANDS = new Set([
  "lights-1-failure",
  "lights-2-failure",
  "scales-1-failure",
  "scales-2-failure",
  "scales-3-failure",
  "scales-4-failure",
]);
const SUPPORTED_COMMANDS: Record<string, ReadonlySet<string>> = {
  sysmon: new Set([...LIFECYCLE_COMMANDS, ...SYSMON_FAILURE_COMMANDS, "open_nontarget_opportunity"]),
  communications: new Set([...LIFECYCLE_COMMANDS, "radioprompt"]),
  track: LIFECYCLE_COMMANDS,
  resman: LIFECYCLE_COMMANDS,
};

export const EXPERIMENT_TASKS = [
  "sysmon",
  "communications",
  "track",
  "resman",
] as const;

export function compareUnicodeCodePoints(first: string, second: string): number {
  const left = Array.from(first, (character) => character.codePointAt(0) as number);
  const right = Array.from(second, (character) => character.codePointAt(0) as number);
  const common = Math.min(left.length, right.length);
  for (let index = 0; index < common; index += 1) {
    if (left[index] !== right[index]) return left[index] - right[index];
  }
  return left.length - right.length;
}

export const INITIAL_EXPERIMENT_EVENTS: ExperimentTimelineEvent[] = [
  { eventKey: "sysmon-start", atSeconds: 0, durationSeconds: null, task: "sysmon", command: "start" },
  { eventKey: "comm-start", atSeconds: 0, durationSeconds: null, task: "communications", command: "start" },
  { eventKey: "track-start", atSeconds: 0, durationSeconds: null, task: "track", command: "start" },
  { eventKey: "resman-start", atSeconds: 0, durationSeconds: null, task: "resman", command: "start" },
  {
    eventKey: "sysmon-nontarget-1",
    atSeconds: 8,
    durationSeconds: 2,
    task: "sysmon",
    command: "open_nontarget_opportunity",
  },
  {
    eventKey: "sysmon-target-1",
    atSeconds: 24,
    durationSeconds: 10,
    task: "sysmon",
    command: "lights-1-failure",
    value: true,
  },
  {
    eventKey: "comm-prompt-1",
    atSeconds: 10,
    durationSeconds: null,
    task: "communications",
    command: "radioprompt",
    value: "own",
  },
  { eventKey: "sysmon-stop", atSeconds: 59, durationSeconds: null, task: "sysmon", command: "stop" },
  { eventKey: "comm-stop", atSeconds: 59, durationSeconds: null, task: "communications", command: "stop" },
  { eventKey: "track-stop", atSeconds: 59, durationSeconds: null, task: "track", command: "stop" },
  { eventKey: "resman-stop", atSeconds: 59, durationSeconds: null, task: "resman", command: "stop" },
];

export function summarizeExperiment(
  events: ExperimentTimelineEvent[],
  durationSeconds: number,
): ExperimentSummary {
  let overlapCount = 0;
  const intervals = events.flatMap((event) => {
    const duration = event.durationSeconds ?? (
      event.task === "communications" && event.command === "radioprompt"
        ? COMM_RESPONSE_AVAILABILITY_SECONDS
        : null
    );
    return duration === null
      ? []
      : [{ start: event.atSeconds, end: event.atSeconds + duration }];
  });
  for (let index = 0; index < intervals.length; index += 1) {
    const first = intervals[index];
    for (let otherIndex = index + 1; otherIndex < intervals.length; otherIndex += 1) {
      const second = intervals[otherIndex];
      if (first.start < second.end && second.start < first.end) overlapCount += 1;
    }
  }
  const possiblePairs = (intervals.length * (intervals.length - 1)) / 2;
  const durationMinutes = durationSeconds / 60;
  const stimuli = events.filter((event) => !LIFECYCLE_COMMANDS.has(event.command));
  const countByTask = (selected: ExperimentTimelineEvent[]) => selected.reduce<Record<string, number>>(
    (counts, event) => ({ ...counts, [event.task]: (counts[event.task] ?? 0) + 1 }),
    {},
  );
  const sourceCounts = countByTask(events);
  const stimulusCounts = countByTask(stimuli);
  const rates = (counts: Record<string, number>) => Object.fromEntries(
    Object.entries(counts).map(([task, count]) => [
      task,
      durationMinutes > 0 ? count / durationMinutes : 0,
    ]),
  );
  const stimulusOnsets = stimuli.reduce<Record<string, number[]>>((byTask, event) => {
    (byTask[event.task] ??= []).push(event.atSeconds);
    return byTask;
  }, {});
  const minimumRefractory = Object.fromEntries(Object.entries(stimulusOnsets).map(
    ([task, onsets]) => {
      const ordered = [...onsets].sort((first, second) => first - second);
      const gaps = ordered.slice(1).map((onset, index) => onset - ordered[index]);
      return [task, gaps.length > 0 ? Math.min(...gaps) * 1000 : null];
    },
  ));
  return {
    sourceCommandCount: events.length,
    sourceCommandRatePerMinute: durationMinutes > 0 ? events.length / durationMinutes : 0,
    perTaskSourceCommandRatePerMinute: rates(sourceCounts),
    stimulusOpportunityCount: stimuli.length,
    stimulusOpportunityRatePerMinute: durationMinutes > 0 ? stimuli.length / durationMinutes : 0,
    perTaskStimulusOpportunityRatePerMinute: rates(stimulusCounts),
    minimumStimulusRefractoryMsByTask: minimumRefractory,
    overlapCount,
    overlapPercent: possiblePairs > 0 ? (overlapCount / possiblePairs) * 100 : 0,
    sysmonTargetOpportunities: events.filter((event) => (
      event.task === "sysmon" && event.command.endsWith("-failure")
    )).length,
    sysmonNontargetOpportunities: events.filter((event) => (
      event.task === "sysmon" && event.command === "open_nontarget_opportunity"
    )).length,
  };
}

export function validateTimeline(
  events: ExperimentTimelineEvent[],
  durationSeconds: number,
  seed = 0,
): TimelineConstraint[] {
  const constraints: TimelineConstraint[] = [];
  const integerFields = [durationSeconds, seed, ...events.flatMap((event) => (
    event.durationSeconds === null
      ? [event.atSeconds]
      : [event.atSeconds, event.durationSeconds]
  ))];
  const precise = integerFields.every((value) => Number.isSafeInteger(value));
  constraints.push({
    id: "integer-precision",
    label: "Browser values preserve exact integer nanoseconds",
    status: precise ? "pass" : "fail",
    detail: precise ? "All time and seed values are safe integers" : "Unsafe or fractional time/seed value detected",
  });

  const seedValid = Number.isSafeInteger(seed)
    && seed >= 0
    && seed <= MAX_SAFE_EXPERIMENT_SEED;
  constraints.push({
    id: "seed-range",
    label: "Experiment seed is a non-negative safe integer",
    status: seedValid ? "pass" : "fail",
    detail: seedValid ? `Seed ${seed} is losslessly representable` : "Seed must be between 0 and Number.MAX_SAFE_INTEGER",
  });

  const durationValid = Number.isSafeInteger(durationSeconds)
    && durationSeconds >= 1
    && durationSeconds <= MAX_EXPERIMENT_DURATION_SECONDS;
  const outside = events.filter((event) => (
    event.atSeconds < 0
    || event.atSeconds >= durationSeconds
    || (event.durationSeconds !== null && event.durationSeconds < 1)
    || event.atSeconds + (event.durationSeconds ?? 0) > durationSeconds
  ));
  constraints.push({
    id: "timeline-boundary",
    label: "All events remain inside experiment duration",
    status: outside.length === 0 && durationValid ? "pass" : "fail",
    detail: outside.length === 0 && durationValid
      ? `${events.length} events checked`
      : `${outside.length} events outside duration or invalid duration`,
  });

  const unsafeTokens = events.filter((event) => (
    /[\n\r;]/.test(event.task) || /[\n\r;]/.test(event.command)
  ));
  constraints.push({
    id: "openmatb-delimiters",
    label: "Task and command fields are delimiter-safe",
    status: unsafeTokens.length === 0 ? "pass" : "fail",
    detail: unsafeTokens.length === 0 ? "No ambiguous command tokens" : `${unsafeTokens.length} unsafe commands`,
  });

  const semanticErrors: string[] = [];
  const eventKeys = new Set<string>();
  const active: Record<string, boolean> = Object.fromEntries(EXPERIMENT_TASKS.map((task) => [task, false]));
  const requiredEnd: Record<string, number | null> = Object.fromEntries(EXPERIMENT_TASKS.map((task) => [task, null]));
  const prompts: ExperimentTimelineEvent[] = [];
  const timedByTask: Record<string, ExperimentTimelineEvent[]> = {};
  const ordered = [...events].sort((first, second) => (
    first.atSeconds - second.atSeconds || compareUnicodeCodePoints(first.eventKey, second.eventKey)
  ));
  for (const event of ordered) {
    if (eventKeys.has(event.eventKey)) semanticErrors.push(`duplicate event key ${event.eventKey}`);
    eventKeys.add(event.eventKey);
    const supported = SUPPORTED_COMMANDS[event.task];
    if (!supported || !supported.has(event.command)) {
      semanticErrors.push(`unsupported ${event.task}.${event.command}`);
      continue;
    }
    const hasValue = event.value !== undefined;
    const needsDuration = event.task === "sysmon"
      && (event.command === "open_nontarget_opportunity" || SYSMON_FAILURE_COMMANDS.has(event.command));
    if (needsDuration !== (event.durationSeconds !== null)) {
      semanticErrors.push(`${event.eventKey} has invalid duration semantics`);
    }
    if (LIFECYCLE_COMMANDS.has(event.command) && hasValue) {
      semanticErrors.push(`${event.eventKey} lifecycle command has a value`);
    } else if (event.command === "open_nontarget_opportunity" && hasValue) {
      semanticErrors.push(`${event.eventKey} non-target opportunity has a value`);
    } else if (SYSMON_FAILURE_COMMANDS.has(event.command) && event.value !== true) {
      semanticErrors.push(`${event.eventKey} failure value is not true`);
    } else if (event.command === "radioprompt" && !["own", "other"].includes(String(event.value))) {
      semanticErrors.push(`${event.eventKey} prompt value is not own/other`);
    }

    if (event.command === "start") {
      if (active[event.task]) semanticErrors.push(`${event.task} starts twice`);
      active[event.task] = true;
      requiredEnd[event.task] = null;
    } else if (event.command === "stop") {
      if (!active[event.task]) semanticErrors.push(`${event.task} stops while inactive`);
      if (requiredEnd[event.task] !== null && event.atSeconds <= (requiredEnd[event.task] ?? 0)) {
        semanticErrors.push(`${event.task} stops before evidence closes`);
      }
      active[event.task] = false;
      requiredEnd[event.task] = null;
    } else if (!active[event.task]) {
      semanticErrors.push(`${event.eventKey} runs before ${event.task} starts`);
    } else {
      const eventEnd = event.command === "radioprompt"
        ? event.atSeconds + COMM_RESPONSE_AVAILABILITY_SECONDS
        : event.atSeconds + (event.durationSeconds ?? 0);
      requiredEnd[event.task] = Math.max(requiredEnd[event.task] ?? eventEnd, eventEnd);
    }
    if (event.command === "radioprompt") prompts.push(event);
    if (event.durationSeconds !== null) {
      (timedByTask[event.task] ??= []).push(event);
    }
  }
  for (const task of EXPERIMENT_TASKS) {
    if (active[task]) semanticErrors.push(`${task} has no matching stop`);
  }
  prompts.sort((first, second) => first.atSeconds - second.atSeconds);
  for (let index = 1; index < prompts.length; index += 1) {
    if (prompts[index].atSeconds - prompts[index - 1].atSeconds < COMM_MIN_ONSET_SEPARATION_SECONDS) {
      semanticErrors.push("communications prompts violate the verified onset separation");
    }
  }
  for (const [task, timed] of Object.entries(timedByTask)) {
    timed.sort((first, second) => first.atSeconds - second.atSeconds);
    for (let index = 1; index < timed.length; index += 1) {
      const previousEnd = timed[index - 1].atSeconds + (timed[index - 1].durationSeconds ?? 0);
      if (timed[index].atSeconds < previousEnd) semanticErrors.push(`${task} timed events overlap`);
    }
  }
  constraints.push({
    id: "runtime-semantics",
    label: "Events are losslessly representable by the runtime compiler",
    status: semanticErrors.length === 0 ? "pass" : "fail",
    detail: semanticErrors.length === 0 ? "Commands, lifecycles, and evidence windows checked" : semanticErrors[0],
  });

  const summary = summarizeExperiment(events, durationSeconds);
  constraints.push({
    id: "sysmon-denominator",
    label: "SYSMON has explicit target-absent opportunities",
    status: summary.sysmonNontargetOpportunities > 0 ? "pass" : "warning",
    detail: `${summary.sysmonNontargetOpportunities} non-target / ${summary.sysmonTargetOpportunities} target`,
  });
  constraints.push({
    id: "workload-claim",
    label: "Workload labels remain engineering presets",
    status: "warning",
    detail: "Human calibration evidence is not inferred by this editor",
  });
  return constraints;
}

export function buildExperimentSpec(
  events: ExperimentTimelineEvent[],
  durationSeconds: number,
  seed: number,
): ExperimentSpec {
  const numericValues = [durationSeconds, seed, ...events.flatMap((event) => (
    event.durationSeconds === null ? [event.atSeconds] : [event.atSeconds, event.durationSeconds]
  ))];
  if (!numericValues.every((value) => Number.isSafeInteger(value))) {
    throw new RangeError("Experiment times and seed must be safe integers");
  }
  if (seed < 0 || seed > MAX_SAFE_EXPERIMENT_SEED) {
    throw new RangeError("Experiment seed must be a non-negative safe integer");
  }
  return {
    schema_version: "1.0",
    experiment_id: "console-designer",
    revision: 1,
    title: "Research Console experiment",
    seed,
    profile_id: "MATB-EXTENDED-2.0",
    duration_ns: durationSeconds * NANOSECONDS_PER_SECOND,
    components: ["matb-runtime"],
    timeline: events.map((event) => {
      const parameters: Record<string, string | number | boolean> = {
        command: event.command,
      };
      if (event.value !== undefined) {
        parameters.value = event.value;
      }
      return {
        event_key: event.eventKey,
        at_ns: event.atSeconds * NANOSECONDS_PER_SECOND,
        duration_ns: event.durationSeconds === null
          ? null
          : event.durationSeconds * NANOSECONDS_PER_SECOND,
        component_id: "matb-runtime",
        task: event.task,
        event_type: "openmatb.command" as const,
        parameters,
      };
    }),
    metadata: {
      workload_label_status: "engineering_preset_pending_human_calibration",
    },
  };
}

export function formatTimelineTime(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const remaining = safe % 60;
  return hours > 0
    ? `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(remaining).padStart(2, "0")}`
    : `${String(minutes).padStart(2, "0")}:${String(remaining).padStart(2, "0")}`;
}
