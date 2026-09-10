import React, {useState} from 'react';
import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {AssessmentPicker} from './AssessmentPicker';
import type {Attempt} from '@/lib/assessments';
vi.mock('@/lib/i18n', () => ({useAppLocale: () => ({copy: (_es: string, en: string) => en})}));
afterEach(() => vi.unstubAllGlobals());
it('reopens exact saved evidence and prepares a reasoned repeat without selecting the completed run', async () => {
  const original = {id: 'attempt-original', occasion_id: 'occasion-1', ordinal: 1, execution_purpose: 'study', acquisition_state: 'finished'};
  const next = {...original, id: 'attempt-repeat', ordinal: 2, acquisition_state: 'created'};
  let repeated = false;
  vi.stubGlobal('fetch', vi.fn(async (url: string, options?: RequestInit) => {
    let result: unknown;
    if (url.includes('/occasions?')) result = [{id: 'occasion-1', participant_id: 'P01', visit_id: 7, instrument: 'screen', phase: 'post', order: 3}];
    else if (url.endsWith('/occasions/occasion-1/attempts')) result = repeated ? [original, next] : [original];
    else if (url.endsWith('/attempts/attempt-original/raw')) result = {attempt: original, record: {id: 42, raw_trials_json: 'original observations'}};
    else if (url.endsWith('/attempts/attempt-original/repeat')) {expect(JSON.parse(String(options?.body))).toEqual({execution_purpose: 'study', reason: 'connection restored'}); repeated = true; result = next;}
    else throw new Error(`Unexpected request ${url}`);
    return new Response(JSON.stringify(result));
  }));
  function Harness() {const [selected, setSelected] = useState<Attempt | null>(null); return <><AssessmentPicker participantId="P01" visitId={7} instrument="screen" purpose="study" onSelect={setSelected} /><output>{selected?.id ?? 'none selected'}</output></>;}
  render(<Harness />);
  await screen.findByRole('option', {name: /post/});
  fireEvent.change(screen.getByLabelText('Occasion'), {target: {value: 'occasion-1'}});
  fireEvent.click(await screen.findByRole('button', {name: 'Reopen'}));
  await screen.findByText(/original observations/);
  expect(screen.getByRole('status')).toHaveTextContent('none selected');
  expect(screen.getByRole('button', {name: 'Repeat with reason'})).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Repeat reason'), {target: {value: 'connection restored'}});
  fireEvent.click(screen.getByRole('button', {name: 'Repeat with reason'}));
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('attempt-repeat'));
  expect(screen.getByText(/Attempt 1/)).toBeInTheDocument();
  expect(screen.getByText(/Attempt 2/)).toBeInTheDocument();
});

it('does not select an old context after an in-flight occasion creation', async () => {
  let resolveCreate!: (value: Response) => void;
  vi.stubGlobal('fetch', vi.fn(async (url: string, options?: RequestInit) => {
    if (url.includes('/occasions?')) return new Response('[]');
    if (url.endsWith('/occasions') && options?.method === 'POST') return new Promise<Response>(resolve => {resolveCreate = resolve;});
    if (url.endsWith('/attempts')) return new Response(JSON.stringify({id: 'stale-attempt', occasion_id: 'old-occasion', ordinal: 1, execution_purpose: 'practice', acquisition_state: 'created'}));
    throw new Error(url);
  }));
  function Harness({visit}: {visit: number}) {const [selected, setSelected] = useState<Attempt | null>(null); return <><AssessmentPicker participantId="P01" visitId={visit} instrument="pvt" purpose="practice" onSelect={setSelected} /><output>{selected?.id ?? 'none selected'}</output></>;}
  const view = render(<Harness visit={7} />);
  fireEvent.change(screen.getByLabelText('Phase'), {target: {value: 'post'}});
  fireEvent.click(screen.getByRole('button', {name: 'Prepare occasion'}));
  await waitFor(() => expect(resolveCreate).toBeTypeOf('function'));
  view.rerender(<Harness visit={8} />);
  resolveCreate(new Response(JSON.stringify({id: 'old-occasion', participant_id: 'P01', visit_id: 7, instrument: 'pvt', phase: 'post', order: 1})));
  await waitFor(() => expect(screen.getByRole('button', {name: 'Prepare occasion'})).toBeEnabled());
  expect(screen.getByRole('status')).toHaveTextContent('none selected');
});

it.each(['withdrawal', 'operator_stop', 'hardware_failure', 'software_failure', 'planned_interruption', 'unknown'])('records the explicitly selected interruption cause %s', async category => {
  let interrupted: string | null = null;
  vi.stubGlobal('fetch', vi.fn(async (url: string, options?: RequestInit) => {
    if (url.includes('/occasions?')) return new Response(JSON.stringify([{id: 'occasion-1', participant_id: 'P01', visit_id: 7, instrument: 'pvt', phase: 'post', order: 1}]));
    if (url.endsWith('/attempts')) return new Response(JSON.stringify([{id: 'attempt-A', ordinal: 1, execution_purpose: 'study', acquisition_state: interrupted ? 'interrupted' : 'started'}]));
    if (url.endsWith('/interrupt')) {interrupted = JSON.parse(String(options?.body)).category; return new Response('{}');}
    throw new Error(url);
  }));
  const select = vi.fn();
  render(<AssessmentPicker participantId="P01" visitId={7} instrument="pvt" purpose="study" onSelect={select} />);
  await screen.findByRole('option', {name: /post/});
  fireEvent.change(screen.getByLabelText('Occasion'), {target: {value: 'occasion-1'}});
  const button = await screen.findByRole('button', {name: 'Record interruption'});
  expect(button).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Interruption cause'), {target: {value: category}});
  fireEvent.click(button);
  await waitFor(() => expect(interrupted).toBe(category));
});

it('retains the assigned URL attempt when its visit arrives after the attempt response',async()=>{
 const selected=vi.fn();
 const assigned={id:'assigned-url',occasion_id:'assigned-occasion',ordinal:1,execution_purpose:'study',acquisition_state:'created',assignment_context:{participant_id:'P01',visit_id:7,instrument:'pvt',locale:'en'}};
 window.history.replaceState(null,'','/?attempt=assigned-url');
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>new Response(JSON.stringify(url.includes('/attempts/assigned-url')?assigned:[]))));
 const view=render(<AssessmentPicker participantId="P01" visitId={null} instrument="pvt" purpose="study" onSelect={selected}/>);
 await waitFor(()=>expect(fetch).toHaveBeenCalled());
 view.rerender(<AssessmentPicker participantId="P01" visitId={7} instrument="pvt" purpose="study" onSelect={selected}/>);
 await waitFor(()=>expect(selected).toHaveBeenLastCalledWith(assigned));
 window.history.replaceState(null,'','/');
});
