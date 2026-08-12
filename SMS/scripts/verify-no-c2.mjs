import { readdir, readFile } from "node:fs/promises";
import { relative, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const SOURCE_ROOTS = ["apps", "packages"];
const ROUTE_METHODS = new Set(["delete", "get", "head", "options", "patch", "post", "put"]);
const FORBIDDEN_IDENTIFIERS = new Set([
  "arm",
  "dispatchcommand",
  "executecommand",
  "gcscommand",
  "launch",
  "payloadcontrol",
  "recoverycontrol",
  "redirect",
  "sendcommand",
  "writecommand",
]);
const FORBIDDEN_ROUTE_SEGMENTS = new Set([
  "arm",
  "command",
  "commands",
  "control",
  "controls",
  "launch",
  "payload-control",
  "payloadcontrol",
  "recovery-control",
  "recoverycontrol",
  "redirect",
]);
const COMMAND_MESSAGE = /(?:^|[.:/_-])(arm|command|commands|gcs-command|launch|payload-control|recovery-control|redirect)(?:$|[.:/_-])/i;
const NETWORK_MODULES = new Set([
  "axios",
  "node:dgram",
  "node:http",
  "node:http2",
  "node:https",
  "node:tls",
  "node:udp",
  "undici",
]);
const APPROVED_READ_ONLY_TERMS = Object.freeze([
  "routeDeviationM",
  "recoveryStatus",
  "c2Link",
]);
const FORBIDDEN_RUNTIME_PROBES = Object.freeze([
  ["POST", "/api/arm"],
  ["POST", "/api/launch"],
  ["POST", "/api/commands"],
  ["POST", "/api/control"],
  ["POST", "/api/payload-control"],
  ["POST", "/api/recovery-control"],
  ["POST", "/api/redirect"],
  ["POST", "/api/gcs/command"],
]);

function normalizedPath(root, path) {
  return relative(root, path).replaceAll("\\", "/");
}

async function sourceFiles(root) {
  const files = [];

  async function visit(directory) {
    let entries;
    try {
      entries = await readdir(directory, { withFileTypes: true });
    } catch (error) {
      if (error && typeof error === "object" && "code" in error && error.code === "ENOENT") return;
      throw error;
    }
    for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
      const path = resolve(directory, entry.name);
      if (entry.isDirectory()) {
        if (entry.name !== "dist" && entry.name !== "node_modules" && entry.name !== "test") await visit(path);
      } else if (entry.isFile() && /\.tsx?$/.test(entry.name)) {
        files.push(path);
      }
    }
  }

  for (const sourceRoot of SOURCE_ROOTS) {
    const workspaceRoot = resolve(root, sourceRoot);
    let workspaces;
    try {
      workspaces = await readdir(workspaceRoot, { withFileTypes: true });
    } catch (error) {
      if (error && typeof error === "object" && "code" in error && error.code === "ENOENT") continue;
      throw error;
    }
    for (const workspace of workspaces.sort((left, right) => left.name.localeCompare(right.name))) {
      if (workspace.isDirectory()) await visit(resolve(workspaceRoot, workspace.name, "src"));
    }
  }
  return files.sort();
}

function memberName(member) {
  if (member.name === undefined) return undefined;
  if (ts.isIdentifier(member.name) || ts.isStringLiteral(member.name) || ts.isNumericLiteral(member.name)) return member.name.text;
  return undefined;
}

function routeFromCall(node) {
  if (!ts.isCallExpression(node) || !ts.isPropertyAccessExpression(node.expression)) return undefined;
  if (!ts.isIdentifier(node.expression.expression) || node.expression.expression.text !== "app") return undefined;
  const method = node.expression.name.text.toLowerCase();
  const routeArgument = node.arguments[0];
  if (!ROUTE_METHODS.has(method) || routeArgument === undefined || !ts.isStringLiteralLike(routeArgument)) return undefined;
  return { method: method.toUpperCase(), path: routeArgument.text };
}

function isForbiddenRoute(path) {
  const segments = path.toLowerCase().split("/").filter(Boolean);
  return segments.some((segment) => FORBIDDEN_ROUTE_SEGMENTS.has(segment));
}

function lineAndColumn(sourceFile, node) {
  const position = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
  return { line: position.line + 1, column: position.character + 1 };
}

