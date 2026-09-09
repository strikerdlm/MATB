import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";
// MapLibre v6 ESM workers import a sibling shared module. Next must serve both.
const frontend = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const installed = path.dirname(
  createRequire(import.meta.url).resolve("maplibre-gl/package.json"),
);
const output = path.join(frontend, "public", "maplibre");
mkdirSync(output, { recursive: true });
for (const file of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"])
  copyFileSync(path.join(installed, "dist", file), path.join(output, file));
copyFileSync(
  path.join(installed, "LICENSE.txt"),
  path.join(output, "LICENSE.txt"),
);
