import { it,expect,vi } from 'vitest';
import { downloadInference } from './inference';
import { stationFetch } from './station-fetch';
vi.mock('./station-fetch',()=>({stationFetch:vi.fn()}));
vi.mock('./runtime-config',()=>({getApiBase:async()=> 'http://localhost:8000'}));
it('exports through station admission and rejects failed downloads',async()=>{
  vi.mocked(stationFetch).mockResolvedValue({ok:false,status:409} as Response);
  await expect(downloadInference('run/1','rater')).rejects.toThrow('HTTP 409');
  expect(stationFetch).toHaveBeenCalledWith('http://localhost:8000/inference/runs/run%2F1/export?reviewer=rater');
});
