import { readdir, readFile } from "node:fs/promises";
import { relative, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const RESEARCH_TABLE_PATTERN = /research|participant|protocol|consent/i;
const OPERATIONAL_SOURCE_ROOTS = ["apps", "packages"];

function normalizedPath(root, path) {
  return relative(root, path).replaceAll("\\", "/");
}

async function readJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

async function operationalWorkspaceDirectories(root) {
  const directories = [];
  for (const group of OPERATIONAL_SOURCE_ROOTS) {
    const groupRoot = resolve(root, group);
    let entries;
    try {
      entries = await readdir(groupRoot, { withFileTypes: true });
    } catch (error) {
      if (error && typeof error === "object" && "code" in error && error.code === "ENOENT") continue;
      throw error;
    }
    for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
      if (!entry.isDirectory() || (group === "packages" && entry.name === "research")) continue;
      directories.push(resolve(groupRoot, entry.name));
    }
  }
  return directories;
}

async function typescriptFiles(directory) {
  const files = [];
  async function visit(path) {
    let entries;
    try {
      entries = await readdir(path, { withFileTypes: true });
    } catch (error) {
      if (error && typeof error === "object" && "code" in error && error.code === "ENOENT") return;
      throw error;
    }
    for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
      const child = resolve(path, entry.name);
      if (entry.isDirectory()) {
        if (entry.name !== "dist" && entry.name !== "node_modules" && entry.name !== "test") await visit(child);
      } else if (entry.isFile() && /\.tsx?$/.test(entry.name)) {
        files.push(child);
      }
    }
  }
  await visit(resolve(directory, "src"));
  return files;
}

function checkPolicy(policy) {
  const operational = policy?.domains?.operational;
  const research = policy?.domains?.research;
  if (policy?.schemaVersion !== "1.0" || operational === undefined || research === undefined) {
    return "data-domain policy must define schema 1.0 operational and research domains";
  }
  for (const field of ["databasePathEnv", "hostDataDirectoryEnv", "encryptionKeyIdEnv"]) {
    if (typeof operational[field] !== "string" || typeof research[field] !== "string" || operational[field] === research[field]) {
      return `operational and research ${field} values must be explicit and distinct`;
    }
  }
  const approvedFlow = policy.allowedFlows?.find((flow) => flow?.from === "research" && flow?.to === "operational");
  if (approvedFlow?.payload !== "approved-deidentified-aggregate-review" || approvedFlow.automatic !== false) {
    return "the only research-to-operational flow must require a non-automatic approved deidentified aggregate review";
  }
  return undefined;
}

function addCheck(report, id, detail, failure) {
  const status = failure === undefined ? "pass" : "fail";
  report.checks.push({ id, status, detail: failure ?? detail });
  if (failure !== undefined) report.violations.push({ id, detail: failure });
}

async function verifyWorkspaceDependencies(root, report) {
  const violations = [];
  for (const directory of await operationalWorkspaceDirectories(root)) {
    const manifestPath = resolve(directory, "package.json");
    let manifest;
    try {
      manifest = await readJson(manifestPath);
    } catch (error) {
      violations.push(`${normalizedPath(root, manifestPath)}: ${error instanceof Error ? error.message : String(error)}`);
      continue;
    }
    const dependencyGroups = [manifest.dependencies, manifest.devDependencies, manifest.optionalDependencies];
    if (dependencyGroups.some((dependencies) => dependencies !== undefined && Object.hasOwn(dependencies, "@fac-isr/research"))) {
      violations.push(`${normalizedPath(root, manifestPath)} depends on @fac-isr/research`);
    }
  }
  addCheck(report, "workspace-dependencies", "operational workspaces do not depend on @fac-isr/research", violations.length === 0 ? undefined : violations.join("; "));
}

