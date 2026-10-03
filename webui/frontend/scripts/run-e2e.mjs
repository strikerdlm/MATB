import { spawn } from "node:child_process";
import { once } from "node:events";
import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { resolvePythonExecutable, prepareScenarioDirectory } from "./e2e-runtime.mjs";

const frontendRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const repoRoot = path.resolve(frontendRoot, "../..");
const backendRoot = path.join(repoRoot, "webui", "backend");
const nextCli = path.join(
  frontendRoot,
  "node_modules",
  "next",
  "dist",
  "bin",
  "next",
);
const playwrightCli = path.join(
  frontendRoot,
  "node_modules",
  "@playwright",
  "test",
  "cli.js",
);
const selectedConfig = process.argv[2];
const diagnosticRoot = path.join(frontendRoot, "test-results", "runner");
fs.mkdirSync(diagnosticRoot, { recursive: true });
const diagnosticFile = path.join(diagnosticRoot, `${path.basename(selectedConfig ?? "unknown")}-${process.pid}.log`);
function diagnostic(message) {
  const line = `[managed-e2e ${new Date().toISOString()}] ${message}\n`;
  fs.appendFileSync(diagnosticFile, line);
  process.stderr.write(line);
}
process.on("uncaughtExceptionMonitor", (error) => diagnostic(error.stack ?? String(error)));
process.on("exit", (code) => diagnostic(`runner exit code=${code}`));
diagnostic(`starting node=${process.version} platform=${process.platform} config=${selectedConfig}`);

async function main() {

if (
  !selectedConfig ||
  path.basename(selectedConfig) !== selectedConfig ||
  !selectedConfig.endsWith(".ts")
) {
  throw new Error("run-e2e.mjs requires a Playwright config filename");
}
for (const required of [
  nextCli,
  playwrightCli,
  path.resolve(frontendRoot, process.env.MATB_NEXT_DIST_DIR || ".next", "BUILD_ID"),
]) {
  if (!fs.existsSync(required))
    throw new Error(`missing E2E prerequisite: ${required}`);
}

function portOpen(port) {
  diagnostic(`checking port ${port}`);
  return new Promise((resolve) => {
    const socket = net.createConnection({ host: "127.0.0.1", port });
    socket.setTimeout(500);
    socket.once("connect", () => {
      socket.destroy();
      resolve(true);
    });
    socket.once("timeout", () => {
      socket.destroy();
      resolve(false);
    });
    socket.once("error", () => resolve(false));
  });
}

async function waitForUrl(url, processes) {
  diagnostic(`waiting for ${url}`);
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    for (const child of processes) {
      if (spawnErrors.has(child)) throw spawnErrors.get(child);
      if (child.exitCode !== null || child.signalCode !== null) {
        throw new Error(`${child.spawnfile} exited before ${url} was ready`);
      }
    }
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(1_000) });
      if (response.ok) { diagnostic(`ready ${url}`); return; }
    } catch {
      // Expected while the local service starts.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`timed out waiting for ${url}`);
}

function waitForChildExit(child, timeoutMs) {
  if (child.exitCode !== null || child.signalCode !== null)
    return Promise.resolve(true);
  return new Promise((resolve) => {
    const finish = (exited) => {
      clearTimeout(timer);
      child.off("exit", onExit);
      child.off("close", onExit);
      resolve(exited);
    };
    const onExit = () => finish(true);
    const timer = setTimeout(() => finish(false), timeoutMs);
    child.once("exit", onExit);
    child.once("close", onExit);
  });
}

async function terminate(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  child.kill();
  if (!(await waitForChildExit(child, 2_000))) {
    if (process.platform === "win32") {
      const killer = spawn(
        "taskkill.exe",
        ["/PID", String(child.pid), "/T", "/F"],
        {
          stdio: "ignore",
          windowsHide: true,
        },
      );
      await once(killer, "exit");
      if (!(await waitForChildExit(child, 5_000))) {
        throw new Error(`could not stop child process ${child.pid}`);
      }
      return;
    }
    child.kill("SIGKILL");
    if (!(await waitForChildExit(child, 5_000))) {
      throw new Error(`could not stop child process ${child.pid}`);
    }
  }
}

if ((await portOpen(8000)) || (await portOpen(3100))) {
  throw new Error(
    "E2E ports 8000 and 3100 must be free before the managed test run",
  );
}

