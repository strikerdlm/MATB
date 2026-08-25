export interface ReleaseWorkflowRecord { readonly id: number; readonly path: string; readonly state: string; }
export interface ProtectedBranchRecord { readonly name: string; readonly protected: boolean; }
export interface ReleaseRunRecord {
  readonly id: number; readonly workflow_id: number; readonly path: string; readonly conclusion: string; readonly status: string;
  readonly event: string; readonly head_branch: string; readonly head_sha: string;
  readonly repository?: { readonly full_name?: string }; readonly head_repository?: { readonly full_name?: string };
}
export function validateCiRunSelection(run: ReleaseRunRecord, workflow: ReleaseWorkflowRecord, options: {
  readonly expectedCommit: string; readonly expectedRepository: string; readonly requestedRunId: string; readonly branch: ProtectedBranchRecord;
}): number;
