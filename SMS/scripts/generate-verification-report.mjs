#!/usr/bin/env node

import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { relative, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const REPORT_PATH = "dist/reports/verification-report.json";
const MATRIX_PATH = "docs/release/verification-matrix.md";
const REVIEWER = Object.freeze({ type: "automated", id: "fac-isr-sms-ci" });

const COMMANDS = Object.freeze({
  core: {
    display: "npm test -- --run",
    executable: "npm",
    args: ["test", "--", "--run"],
  },
  stateAviation: {
    display: "npm test -- test/integration/state-aviation.test.ts --run",
    executable: "npm",
    args: ["test", "--", "test/integration/state-aviation.test.ts", "--run"],
  },
  performance: {
    display: "npm test -- test/performance --run",
    executable: "npm",
    args: ["test", "--", "test/performance", "--run"],
  },
  offline: {
    display: "npm test -- test/integration/offline-install.test.ts --run",
    executable: "npm",
    args: ["test", "--", "test/integration/offline-install.test.ts", "--run"],
    conditionalOnSkip: true,
  },
  consoleE2e: {
    display: "npm run test:e2e --workspace @fac-isr/console",
    executable: "npm",
    args: ["run", "test:e2e", "--workspace", "@fac-isr/console"],
  },
  consoleA11y: {
    display: "npm run test:a11y --workspace @fac-isr/console",
    executable: "npm",
    args: ["run", "test:a11y", "--workspace", "@fac-isr/console"],
  },
  noC2: {
    display: "npm run verify:no-c2",
    executable: "npm",
    args: ["run", "verify:no-c2"],
  },
  dataSeparation: {
    display: "npm run verify:data-separation",
    executable: "npm",
    args: ["run", "verify:data-separation"],
  },
});

const REQUIREMENTS = Object.freeze([
  {
    coverage: "normalized-rules-calculations",
    title: "Normalized rules and deterministic calculations",
    commandKey: "core",
    artifacts: [
      "docs/regulations/normalized/racae94-amendment-2.json",
      "packages/safety-kernel/test/applicability.test.ts",
      "packages/energy/test/property.test.ts",
    ],
    limitation: "Automated checks do not replace approval of normalized interpretations by the competent State-aviation and legal authorities.",
  },
  {
    coverage: "racae-classes",
    title: "All RACAE aircraft classes",
    commandKey: "stateAviation",
    artifacts: [
      "test/integration/state-aviation.test.ts",
      "packages/safety-kernel/test/fixtures/all-racae-classes.json",
    ],
    limitation: "Class thresholds are verified against the approved repository fixtures; authority acceptance of the operational classification policy remains pending.",
  },
  {
    coverage: "vfr-ifr",
    title: "VFR and explicit IFR prerequisites",
    commandKey: "stateAviation",
    artifacts: [
      "test/integration/state-aviation.test.ts",
      "packages/safety-kernel/test/applicability.test.ts",
      "packages/geo/test/flight-plan.test.ts",
    ],
    limitation: "IFR readiness remains conditional on mission-specific authorization, segregated airspace, equipment approval, and current evidence.",
  },
  {
    coverage: "visual-conditions",
    title: "VLOS, EVLOS, and BVLOS conditions",
    commandKey: "stateAviation",
    artifacts: [
      "test/integration/state-aviation.test.ts",
      "packages/geo/test/visibility.test.ts",
    ],
    limitation: "Synthetic viewshed and evidence fixtures do not constitute field validation of observers, detect-and-avoid equipment, or tactical links.",
  },
  {
    coverage: "golden-blocked-cases",
    title: "Fail-closed golden blocked cases",
    commandKey: "stateAviation",
    artifacts: [
      "test/integration/state-aviation.test.ts",
      "test/fixtures/blocked-cases/airspace-review-pending.json",
      "test/fixtures/blocked-cases/armed-configuration.json",
      "test/fixtures/blocked-cases/autonomous-flight.json",
      "test/fixtures/blocked-cases/missing-operator.json",
      "test/fixtures/blocked-cases/stale-weather.json",
    ],
    limitation: "The curated blockers are regression evidence, not an exhaustive substitute for an authority-approved operational hazard catalogue.",
  },
  {
    coverage: "dependency-invalidation",
    title: "Material-change dependency invalidation",
    commandKey: "core",
    artifacts: [
      "packages/safety-kernel/test/dependencies.test.ts",
      "packages/safety-kernel/test/gates.test.ts",
    ],
    limitation: "The dependency graph covers modeled fields; receiving-organization change-control validation remains required for local extensions.",
  },
  {
    coverage: "bilingual-equivalence",
    title: "Bilingual controlled terminology",
    commandKey: "consoleE2e",
    artifacts: [
      "apps/console/e2e/console.spec.ts",
      "apps/console/src/i18n/registry.ts",
      "docs/translations/controlled-terms.json",
    ],
    limitation: "UI equivalence is automated, but controlled legal translations still require designated bilingual human review.",
  },
  {
    coverage: "geospatial-integrity",
    title: "Projection, datum, terrain, obstacle, and airspace integrity",
    commandKey: "core",
    artifacts: [
      "packages/geo/test/coordinates.test.ts",
      "packages/geo/test/terrain.test.ts",
      "packages/geo/test/airspace.test.ts",
      "packages/geo/test/packages.test.ts",
    ],
    limitation: "Synthetic fixtures do not approve provider licensing, authoritative coverage, obstacle completeness, or receiving-site vertical-datum surveys.",
  },
  {
    coverage: "battery-reserve",
    title: "Battery demand and approved reserve floors",
    commandKey: "core",
    artifacts: [
      "packages/energy/test/model.test.ts",
      "packages/energy/test/property.test.ts",
      "packages/safety-kernel/test/fleet-energy-integration.test.ts",
    ],
    limitation: "Deterministic model checks require calibration and endurance acceptance with each approved aircraft, battery, payload, and environment.",
  },
  {
    coverage: "package-integrity",
    title: "Package tamper, expiry, downgrade, and partial-import rejection",
    commandKey: "core",
    artifacts: [
      "test/security/package-tamper.test.ts",
      "packages/evidence/test/manifest.test.ts",
      "packages/geo/test/packages.test.ts",
    ],
    limitation: "Software verification does not attest institutional key custody, malware scanning, removable-media control, or source-provider approval.",
  },
  {
    coverage: "telemetry-degradation",
    title: "Telemetry delay, dropout, duplication, ordering, and malformed input",
    commandKey: "core",
    artifacts: [
      "packages/telemetry/test/replay.test.ts",
      "apps/edge-api/test/telemetry.test.ts",
      "apps/edge-api/test/safe-mode.test.ts",
    ],
    limitation: "Simulated streams do not replace hardware-in-the-loop validation over representative radios, gateways, and contested networks.",
  },
  {
    coverage: "offline-cold-start",
    title: "Disconnected installation and cold start",
    commandKey: "offline",
    artifacts: [
      "test/integration/offline-install.test.ts",
      "scripts/verify-offline.mjs",
      "Dockerfile",
    ],
    limitation: "The Docker exercise is conditional when a daemon is unavailable; receiving-hardware transfer, boot, storage, and endurance acceptance remains pending.",
  },
  {
    coverage: "concurrency-gate-separation",
    title: "Concurrent workload and accountable gate separation",
    commandKey: "core",
    artifacts: [
      "test/performance/multi-aircraft.test.ts",
      "apps/edge-api/test/audit.test.ts",
      "apps/edge-api/test/gates.test.ts",
    ],
    limitation: "Concurrency uses synthetic in-process and in-memory fixtures; approved-node SQLite, storage endurance, and operational staffing loads remain unmeasured.",
  },
  {
    coverage: "accessibility",
    title: "Automated accessibility in day, night, desktop, and tablet states",
    commandKey: "consoleA11y",
    artifacts: [
      "apps/console/e2e/accessibility.spec.ts",
      "apps/console/src/app/AppShell.tsx",
      "apps/console/src/styles/tokens.css",
      "apps/console/src/styles/operational.css",
    ],
    limitation: "Axe serious/critical checks do not replace assistive-technology trials or operational human-factors acceptance with representative users.",
  },
  {
    coverage: "responsive-human-factors",
    title: "Responsive, reduced-motion, keyboard, day/night, and tablet behavior",
    commandKey: "consoleE2e",
    artifacts: [
      "apps/console/e2e/console.spec.ts",
      "apps/console/src/styles/operational.css",
      "apps/console/playwright.config.ts",
    ],
    limitation: "Playwright viewport coverage does not replace workload, glare, touch, fatigue, or representative-device human-factors validation.",
  },
  {
    coverage: "long-duration-performance",
    title: "Accelerated long-duration telemetry replay",
    commandKey: "performance",
    artifacts: ["test/performance/long-duration.test.ts"],
    limitation: "The test accelerates twelve synthetic hours and is not a wall-clock soak, leak, thermal, storage, or receiving-hardware endurance test.",
  },
  {
    coverage: "multi-aircraft-performance",
    title: "Configured multi-aircraft correctness workload",
    commandKey: "performance",
    artifacts: ["test/performance/multi-aircraft.test.ts"],
    limitation: "The in-process workload asserts correctness only; no universal throughput or latency threshold is claimed for approved tactical hardware.",
  },
  {
    coverage: "data-separation",
    title: "Operational and research data-domain separation",
    commandKey: "dataSeparation",
    artifacts: [
      "scripts/verify-data-separation.mjs",
      "test/security/data-separation.test.ts",
      "docker/data-domain-policy.json",
    ],
    limitation: "Repository and runtime controls do not attest host encryption, key administration, physical media, or receiving-organization access governance.",
  },
  {
    coverage: "no-c2",
    title: "No command-and-control path",
    commandKey: "noC2",
    artifacts: [
      "scripts/verify-no-c2.mjs",
      "test/security/no-c2.test.ts",
      "apps/edge-api/src/server.ts",
    ],
    limitation: "Static and runtime probes require independent architecture and penetration review of the deployed system-of-systems and connected equipment.",
  },
]);

function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

function normalizedPath(root, path) {
  return relative(root, path).replaceAll("\\", "/");
}

async function sourceArtifact(root, path) {
  const absolutePath = resolve(root, path);
  let contents;
  try {
    contents = await readFile(absolutePath);
  } catch (error) {
    throw new Error(`verification evidence is unavailable: ${normalizedPath(root, absolutePath)}`, { cause: error });
  }
  return { kind: "source", path, sha256: sha256(contents) };
}

function skippedTests(output) {
  return /\b[1-9]\d*\s+skipped\b/i.test(output) || /\bskipped\s+\([1-9]\d*\)/i.test(output);
}

function commandLog(definition, result, stdout, stderr) {
  return [
    `command: ${definition.display}`,
    `result: ${result}`,
    "",
    "[stdout]",
    stdout.trimEnd(),
    "",
    "[stderr]",
    stderr.trimEnd(),
    "",
  ].join("\n");
}

async function runCommand(root, key, definition) {
  const startedAtUtc = new Date().toISOString();
  const started = performance.now();
  const execution = await new Promise((resolveExecution) => {
    const environment = { ...process.env, NO_COLOR: "1" };
    delete environment.FORCE_COLOR;
    const child = spawn(definition.executable, definition.args, {
      cwd: root,
      env: environment,
      stdio: ["ignore", "pipe", "pipe"],
    });
    const stdout = [];
    const stderr = [];
    child.stdout.on("data", (chunk) => stdout.push(chunk));
    child.stderr.on("data", (chunk) => stderr.push(chunk));
    child.once("error", (error) => resolveExecution({ exitCode: null, signal: null, stdout: Buffer.concat(stdout).toString("utf8"), stderr: `${Buffer.concat(stderr).toString("utf8")}${error.message}\n` }));
    child.once("close", (exitCode, signal) => resolveExecution({ exitCode, signal, stdout: Buffer.concat(stdout).toString("utf8"), stderr: Buffer.concat(stderr).toString("utf8") }));
  });
  const combinedOutput = `${execution.stdout}\n${execution.stderr}`;
  const result = execution.exitCode !== 0
    ? "fail"
    : definition.conditionalOnSkip === true && skippedTests(combinedOutput)
      ? "conditional"
      : "pass";
  const log = commandLog(definition, result, execution.stdout, execution.stderr);
  const artifact = {
    kind: "command-output",
    path: `dist/reports/commands/${key}.log`,
    sha256: sha256(log),
  };
  return {
    key,
    command: definition.display,
    result,
    exitCode: execution.exitCode,
    signal: execution.signal,
    startedAtUtc,
    finishedAtUtc: new Date().toISOString(),
    durationMs: Math.round((performance.now() - started) * 1000) / 1000,
    stdoutSha256: sha256(execution.stdout),
    stderrSha256: sha256(execution.stderr),
    artifact,
    log,
  };
}

function publicCommandResult(commandRun) {
  return {
    key: commandRun.key,
    command: commandRun.command,
    result: commandRun.result,
    exitCode: commandRun.exitCode,
    signal: commandRun.signal,
    startedAtUtc: commandRun.startedAtUtc,
    finishedAtUtc: commandRun.finishedAtUtc,
    durationMs: commandRun.durationMs,
    stdoutSha256: commandRun.stdoutSha256,
    stderrSha256: commandRun.stderrSha256,
    artifact: commandRun.artifact,
  };
}

function markdownCell(value) {
  return String(value).replaceAll("|", "\\|").replaceAll("\n", "<br>");
}

function renderMatrix(report) {
  const rows = report.requirements.map((requirement) => {
    const artifacts = requirement.artifacts
      .filter((artifact) => artifact.kind === "source")
      .map((artifact) => `\`${artifact.path}\`<br>\`${artifact.sha256}\``)
      .join("<br><br>");
    return `| ${markdownCell(requirement.title)} | \`${markdownCell(requirement.command)}\` | ${requirement.result.toUpperCase()} | ${artifacts} | \`${requirement.reviewer.type}:${requirement.reviewer.id}\` | ${markdownCell(requirement.unresolvedLimitation)} |`;
  });
  return [
    "# FAC ISR SMS verification matrix",
    "",
    "> Automated verification evidence only. Operational readiness remains **false** until the unresolved institutional and field-acceptance limitations are closed by accountable human reviewers.",
    "",
    `Schema: \`${report.schemaVersion}\``,
    "",
    `Operational ready: \`${String(report.operationalReady)}\``,
    "",
    "| Requirement | Test command | Result | Hash-locked evidence | Reviewer | Unresolved limitation |",
    "| --- | --- | --- | --- | --- | --- |",
    ...rows,
    "",
    "## Release blockers retained by design",
    "",
    ...report.readinessBlockers.map((blocker) => `- ${blocker}`),
    "",
  ].join("\n");
}

async function writeOutputs(root, report, commandRuns) {
  const reportPath = resolve(root, REPORT_PATH);
  const matrixPath = resolve(root, MATRIX_PATH);
  await Promise.all([
    mkdir(resolve(reportPath, ".."), { recursive: true }),
    mkdir(resolve(matrixPath, ".."), { recursive: true }),
    mkdir(resolve(root, "dist/reports/commands"), { recursive: true }),
  ]);
  await Promise.all(commandRuns.map((commandRun) => writeFile(resolve(root, commandRun.artifact.path), commandRun.log, "utf8")));
  await Promise.all([
    writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8"),
    writeFile(matrixPath, renderMatrix(report), "utf8"),
  ]);
}

/** Build the complete P6.5 verification report without claiming institutional readiness. */
export async function buildVerificationReport(root = process.cwd(), options = {}) {
  const repositoryRoot = resolve(root);
  const execute = options.execute === true;
  const write = options.write === true;
  const commandRuns = [];
  const commandRunByKey = new Map();

  if (execute) {
    for (const requirement of REQUIREMENTS) {
      if (commandRunByKey.has(requirement.commandKey)) continue;
      const definition = COMMANDS[requirement.commandKey];
      const commandRun = await runCommand(repositoryRoot, requirement.commandKey, definition);
      commandRuns.push(commandRun);
      commandRunByKey.set(requirement.commandKey, commandRun);
    }
  }

  const requirements = [];
  for (const definition of REQUIREMENTS) {
    const command = COMMANDS[definition.commandKey];
    const commandRun = commandRunByKey.get(definition.commandKey);
    const artifacts = await Promise.all(definition.artifacts.map((path) => sourceArtifact(repositoryRoot, path)));
    if (commandRun !== undefined) artifacts.push(commandRun.artifact);
    requirements.push({
      coverage: definition.coverage,
      title: definition.title,
      command: command.display,
      result: commandRun?.result ?? "not-run",
      artifacts,
      reviewer: { ...REVIEWER },
      unresolvedLimitation: definition.limitation,
    });
  }

  const report = {
    schemaVersion: "1.0",
    generatedAtUtc: new Date().toISOString(),
    environment: { node: process.version, platform: process.platform, arch: process.arch },
    operationalReady: false,
    readinessBlockers: [
      "Competent-authority and bilingual legal review of normalized operational interpretations is incomplete.",
      "Representative aircraft, operator, tactical-network, assistive-technology, and receiving-hardware acceptance is incomplete.",
      "Institutional key custody, host encryption, removable-media, malware-scan, and source-licensing attestations are incomplete.",
    ],
    commands: commandRuns.map(publicCommandResult),
    requirements,
  };

  if (write) await writeOutputs(repositoryRoot, report, commandRuns);
  return report;
}

async function main() {
  const report = await buildVerificationReport(process.cwd(), { execute: true, write: true });
  const failures = report.requirements.filter((requirement) => requirement.result === "fail");
  const conditional = report.requirements.filter((requirement) => requirement.result === "conditional");
  if (failures.length > 0) {
    process.stderr.write(`FAIL verification matrix (${failures.length} failed requirements; report: ${REPORT_PATH})\n`);
    process.exitCode = 1;
    return;
  }
  process.stdout.write(`PASS verification matrix (${report.requirements.length} requirements, ${conditional.length} conditional, operationalReady=false)\n`);
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.stack ?? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
