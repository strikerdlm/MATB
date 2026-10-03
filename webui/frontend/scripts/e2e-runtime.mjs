import path from "node:path";
import fs from "node:fs";

function nonEmpty(value) {
  const selected = value?.trim();
  return selected || undefined;
}

/**
 * @param {Record<string, string | undefined>} environment
 * @param {NodeJS.Platform} platform
 */
export function resolvePythonExecutable(environment = process.env, platform = process.platform) {
  const explicit = nonEmpty(environment.MATB_PYTHON);
  if (explicit) return explicit;

  const venv = nonEmpty(environment.MATB_VENV);
  if (venv) {
    return platform === "win32"
      ? path.win32.join(venv, "Scripts", "python.exe")
      : path.posix.join(venv, "bin", "python");
  }
  return platform === "win32" ? "python" : "python3";
}

/** @param {string} value @param {NodeJS.Platform} platform */
export function quoteShellArgument(value, platform = process.platform) {
  if (!value || /[\0\r\n]/u.test(value)) {
    throw new Error("process arguments must be non-empty and contain no NUL or newline");
  }
  if (platform === "win32") {
    if (value.includes('"')) throw new Error("Windows process arguments must not contain a double quote");
    return `"${value}"`;
  }
  return `'${value.replaceAll("'", "'\\''")}'`;
}

/** @param {string} executable @param {readonly string[]} args @param {NodeJS.Platform} platform */
export function shellCommand(executable, args, platform = process.platform) {
  return [executable, ...args].map((part) => quoteShellArgument(part, platform)).join(" ");
}

/** @param {NodeJS.Platform} platform */
export function backendCommand(platform = process.platform) {
  return shellCommand(
    resolvePythonExecutable(process.env, platform),
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    platform,
  );
}

/** @param {string} frontendRoot @param {NodeJS.Platform} platform */
export function frontendCommand(frontendRoot, platform = process.platform) {
  const nextCli = path.join(frontendRoot, "node_modules", "next", "dist", "bin", "next");
  return shellCommand(
    process.execPath,
    [nextCli, "start", "--hostname", "127.0.0.1", "--port", "3100"],
    platform,
  );
}

// The hosted Windows runner exited during scenario staging. Avoid native copy
// helpers for these small fixtures; preserve their bytes through explicit I/O.
function stageFiles(source, destination) {
  fs.mkdirSync(destination, { recursive: true });
  for (const entry of fs.readdirSync(source, { withFileTypes: true })) {
    const from = path.join(source, entry.name);
    const to = path.join(destination, entry.name);
    if (entry.isDirectory()) stageFiles(from, to);
    else if (entry.isFile()) fs.writeFileSync(to, fs.readFileSync(from));
    else throw new Error(`unsupported scenario fixture: ${from}`);
  }
}

/** Install browser fixtures and the real LOW/HIGH fleet scenario in an isolated run. */
export function prepareScenarioDirectory(repoRoot, runRoot) {
  const directory = path.join(runRoot, "scenarios");
  stageFiles(path.join(repoRoot, "tests", "suas", "fixtures"), directory);
  fs.writeFileSync(path.join(directory, "reference_area_search.yaml"),
    fs.readFileSync(path.join(repoRoot, "scenarios", "suas", "reference_area_search.yaml")));
  return directory;
}