function scanSource(root, path, contents, result) {
  const file = normalizedPath(root, path);
  const sourceFile = ts.createSourceFile(
    file,
    contents,
    ts.ScriptTarget.Latest,
    true,
    path.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );

  function addForbidden(id, node, detail) {
    result.forbidden.push({ id, file, ...lineAndColumn(sourceFile, node), detail });
  }

  function visit(node) {
    const route = routeFromCall(node);
    if (route !== undefined) {
      result.routes.push({ ...route, file, ...lineAndColumn(sourceFile, node) });
      if (isForbiddenRoute(route.path)) addForbidden("command-route", node, `${route.method} ${route.path}`);
    }

    if ((ts.isInterfaceDeclaration(node) || ts.isClassDeclaration(node)) && node.name?.text.toLowerCase().includes("adapter")) {
      const methods = node.members.map(memberName).filter((name) => name !== undefined);
      result.adapters.push({ name: node.name.text, methods, file, ...lineAndColumn(sourceFile, node) });
    }

    if (ts.isIdentifier(node) && FORBIDDEN_IDENTIFIERS.has(node.text.toLowerCase())) {
      addForbidden("command-identifier", node, node.text);
    }

    if (ts.isStringLiteralLike(node) && COMMAND_MESSAGE.test(node.text) && route === undefined) {
      addForbidden("command-message", node, node.text);
    }

    if (ts.isImportDeclaration(node) && ts.isStringLiteral(node.moduleSpecifier)) {
      const moduleName = node.moduleSpecifier.text;
      if (NETWORK_MODULES.has(moduleName)) addForbidden("network-client", node, `unapproved runtime module ${moduleName}`);
      if (moduleName === "node:net") {
        const imports = node.importClause?.namedBindings;
        const onlyIpValidation = imports !== undefined
          && ts.isNamedImports(imports)
          && imports.elements.length > 0
          && imports.elements.every((element) => element.name.text === "isIP");
        if (!onlyIpValidation) addForbidden("network-client", node, "node:net is approved only for address validation via isIP");
      }
    }

    if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === "fetch") {
      addForbidden("network-client", node, "unapproved fetch client in runtime source");
    }
    if (ts.isNewExpression(node) && ts.isIdentifier(node.expression) && ["EventSource", "WebSocket"].includes(node.expression.text)) {
      addForbidden("network-client", node, `unapproved ${node.expression.text} client in runtime source`);
    }

    ts.forEachChild(node, visit);
  }

  visit(sourceFile);
}

function routeExample(path) {
  return path.replace(/:([A-Za-z0-9_]+)/g, (_match, parameter) => `scan-${parameter}`);
}

async function probeRuntime(root, result) {
  const serverPath = resolve(root, "apps/edge-api/dist/server.js");
  let app;
  try {
    const serverModule = await import(`${pathToFileURL(serverPath).href}?no-c2=${Date.now()}`);
    app = await serverModule.buildServer({ databaseUrl: ":memory:", internet: "disabled" });
    await app.ready();
    result.runtimeRouteMetadata = app.printRoutes({ commonPrefix: false });

    for (const route of result.routes) {
      const response = await app.inject({ method: route.method, url: routeExample(route.path), payload: route.method === "GET" || route.method === "HEAD" ? undefined : {} });
      const registered = app.hasRoute({ method: route.method, url: route.path });
      result.runtimeRoutes.push({ method: route.method, path: route.path, status: response.statusCode, registered });
      if (!registered) {
        result.forbidden.push({ id: "route-metadata", file: route.file, line: route.line, column: route.column, detail: `${route.method} ${route.path} is absent from the runtime route registry` });
      }
    }

    for (const [method, path] of FORBIDDEN_RUNTIME_PROBES) {
      const response = await app.inject({ method, url: path, payload: {} });
      result.runtimeProbes.push({ method, path, status: response.statusCode });
      if (response.statusCode !== 404) {
        result.forbidden.push({ id: "runtime-command-route", file: "runtime-route-registry", line: 1, column: 1, detail: `${method} ${path} returned ${response.statusCode}` });
      }
    }
  } catch (error) {
    result.forbidden.push({
      id: "runtime-verification",
      file: normalizedPath(root, serverPath),
      line: 1,
      column: 1,
      detail: error instanceof Error ? error.message : String(error),
    });
  } finally {
    await app?.close();
  }
}

/** Scan source syntax and, when requested, the built edge runtime for command paths. */
export async function scanNoC2(root = resolve(process.cwd()), options = {}) {
  const repositoryRoot = resolve(root);
  const result = {
    ok: false,
    forbidden: [],
    routes: [],
    adapters: [],
    runtimeRoutes: [],
    runtimeProbes: [],
    runtimeRouteMetadata: "",
    approvedReadOnlyTerms: [...APPROVED_READ_ONLY_TERMS],
  };

  for (const path of await sourceFiles(repositoryRoot)) {
    scanSource(repositoryRoot, path, await readFile(path, "utf8"), result);
  }
  if (options.runtime === true) await probeRuntime(repositoryRoot, result);

  result.forbidden.sort((left, right) => `${left.file}:${left.line}:${left.column}:${left.id}`.localeCompare(`${right.file}:${right.line}:${right.column}:${right.id}`));
  result.routes.sort((left, right) => `${left.path}:${left.method}`.localeCompare(`${right.path}:${right.method}`));
  result.adapters.sort((left, right) => `${left.name}:${left.file}`.localeCompare(`${right.name}:${right.file}`));
  result.ok = result.forbidden.length === 0;
  return result;
}

async function main() {
  const result = await scanNoC2(resolve(process.cwd()), { runtime: !process.argv.includes("--static-only") });
  if (!result.ok) {
    for (const finding of result.forbidden) process.stderr.write(`${finding.id} ${finding.file}:${finding.line}:${finding.column} ${finding.detail}\n`);
    process.exitCode = 1;
    return;
  }
  process.stdout.write(`PASS no-C2 verification (${result.routes.length} routes, ${result.adapters.length} adapter contracts, ${result.runtimeProbes.length} forbidden-route probes)\n`);
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
