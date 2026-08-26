import { isAbsolute as posixIsAbsolute, relative as posixRelative, resolve as posixResolve, sep as posixSep, win32 } from "node:path";

function windowsPath(value: string): boolean {
  return /^[a-zA-Z]:[\\/]/.test(value) || value.startsWith("\\\\");
}

export function resolvePortableRuntimePath(base: string, value: string): string {
  if (typeof base !== "string" || base.trim() === "" || base.includes("\0")) throw new Error("runtime path base must be non-empty");
  if (typeof value !== "string" || value.trim() === "" || value.includes("\0")) throw new Error("runtime path must be non-empty");
  if (windowsPath(base) || windowsPath(value)) return win32.resolve(base, value);
  return posixResolve(base, value);
}

export function resolveContainedRuntimePath(root: string, candidate: string): string {
  const windows = windowsPath(root) || windowsPath(candidate);
  const pathApi = windows ? win32 : { resolve: posixResolve, relative: posixRelative, isAbsolute: posixIsAbsolute, sep: posixSep };
  const canonicalRoot = pathApi.resolve(root);
  const full = pathApi.resolve(canonicalRoot, candidate);
  const fromRoot = pathApi.relative(canonicalRoot, full);
  const escaped = fromRoot === ".." || fromRoot.startsWith(`..${pathApi.sep}`) || pathApi.isAbsolute(fromRoot);
  if (escaped) throw new Error("runtime path must remain contained by its configured root");
  return full;
}
