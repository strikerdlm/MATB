#!/usr/bin/env node

import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { REQUIRED_REVIEW_SCOPES } from "./acceptance-contracts.mjs";

export function validateExpectedOperationalBlock(report, exitCode) {
  if (exitCode !== 1) throw new Error("operational verifier must use documented not-ready exit code 1");
  if (report?.ok !== true || !Array.isArray(report.violations) || report.violations.length !== 0) throw new Error("operational evidence must be valid before a not-ready result is accepted");
  if (report.operationalReady !== false) throw new Error("operationalReady must be false");
  if (report.qualification !== "blocked") throw new Error("operational qualification must be blocked");
  const pending = Array.isArray(report.pendingReviewScopes) ? [...report.pendingReviewScopes].sort() : [];
  const expected = [...REQUIRED_REVIEW_SCOPES].sort();
  if (JSON.stringify(pending) !== JSON.stringify(expected)) throw new Error("exact pending institutional review scopes are required");
  const pendingBlockers = Array.isArray(report.blockers)
    ? report.blockers.filter((item) => item?.code === "INSTITUTIONAL_REVIEW_PENDING").map((item) => item.scope).sort()
    : [];
  if (JSON.stringify(pendingBlockers) !== JSON.stringify(expected)) throw new Error("exact pending-review blocker records are required");
  return { pendingReviewCount: expected.length };
}

async function main() {
  const [reportPath, exitCodeText] = process.argv.slice(2);
  if (!reportPath || !/^[0-9]+$/u.test(exitCodeText ?? "")) throw new Error("usage: validate-operational-block.mjs REPORT EXIT_CODE");
  const result = validateExpectedOperationalBlock(JSON.parse(await readFile(resolve(reportPath), "utf8")), Number(exitCodeText));
  process.stdout.write(`PASS expected operationalReady=false (${result.pendingReviewCount} pending reviews)\n`);
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