const runRoot = path.join(repoRoot, ".matb-managed-e2e", String(process.pid));
fs.mkdirSync(runRoot, { recursive: true });
diagnostic(`staging scenarios in ${runRoot}`);
const scenarioDirectory = prepareScenarioDirectory(repoRoot, runRoot);
diagnostic("scenarios staged");
const serviceEnvironment = {
  ...process.env,
  PYTHONDONTWRITEBYTECODE: "1",
  PYTHONUTF8: "1",
  MATB_COMPONENTS: selectedConfig.includes("core")
    ? "core"
    : (process.env.MATB_COMPONENTS ?? "auto"),
  MATB_DB_PATH: path.join(runRoot, "matb-e2e.db"),
  MATB_SIMULATION_OUTPUT_DIR: path.join(runRoot, "exports"),
  MATB_SIMULATION_SCENARIO_DIR: scenarioDirectory,
  MATB_SIMULATION_TEST_MODE: "1",
  MATB_SIMULATION_WALL_TIME_SCALE:
    process.env.MATB_SIMULATION_WALL_TIME_SCALE ?? "0.5",
  MATB_GEOGRAPHY_DIR: path.join(runRoot, "geography"),
  MATB_BACKEND_PORT: "8000",
  NEXT_TELEMETRY_DISABLED: "1",
};

// Prefer explicit color policy without passing conflicting Node flags to children.
if (serviceEnvironment.NO_COLOR !== undefined) {
  serviceEnvironment.FORCE_COLOR ??= "0";
  delete serviceEnvironment.NO_COLOR;
}

const children = [];
const spawnErrors = new WeakMap();
function launch(name, executable, args, options) {
  diagnostic(`spawning ${name}: ${executable} cwd=${options.cwd}`);
  const child = spawn(executable, args, options);
  children.push(child);
  child.once("spawn", () => diagnostic(`${name} spawned pid=${child.pid}`));
  child.once("error", (error) => {
    spawnErrors.set(child, error);
    diagnostic(`${name} spawn error: ${error.stack ?? error}`);
  });
  child.once("exit", (code, signal) => diagnostic(`${name} exit code=${code} signal=${signal}`));
  return child;
}
let succeeded = false;
let interrupted = false;
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.once(signal, () => {
    interrupted = true;
  });
}

try {
  launch(
    "backend", resolvePythonExecutable(),
    [
      "-m",
      "uvicorn",
      process.env.MATB_E2E_TRAFFIC_FIXTURE === "1"
        ? "tests.traffic_e2e_app:app"
        : "app.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      "8000",
    ],
    {
      cwd: backendRoot,
      env: serviceEnvironment,
      stdio: "inherit",
      windowsHide: true,
    },
  );
  launch(
    "frontend", process.execPath,
    [nextCli, "start", "--hostname", "127.0.0.1", "--port", "3100"],
    {
      cwd: frontendRoot,
      env: serviceEnvironment,
      stdio: "inherit",
      windowsHide: true,
    },
  );
  await waitForUrl("http://127.0.0.1:8000/health", children);
  await waitForUrl(
    selectedConfig.includes("core")
      ? "http://127.0.0.1:3100/experiments"
      : "http://127.0.0.1:3100/mission/setup",
    children,
  );

  const playwright = launch(
    "playwright", process.execPath,
    [
      playwrightCli,
      "test",
      `--config=${selectedConfig}`,
      ...process.argv.slice(3),
    ],
    {
      cwd: frontendRoot,
      env: { ...serviceEnvironment, PW_REUSE_SERVER: "1" },
      stdio: "inherit",
      windowsHide: true,
    },
  );
  const [code] = await once(playwright, "exit");
  succeeded = code === 0 && !interrupted;
  if (interrupted) process.exitCode = 130;
  else if (code !== 0) process.exitCode = typeof code === "number" ? code : 1;
} finally {
  for (const child of children.reverse()) await terminate(child);
  if (!succeeded) {
    diagnostic(`failure artifacts retained at ${runRoot}`);
  } else {
    fs.rmSync(runRoot, { recursive: true, force: true });
    try {
      fs.rmdirSync(path.dirname(runRoot));
    } catch (error) {
      if (error?.code !== "ENOENT" && error?.code !== "ENOTEMPTY") throw error;
    }
  }
}

}
try {
  await main();
} catch (error) {
  diagnostic(`failed: ${error.stack ?? error}`);
  process.exitCode = 1;
}