async function verifySourceImports(root, report) {
  const violations = [];
  for (const directory of await operationalWorkspaceDirectories(root)) {
    for (const path of await typescriptFiles(directory)) {
      const contents = await readFile(path, "utf8");
      if (/from\s+["']@fac-isr\/research(?:["'/]|$)|import\s*\(\s*["']@fac-isr\/research(?:["'/]|$)/.test(contents)) {
        violations.push(`${normalizedPath(root, path)} imports @fac-isr/research`);
      }
    }
  }
  addCheck(report, "source-imports", "operational runtime source has no research-package import", violations.length === 0 ? undefined : violations.join("; "));
}

async function verifyOperationalSchema(root, report) {
  const edgeSource = resolve(root, "apps/edge-api/src");
  const tables = [];
  for (const path of await typescriptFiles(resolve(root, "apps/edge-api"))) {
    const contents = await readFile(path, "utf8");
    for (const match of contents.matchAll(/CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)/gi)) tables.push(match[1]);
  }
  const forbidden = tables.filter((table) => RESEARCH_TABLE_PATTERN.test(table));
  const missing = tables.length === 0 ? `no operational tables were discovered under ${normalizedPath(root, edgeSource)}` : undefined;
  addCheck(report, "operational-schema", `${tables.length} operational table declarations contain no research identity`, missing ?? (forbidden.length === 0 ? undefined : `research-shaped operational tables: ${forbidden.join(", ")}`));
  report.operationalTables = [...new Set(tables)].sort();
}

async function verifyDeploymentPolicy(root, report) {
  const policyPath = resolve(root, "docker/data-domain-policy.json");
  try {
    const policy = await readJson(policyPath);
    addCheck(report, "database-key-separation", "operational and research database, host path, and encryption-key identifiers are distinct", checkPolicy(policy));
    report.policy = policy;
  } catch (error) {
    addCheck(report, "database-key-separation", "data-domain policy is valid", `${normalizedPath(root, policyPath)}: ${error instanceof Error ? error.message : String(error)}`);
  }

  const composePath = resolve(root, "docker/compose.edge.yml");
  try {
    const compose = await readFile(composePath, "utf8");
    const hasRequiredDataPath = compose.includes("${SMS_DATA_DIR:?set SMS_DATA_DIR}:/var/lib/fac-isr/data:rw");
    const hasEncryptionRequirement = /institutionally approved encrypted volume/i.test(compose);
    const exposesResearchPath = /SMS_RESEARCH_|\/research(?:\/|:|\s)/i.test(compose);
    const failure = !hasRequiredDataPath
      ? "edge compose must require the explicit operational data-directory mount"
      : !hasEncryptionRequirement
        ? "edge compose must mark the host data directory as an approved encrypted volume"
        : exposesResearchPath
          ? "edge compose must not mount a research data path"
          : undefined;
    addCheck(report, "encrypted-operational-path", "edge storage requires an approved encrypted host volume and exposes no research mount", failure);
  } catch (error) {
    addCheck(report, "encrypted-operational-path", "edge storage policy is present", `${normalizedPath(root, composePath)}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

async function verifyBoundaryRegistration(root, report) {
  try {
    const [server, boundary] = await Promise.all([
      readFile(resolve(root, "apps/edge-api/src/server.ts"), "utf8"),
      readFile(resolve(root, "apps/edge-api/src/data-boundary.ts"), "utf8"),
    ]);
    const registered = /registerOperationalDataBoundary\(app\)/.test(server);
    const failClosed = boundary.includes("RESEARCH_DATA_DOMAIN_FORBIDDEN")
      && /participantcode/i.test(boundary)
      && /datadomain/i.test(boundary)
      && /nondispatchable/i.test(boundary);
    addCheck(report, "operational-boundary", "edge write routes register a fail-closed research-domain pre-validation boundary", registered && failClosed ? undefined : "operational research-domain boundary is absent or incomplete");
  } catch (error) {
    addCheck(report, "operational-boundary", "edge write boundary is present", error instanceof Error ? error.message : String(error));
  }
}

async function verifyResearchContract(root, report) {
  try {
    const contract = await readFile(resolve(root, "packages/research/src/types.ts"), "utf8");
    const complete = contract.includes('readonly dataDomain: "research"')
      && contract.includes("readonly nonDispatchable: true")
      && /strictKeys\(input/.test(contract)
      && /participantCode/.test(contract);
    addCheck(report, "research-contract", "research records are explicitly research-only, non-dispatchable, pseudonymous, and strict", complete ? undefined : "research contract does not encode every separation invariant");
  } catch (error) {
    addCheck(report, "research-contract", "research contract is present", error instanceof Error ? error.message : String(error));
  }
}

async function verifyRuntime(root, report) {
  const serverPath = resolve(root, "apps/edge-api/dist/server.js");
  const authPath = resolve(root, "apps/edge-api/dist/auth/index.js");
  let app;
  try {
    const [serverModule, authModule] = await Promise.all([
      import(`${pathToFileURL(serverPath).href}?data-separation=${Date.now()}`),
      import(`${pathToFileURL(authPath).href}?data-separation=${Date.now()}`),
    ]);
    const nowUtc = "2026-08-10T12:00:00.000Z";
    const password = "correct horse battery staple";
    const identityStore = new authModule.LocalIdentityStore({ now: () => nowUtc });
    identityStore.register({ userId: "boundary-commander", displayName: "Boundary Commander", roles: ["commander"], missionIds: ["mission-1"], password });
    const sessionManager = new authModule.SessionManager({
      now: () => nowUtc,
      idleTimeoutMs: 15 * 60_000,
      maxLifetimeMs: 8 * 60 * 60_000,
      reauthenticationIntervalMs: 5 * 60_000,
      sessionIdFactory: () => "boundary-session",
      csrfTokenFactory: () => "boundary-csrf",
    });
    app = await serverModule.buildServer({ databaseUrl: ":memory:", internet: "disabled" }, { identityStore, sessionManager });
    await app.ready();
    const login = await app.inject({ method: "POST", url: "/api/auth/login", payload: { userId: "boundary-commander", password } });
    if (login.statusCode !== 200) throw new Error(`data-separation probe login returned ${login.statusCode}`);
    const response = await app.inject({
      method: "POST",
      url: "/api/missions",
      headers: { cookie: "__Host-sms_session=boundary-session", "x-csrf-token": "boundary-csrf" },
      payload: {
        dataDomain: "research",
        nonDispatchable: true,
        participantCode: "BOUNDARY-PROBE",
        protocolId: "BOUNDARY-PROBE",
      },
    });
    const body = response.json();
    const tableNames = app.edgeDatabase.tableNames();
    const boundaryFailure = response.statusCode === 400 && body?.error === "RESEARCH_DATA_DOMAIN_FORBIDDEN"
      ? undefined
      : `research payload returned ${response.statusCode} with ${JSON.stringify(body)}`;
    addCheck(report, "operational-ingress", "runtime rejects research payload before operational persistence", boundaryFailure);
    addCheck(report, "runtime-schema", "runtime operational database contains no research tables", tableNames.some((table) => RESEARCH_TABLE_PATTERN.test(table)) ? `research-shaped runtime tables: ${tableNames.join(", ")}` : undefined);
    report.runtimeTables = tableNames;
  } catch (error) {
    addCheck(report, "operational-ingress", "runtime rejects research payload before operational persistence", error instanceof Error ? error.message : String(error));
    addCheck(report, "runtime-schema", "runtime operational database contains no research tables", "runtime schema could not be inspected");
  } finally {
    await app?.close();
  }
}

/** Verify build-time, deployment, schema, and runtime separation invariants. */
export async function verifyDataSeparation(root = resolve(process.cwd()), options = {}) {
  const repositoryRoot = resolve(root);
  const report = {
    ok: false,
    checks: [],
    violations: [],
    operationalTables: [],
    runtimeTables: [],
    policy: undefined,
  };
  await verifyWorkspaceDependencies(repositoryRoot, report);
  await verifySourceImports(repositoryRoot, report);
  await verifyOperationalSchema(repositoryRoot, report);
  await verifyDeploymentPolicy(repositoryRoot, report);
  await verifyBoundaryRegistration(repositoryRoot, report);
  await verifyResearchContract(repositoryRoot, report);
  if (options.runtime === true) await verifyRuntime(repositoryRoot, report);
  report.ok = report.violations.length === 0;
  return report;
}

async function main() {
  const report = await verifyDataSeparation(resolve(process.cwd()), { runtime: !process.argv.includes("--static-only") });
  if (!report.ok) {
    for (const violation of report.violations) process.stderr.write(`${violation.id}: ${violation.detail}\n`);
    process.exitCode = 1;
    return;
  }
  process.stdout.write(`PASS data separation (${report.checks.length} controls, ${report.runtimeTables.length} operational tables)\n`);
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
