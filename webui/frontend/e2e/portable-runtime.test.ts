import { describe, expect, it } from "vitest";

import { quoteShellArgument, resolvePythonExecutable, shellCommand } from "../scripts/e2e-runtime.mjs";

describe("portable Playwright runtime", () => {
  it("uses the native virtual-environment layout on each platform", () => {
    expect(resolvePythonExecutable({ MATB_VENV: "C:\\MATB env ñ" }, "win32"))
      .toBe("C:\\MATB env ñ\\Scripts\\python.exe");
    expect(resolvePythonExecutable({ MATB_VENV: "/tmp/MATB env ñ" }, "linux"))
      .toBe("/tmp/MATB env ñ/bin/python");
  });

  it("honors an explicit executable or portable platform fallback", () => {
    expect(resolvePythonExecutable({ MATB_PYTHON: " custom-python " }, "win32")).toBe("custom-python");
    expect(resolvePythonExecutable({}, "win32")).toBe("python");
    expect(resolvePythonExecutable({}, "linux")).toBe("python3");
  });

  it("quotes spaces and Unicode for Windows and POSIX shells", () => {
    expect(quoteShellArgument("C:\\MATB files ñ\\python.exe", "win32"))
      .toBe('"C:\\MATB files ñ\\python.exe"');
    expect(quoteShellArgument("/tmp/MATB files ñ/python", "linux"))
      .toBe("'/tmp/MATB files ñ/python'");
    expect(shellCommand("/tmp/it's python", ["-m", "module"], "linux"))
      .toBe("'/tmp/it'\\''s python' '-m' 'module'");
  });

  it("rejects arguments that cannot be represented safely", () => {
    expect(() => quoteShellArgument("bad\npath", "linux")).toThrow(/NUL or newline/);
    expect(() => quoteShellArgument('bad"path', "win32")).toThrow(/double quote/);
  });
});
