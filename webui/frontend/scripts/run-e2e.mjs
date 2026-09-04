import { spawn } from "node:child_process";
import { once } from "node:events";
import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { resolvePythonExecutable } from "./e2e-runtime.mjs";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(frontendRoot, "../..");
const backendRoot = path.join(repoRoot, "webui", "backend");
const nextCli = path.join(frontendRoot, "node_modules", "next", "dist", "bin", "next");
const playwrightCli = path.join(frontendRoot, "node_modules", "@playwright", "test", "cli.js");
const selectedConfig = process.argv[2];

if (!selectedConfig || path.basename(selectedConfig) !== selectedConfig || !selectedConfig.endsWith(".ts")) {
  throw new Error("run-e2e.mjs requires a Playwright config filename");
}
for (const required of [nextCli, playwrightCli, path.join(frontendRoot, ".next", "BUILD_ID")]) {
  if (!fs.existsSync(required)) throw new Error(`missing E2E prerequisite: ${required}`);
}

function portOpen(port) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host: "127.0.0.1", port });
    socket.setTimeout(500);
    socket.once("connect", () => { socket.destroy(); resolve(true); });
    socket.once("timeout", () => { socket.destroy(); resolve(false); });
    socket.once("error", () => resolve(false));
  });
}

async function waitForUrl(url, processes) {
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    for (const child of processes) {
      if (child.exitCode !== null || child.signalCode !== null) {
        throw new Error(`${child.spawnfile} exited before ${url} was ready`);
      }
    }
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(1_000) });
      if (response.ok) return;
    } catch {
      // Expected while the local service starts.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`timed out waiting for ${url}`);
}

function waitForChildExit(child, timeoutMs) {
  if (child.exitCode !== null || child.signalCode !== null) return Promise.resolve(true);
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
  if (!await waitForChildExit(child, 2_000)) {
    if (process.platform === "win32") {
      const killer = spawn("taskkill.exe", ["/PID", String(child.pid), "/T", "/F"], {
        stdio: "ignore",
        windowsHide: true,
      });
      await once(killer, "exit");
      if (!await waitForChildExit(child, 5_000)) {
        throw new Error(`could not stop child process ${child.pid}`);
      }
      return;
    }
    child.kill("SIGKILL");
    if (!await waitForChildExit(child, 5_000)) {
      throw new Error(`could not stop child process ${child.pid}`);
    }
  }
}

if (await portOpen(8000) || await portOpen(3100)) {
  throw new Error("E2E ports 8000 and 3100 must be free before the managed test run");
}

const runRoot = path.join(repoRoot, ".matb-managed-e2e", String(process.pid));
fs.mkdirSync(runRoot, { recursive: true });
const serviceEnvironment = {
  ...process.env,
  PYTHONDONTWRITEBYTECODE: "1",
  PYTHONUTF8: "1",
  MATB_COMPONENTS: selectedConfig.includes("core") ? "core" : (process.env.MATB_COMPONENTS ?? "auto"),
  MATB_DB_PATH: path.join(runRoot, "matb-e2e.db"),
  MATB_SIMULATION_OUTPUT_DIR: path.join(runRoot, "exports"),
  MATB_SIMULATION_SCENARIO_DIR: path.join(repoRoot, "tests", "suas", "fixtures"),
  MATB_SIMULATION_TEST_MODE: "1",
  MATB_SIMULATION_WALL_TIME_SCALE: process.env.MATB_SIMULATION_WALL_TIME_SCALE ?? "0.5",
  MATB_BACKEND_PORT: "8000",
  NEXT_TELEMETRY_DISABLED: "1",
};

const children = [];
let interrupted = false;
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.once(signal, () => { interrupted = true; });
}

try {
  const backend = spawn(
    resolvePythonExecutable(),
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    { cwd: backendRoot, env: serviceEnvironment, stdio: "inherit", windowsHide: true },
  );
  children.push(backend);
  const frontend = spawn(
    process.execPath,
    [nextCli, "start", "--hostname", "127.0.0.1", "--port", "3100"],
    { cwd: frontendRoot, env: serviceEnvironment, stdio: "inherit", windowsHide: true },
  );
  children.push(frontend);
  await waitForUrl("http://127.0.0.1:8000/health", children);
  await waitForUrl(
    selectedConfig.includes("core")
      ? "http://127.0.0.1:3100/experiments"
      : "http://127.0.0.1:3100/mission/setup",
    children,
  );

  const playwright = spawn(
    process.execPath,
    [playwrightCli, "test", `--config=${selectedConfig}`],
    {
      cwd: frontendRoot,
      env: { ...serviceEnvironment, PW_REUSE_SERVER: "1" },
      stdio: "inherit",
      windowsHide: true,
    },
  );
  children.push(playwright);
  const [code] = await once(playwright, "exit");
  if (interrupted) process.exitCode = 130;
  else if (code !== 0) process.exitCode = typeof code === "number" ? code : 1;
} finally {
  for (const child of children.reverse()) await terminate(child);
  fs.rmSync(runRoot, { recursive: true, force: true });
  try {
    fs.rmdirSync(path.dirname(runRoot));
  } catch (error) {
    if (error?.code !== "ENOENT" && error?.code !== "ENOTEMPTY") throw error;
  }
}
