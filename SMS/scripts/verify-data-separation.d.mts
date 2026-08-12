export interface DataSeparationCheck {
  readonly id: string;
  readonly status: "pass" | "fail";
  readonly detail: string;
}

export interface DataSeparationViolation {
  readonly id: string;
  readonly detail: string;
}

export interface DataSeparationReport {
  readonly ok: boolean;
  readonly checks: readonly DataSeparationCheck[];
  readonly violations: readonly DataSeparationViolation[];
  readonly operationalTables: readonly string[];
  readonly runtimeTables: readonly string[];
  readonly policy?: unknown;
}

export function verifyDataSeparation(root?: string, options?: { readonly runtime?: boolean }): Promise<DataSeparationReport>;
