import fs from "node:fs";
import path from "node:path";

const frontendRoot = path.resolve();
const buildDirectory = path.join(frontendRoot, ".next");

if (!fs.existsSync(path.join(buildDirectory, "BUILD_ID"))) {
  throw new Error("cannot stamp a frontend build before Next.js creates BUILD_ID");
}

fs.writeFileSync(path.join(buildDirectory, ".matb-build-root"), frontendRoot, "utf8");
