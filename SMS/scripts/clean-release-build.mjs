#!/usr/bin/env node

import { rm } from "node:fs/promises";
import { resolve } from "node:path";

const roots = [
  "apps/console/dist",
  "apps/console/test-results",
  "apps/edge-api/dist",
  "packages/energy/dist",
  "packages/evidence/dist",
  "packages/fleet/dist",
  "packages/geo/dist",
  "packages/human-performance/dist",
  "packages/research/dist",
  "packages/safety-kernel/dist",
  "packages/sms/dist",
  "packages/telemetry/dist",
  "tools/map-packager/dist",
  "tools/research/dist",
];

for (const path of roots) await rm(resolve(path), { recursive: true, force: true });
process.stdout.write(`Cleaned ${roots.length} generated build/test output roots\n`);
