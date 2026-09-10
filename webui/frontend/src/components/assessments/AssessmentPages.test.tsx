import React from 'react';
import {act, cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import PvtPage from '@/app/pvt/page';
import ScreenPage from '@/app/screen/page';
import type {Attempt} from '@/lib/assessments';
import * as api from '@/lib/api';
import * as assessments from '@/lib/assessments';
const controls = vi.hoisted(() => ({purpose: 'study' as 'study' | 'practice', select: null as null | ((a: Attempt | null) => void)}));
vi.mock('@/lib/execution-purpose', () => ({useExecutionPurpose: () => controls.purpose}));
vi.mock('@/lib/i18n', () => ({useAppLocale: () => ({locale: 'en', copy: (_es: string, en: string) => en})}));
vi.mock('@/lib/console-context', () => ({useConsole: () => ({catalog: []})}));
vi.mock('@/lib/experiment-flow', () => ({useReportExperimentFlow: () => {}, flowStageForPvt: () => '', flowStageForScreen: () => ''}));
vi.mock('@/components/experiments/ExperimentGuide', () => ({ExperimentGuide: () => null, ExecutionPurposeBadge: () => null}));
vi.mock('@/components/instructions/InstructionAudio', () => ({InstructionAudio: () => null}));
vi.mock('@/components/layout/PageHeader', () => ({PageHeader: () => null}));
vi.mock('@/components/assessments/AssessmentPicker', () => ({AssessmentPicker: ({onSelect, disabled}: {onSelect: (a: Attempt | null) => void; disabled?: boolean}) => {
  controls.select = onSelect;
  return <button disabled={disabled} onClick={() => onSelect({id: 'attempt-A', occasion_id: 'occasion-A', execution_purpose: 'study', acquisition_state: 'created'} as Attempt)}>Choose attempt A</button>;
}}));
vi.mock('@/components/pvt/PvtRunner', () => ({PvtRunner: ({onComplete}: {onComplete: (r: unknown) => void}) => <button onClick={() => onComplete({durationMs: 600000, administeredAt: '2026-09-10T12:00:00Z', trials: [], interruptionCount: 0, maxFrameGapMs: 0, terminalPhase: 'complete', terminalStimulusAtMs: null})}>Complete PVT</button>}));
vi.mock('next/dynamic', () => ({default: () => function ScreenRunner({onComplete}: {onComplete: (r: unknown) => void}) {return <button onClick={() => onComplete({schema_version: 2, administered_at: '2026-09-10T12:00:00Z', simple_rt: {}, choice_rt: {}, nback: {}, tracking: {}})}>Complete screen</button>;}}));
vi.mock('@/lib/assessments', () => ({startAttempt: vi.fn()}));
vi.mock('@/lib/api', () => ({
  listParticipants: async () => [{id: 'P01'}, {id: 'P02'}],
  listVisits: async (participant: string) => [{id: participant === 'P01' ? 7 : 8, visit_ordinal: 1, scheduled_day: 0}],
  getPvtSummary: async () => ({assessments: []}), postPvt: vi.fn(), postScreen: vi.fn(),
}));
beforeEach(() => {controls.purpose = 'study'; controls.select = null; vi.clearAllMocks();});
afterEach(cleanup);

async function choose(kind: 'pvt' | 'screen') {
  const participant = await screen.findByLabelText(kind === 'pvt' ? 'Participant' : 'Your participant code');
  await waitFor(() => expect(screen.getByRole('option', {name: 'P01'})).toBeInTheDocument());
  fireEvent.change(participant, {target: {value: 'P01'}});
  await waitFor(() => expect(screen.getByLabelText('Visit')).toHaveValue(kind === 'pvt' ? '1' : '7'));
  fireEvent.click(screen.getByRole('button', {name: 'Choose attempt A'}));
  return participant;
}

it.each(['pvt', 'screen'] as const)('%s ignores a stale start response and locks context controls while admitting', async kind => {
  let resolveStart!: (a: Attempt) => void;
  vi.mocked(assessments.startAttempt).mockImplementation(() => new Promise(resolve => {resolveStart = resolve;}));
  render(kind === 'pvt' ? <PvtPage /> : <ScreenPage />);
  const participant = await choose(kind);
  fireEvent.click(screen.getByRole('button', {name: kind === 'pvt' ? 'Continue to KSS' : 'View instructions and begin'}));
  await waitFor(() => expect(resolveStart).toBeTypeOf('function'));
  expect(participant).toBeDisabled();
  expect(screen.getByLabelText('Visit')).toBeDisabled();
  expect(screen.getByRole('button', {name: 'Choose attempt A'})).toBeDisabled();
  // A late external/context update must also invalidate admission, even though
  // ordinary user changes are prevented by the disabled selection controls.
  fireEvent.change(participant, {target: {value: 'P02'}});
  await act(async () => {resolveStart({id: 'attempt-A', acquisition_state: 'started'} as Attempt);});
  expect(screen.queryByRole('radio')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', {name: 'Complete screen'})).not.toBeInTheDocument();
  expect(participant).toHaveValue('P02');
  expect(api.postPvt).not.toHaveBeenCalled();
  expect(api.postScreen).not.toHaveBeenCalled();
});

it.each(['pvt', 'screen'] as const)('%s saves and retries with the admitted immutable context', async kind => {
  vi.mocked(assessments.startAttempt).mockResolvedValue({id: 'attempt-A', acquisition_state: 'started'} as Attempt);
  vi.mocked(api.postPvt).mockRejectedValueOnce(new Error('offline')).mockResolvedValue({id: 42, kss_score: 3, protocol_valid: false, metrics: {median_rt_ms: null, lapses: 0, false_starts: 0}} as never);
  vi.mocked(api.postScreen).mockRejectedValueOnce(new Error('offline')).mockResolvedValue({participant_id: 'P01', screen_version: 2, scores: {}});
  const view = render(kind === 'pvt' ? <PvtPage /> : <ScreenPage />);
  await choose(kind);
  fireEvent.click(screen.getByRole('button', {name: kind === 'pvt' ? 'Continue to KSS' : 'View instructions and begin'}));
  if (kind === 'pvt') {
    const radios = await screen.findAllByRole('radio'); fireEvent.click(radios[2]);
    fireEvent.click(screen.getByRole('button', {name: 'Confirm KSS and view PVT instructions'}));
    fireEvent.click(screen.getByRole('button', {name: 'I am ready'}));
  }
  await screen.findByRole('button', {name: kind === 'pvt' ? 'Complete PVT' : 'Complete screen'});
  controls.purpose = 'practice';
  act(() => controls.select?.(null));
  view.rerender(kind === 'pvt' ? <PvtPage /> : <ScreenPage />);
  fireEvent.click(screen.getByRole('button', {name: kind === 'pvt' ? 'Complete PVT' : 'Complete screen'}));
  fireEvent.click(await screen.findByRole('button', {name: 'Retry saving'}));
  await waitFor(() => expect(kind === 'pvt' ? api.postPvt : api.postScreen).toHaveBeenCalledTimes(2));
  if (kind === 'pvt') {
    for (const [payload] of vi.mocked(api.postPvt).mock.calls) expect(payload).toMatchObject({attempt_id: 'attempt-A', participant_id: 'P01', visit_ordinal: 1, execution_purpose: 'study', kss_score: 3, locale: 'en'});
    expect(vi.mocked(api.postPvt).mock.calls[0][0]).toEqual(vi.mocked(api.postPvt).mock.calls[1][0]);
  } else {
    for (const [participant, , , purpose, attemptId] of vi.mocked(api.postScreen).mock.calls) expect([participant, purpose, attemptId]).toEqual(['P01', 'study', 'attempt-A']);
    expect(vi.mocked(api.postScreen).mock.calls[0]).toEqual(vi.mocked(api.postScreen).mock.calls[1]);
  }
});
