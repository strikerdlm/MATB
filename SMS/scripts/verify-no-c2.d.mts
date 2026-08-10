export interface NoC2Finding {
  readonly id: string;
  readonly file: string;
  readonly line: number;
  readonly column: number;
  readonly detail: string;
}

export interface NoC2Route {
  readonly method: string;
  readonly path: string;
  readonly file: string;
  readonly line: number;
  readonly column: number;
}

export interface NoC2Adapter {
  readonly name: string;
  readonly methods: readonly string[];
  readonly file: string;
  readonly line: number;
  readonly column: number;
}

export interface NoC2RuntimeProbe {
  readonly method: string;
  readonly path: string;
  readonly status: number;
  readonly registered?: boolean;
}

export interface NoC2Report {
  readonly ok: boolean;
  readonly forbidden: readonly NoC2Finding[];
  readonly routes: readonly NoC2Route[];
  readonly adapters: readonly NoC2Adapter[];
  readonly runtimeRoutes: readonly NoC2RuntimeProbe[];
  readonly runtimeProbes: readonly NoC2RuntimeProbe[];
  readonly runtimeRouteMetadata: string;
  readonly approvedReadOnlyTerms: readonly string[];
}

export function scanNoC2(root?: string, options?: { readonly runtime?: boolean }): Promise<NoC2Report>;
