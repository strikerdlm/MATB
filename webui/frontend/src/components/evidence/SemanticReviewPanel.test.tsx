import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SemanticReviewPanel } from './SemanticReviewPanel';
import type { EvidenceCapture } from '@/lib/evidence';
import { inferenceRequest } from '@/lib/inference';

vi.mock('@/lib/i18n',()=>({useAppLocale:()=>({copy:(_es:string,en:string)=>en})}));
vi.mock('@/lib/api',()=>({getCapabilities:vi.fn(async()=>({components:[]}))}));
vi.mock('@/lib/inference',async original=>({...await original<typeof import('@/lib/inference')>(),inferenceRequest:vi.fn()}));
const capture={id:'c',runs:[{id:'r',status:'complete'}],reconciliation:{fingerprint:'a'}} as EvidenceCapture;

describe('experimental semantic review',()=>{
  beforeEach(()=>{vi.mocked(inferenceRequest).mockReset();});
  it('stays absent without capability',async()=>{
    render(<SemanticReviewPanel capture={capture}/>);
    expect(screen.queryByText(/Experimental semantic review/)).not.toBeInTheDocument();
  });
  it('keeps source language explicit and requires a reviewed preview',async()=>{
    const {getCapabilities}=await import('@/lib/api');
    vi.mocked(getCapabilities).mockResolvedValueOnce({components:[{component_id:'matb-semantic-review'}]} as never);
    render(<SemanticReviewPanel capture={capture}/>);
    expect(await screen.findByText('Experimental semantic review')).toBeInTheDocument();
    expect(screen.getByLabelText('Source language')).toHaveValue('en');
    fireEvent.change(screen.getByLabelText('Source language'),{target:{value:'es'}});
    expect(screen.getByLabelText('Source language')).toHaveValue('es');
    expect(screen.queryByRole('button',{name:'Authorize and queue'})).not.toBeInTheDocument();
  });
  it('accepts asynchronous previews under React StrictMode',async()=>{
    const {getCapabilities}=await import('@/lib/api');
    vi.mocked(getCapabilities).mockResolvedValue({components:[{component_id:'matb-semantic-review'}]} as never);
    vi.mocked(inferenceRequest).mockResolvedValueOnce({id:'n'}).mockResolvedValueOnce({id:'p',status:'queued'});
    render(<React.StrictMode><SemanticReviewPanel capture={capture}/></React.StrictMode>);
    fireEvent.change(await screen.findByLabelText('Synthetic note'),{target:{value:'A synthetic report.'}});
    fireEvent.click(screen.getByRole('button',{name:'Create preview'}));
    expect(await screen.findByText('Queued')).toBeInTheDocument();
  });
  it('reopens stored attempts without disclosing answers and can revoke queued approval',async()=>{
    const {getCapabilities}=await import('@/lib/api');
    vi.mocked(getCapabilities).mockResolvedValue({components:[{component_id:'matb-semantic-review'}]} as never);
    vi.mocked(inferenceRequest).mockImplementation(async(path)=>{
      if(String(path).startsWith('/inference/annotations?'))return {items:[],next_offset:null};
      if(String(path).startsWith('/inference/runs?'))return {items:[{id:'saved',status:'queued',preview_id:'p'}],next_offset:null};
      if(path==='/inference/runs/saved/revoke')return {prevented_dispatch:true};
      if(path==='/inference/runs/saved')return {id:'saved',status:'queued',preview_id:'p',result_json:null};
      return {id:'p',status:'ready',payload:'exact bytes',preview_hash:'h',lineage:{payload_hash:'hash',evidence_run_id:'r'}};
    });
    render(<SemanticReviewPanel capture={capture}/>);
    fireEvent.click(await screen.findByRole('button',{name:'Load saved reviews'}));
    fireEvent.click(await screen.findByRole('button',{name:/Open attempt saved/}));
    expect(await screen.findByText('exact bytes')).toBeInTheDocument();
    expect(screen.getByRole('button',{name:'Show assessment'})).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Reviewer'),{target:{value:'rater'}});
    fireEvent.change(screen.getByLabelText('Revocation reason'),{target:{value:'Withdraw'}});
    fireEvent.click(screen.getByRole('button',{name:'Revoke approval'}));
    await waitFor(()=>expect(inferenceRequest).toHaveBeenCalledWith('/inference/runs/saved/revoke',expect.anything()));
    expect(await screen.findByText('Approval revoked before dispatch.')).toBeInTheDocument();
  });
  it('rejects stale responses after capture switching',async()=>{
    const {getCapabilities}=await import('@/lib/api');
    vi.mocked(getCapabilities).mockResolvedValue({components:[{component_id:'matb-semantic-review'}]} as never);
    let resolveNote:(value:unknown)=>void=()=>{};
    vi.mocked(inferenceRequest).mockReturnValueOnce(new Promise(resolve=>{resolveNote=resolve;}));
    const view=render(<SemanticReviewPanel capture={capture}/>);
    fireEvent.change(await screen.findByLabelText('Synthetic note'),{target:{value:'Old capture note'}});
    fireEvent.click(screen.getByRole('button',{name:'Create preview'}));
    view.rerender(<SemanticReviewPanel capture={{...capture,id:'other'}}/>);
    vi.mocked(inferenceRequest).mockResolvedValueOnce({id:'old-preview',status:'queued'});
    resolveNote({id:'old-note'});
    await waitFor(()=>expect(screen.getByLabelText('Synthetic note')).toHaveValue(''));
    expect(screen.queryByText('Queued')).not.toBeInTheDocument();
  });
  it('shows blocked source and transport failures without a score',async()=>{
    const {getCapabilities}=await import('@/lib/api');
    vi.mocked(getCapabilities).mockResolvedValue({components:[{component_id:'matb-semantic-review'}]} as never);
    render(<SemanticReviewPanel capture={{...capture,reconciliation:null} as never}/>);
    expect(await screen.findByText('Blocked: completed reconciliation required.')).toBeVisible();
    expect(screen.getByRole('button',{name:'Create preview'})).toBeDisabled();
    vi.mocked(inferenceRequest).mockRejectedValue(new Error('HTTP 503'));
    await act(async()=>{fireEvent.click(screen.getByRole('button',{name:'Load saved reviews'}));});
    expect(await screen.findByRole('alert')).toHaveTextContent('HTTP 503');
    expect(screen.queryByText(/Model-assigned probability/)).not.toBeInTheDocument();
  });
  it('removes exposed reference labels before changing reviewer',async()=>{
    const {getCapabilities}=await import('@/lib/api');
    vi.mocked(getCapabilities).mockResolvedValue({components:[{component_id:'matb-semantic-review'}]} as never);
    vi.mocked(inferenceRequest).mockImplementation(async(path)=>{
      if(String(path).startsWith('/inference/annotations?'))return {items:[],next_offset:null};
      if(String(path).startsWith('/inference/runs?'))return {items:[{id:'saved',status:'valid',preview_id:'p'}],next_offset:null};
      if(String(path).includes('/reviews?'))return {items:[{id:'ref',reviewer:'reference-rater',activity:'blinded_reference',created_at_ns:'1',content_json:'{"automation_belief":"expected_active"}'}],next_offset:null};
      if(path==='/inference/runs/saved')return {id:'saved',status:'valid',preview_id:'p',result_json:null};
      return {id:'p',status:'ready',payload:'exact bytes',lineage:{evidence_run_id:'r'}};
    });
    render(<SemanticReviewPanel capture={capture}/>);
    fireEvent.click(await screen.findByRole('button',{name:'Load saved reviews'}));
    fireEvent.click(await screen.findByRole('button',{name:/Open attempt saved/}));
    fireEvent.change(await screen.findByLabelText('Reviewer'),{target:{value:'A'}});
    fireEvent.click(screen.getByLabelText('Independent blinded labeling'));
    fireEvent.click(screen.getByRole('button',{name:'View label and disagreement history'}));
    expect(await screen.findByText('expected_active')).toBeVisible();
    fireEvent.change(screen.getByLabelText('Reviewer'),{target:{value:'B'}});
    expect(screen.queryByText('expected_active')).not.toBeInTheDocument();
    expect(screen.getByRole('button',{name:'Show assessment'})).toBeDisabled();
  });
});
