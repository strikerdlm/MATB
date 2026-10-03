import { describe, expect, it } from "vitest";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import { prepareScenarioDirectory, quoteShellArgument, resolvePythonExecutable, shellCommand } from "../scripts/e2e-runtime.mjs";

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

it("stages byte-identical independent scenarios in relocated Unicode paths", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "MATB relocation ñ "));
  try {
    const fixtures = path.join(root, "tests", "suas", "fixtures");
    fs.mkdirSync(path.join(fixtures, "nested"), { recursive: true });
    fs.mkdirSync(path.join(root, "scenarios", "suas"), { recursive: true });
    const bytes = Buffer.from("label: misión\r\nvalue: 123\n", "utf8");
    fs.writeFileSync(path.join(fixtures, "fixture.yaml"), bytes);
    fs.writeFileSync(path.join(fixtures, "nested", "extra.yaml"), bytes);
    fs.writeFileSync(path.join(root, "scenarios", "suas", "reference_area_search.yaml"), bytes);
    const first = prepareScenarioDirectory(root, path.join(root, "run one ñ"));
    const second = prepareScenarioDirectory(root, path.join(root, "run two ñ"));
    for (const name of ["fixture.yaml", "nested/extra.yaml", "reference_area_search.yaml"]) {
      expect(fs.readFileSync(path.join(first, name))).toEqual(bytes);
      expect(fs.readFileSync(path.join(second, name))).toEqual(bytes);
    }
    fs.writeFileSync(path.join(first, "fixture.yaml"), "changed");
    expect(fs.readFileSync(path.join(fixtures, "fixture.yaml"))).toEqual(bytes);
    expect(fs.readFileSync(path.join(second, "fixture.yaml"))).toEqual(bytes);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});
