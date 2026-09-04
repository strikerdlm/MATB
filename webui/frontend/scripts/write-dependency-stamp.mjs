import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const packageLock = path.join(frontendRoot, "package-lock.json");
const nodeModules = path.join(frontendRoot, "node_modules");

if (!fs.existsSync(nodeModules)) {
  throw new Error("cannot stamp frontend dependencies before node_modules exists");
}

const packageLockHash = crypto
  .createHash("sha256")
  .update(fs.readFileSync(packageLock))
  .digest("hex");

fs.writeFileSync(
  path.join(nodeModules, ".matb-package-lock.sha256"),
  packageLockHash,
  "ascii",
);
