import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { SemanticReviewPanel } from './SemanticReviewPanel';
import type { EvidenceCapture } from '@/lib/evidence';
import { inferenceRequest } from '@/lib/inference';

vi.mock('@/lib/i18n',()=>({useAppLocale:()=>({copy:(_es:string,en:string)=>en})}));
vi.mock('@/lib/api',()=>({getCapabilities:vi.fn(async()=>({components:[]}))}));
vi.mock('@/lib/inference',async original=>({...await original<typeof import('@/lib/inference')>(),inferenceRequest:vi.fn()}));
const capture={id:'c',runs:[{id:'r',status:'complete'}],reconciliation:{fingerprint:'a'}} as EvidenceCapture;

describe('experimental semantic review',()=>{
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
    expect(await screen.findByText('queued')).toBeInTheDocument();
  });
});
