#!/usr/bin/env node

import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const COMMIT = /^[a-f0-9]{40}$/u;
const RUN_ID = /^[1-9][0-9]*$/u;

export function validateCiRunSelection(run, workflow, options) {
  if (!COMMIT.test(options?.expectedCommit ?? "")) throw new Error("expected commit must be 40 lowercase hexadecimal characters");
  if (typeof options?.expectedRepository !== "string" || options.expectedRepository === "") throw new Error("expected repository is required");
  if (!RUN_ID.test(options?.requestedRunId ?? "")) throw new Error("candidate run ID must be a positive numeric value");
  if (options?.branch?.name !== "main" || options.branch.protected !== true) throw new Error("release source branch main must be protected");
  const requested = Number(options.requestedRunId);
  if (!Number.isSafeInteger(requested) || run?.id !== requested) throw new Error("candidate run ID differs from the selected run");
  if (!Number.isSafeInteger(workflow?.id) || workflow?.path !== ".github/workflows/sms-ci.yml" || workflow?.state !== "active") {
    throw new Error("sms-ci workflow identity is not active and exact");
  }
  if (run.workflow_id !== workflow.id || !String(run.path ?? "").startsWith(".github/workflows/sms-ci.yml@")) throw new Error("candidate run is not sms-ci.yml");
  if (run.status !== "completed" || run.conclusion !== "success") throw new Error("candidate run did not complete successfully");
  if (run.event !== "push" || run.head_branch !== "main") throw new Error("candidate run is not a trusted main push");
  if (run.head_sha !== options.expectedCommit) throw new Error("candidate run commit differs from the release source");
  if (run.repository?.full_name !== options.expectedRepository || run.head_repository?.full_name !== options.expectedRepository) {
    throw new Error("candidate run originated from another repository or fork");
  }
  return requested;
}

function parse(argv) {
  const options = {};
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (!["--run", "--workflow", "--branch", "--source-commit", "--repository", "--run-id"].includes(argument)) throw new Error(`unknown argument: ${argument}`);
    const value = argv[++index];
    if (!value || value.startsWith("--")) throw new Error(`${argument} requires a value`);
    options[argument.slice(2).replaceAll(/-([a-z])/gu, (_, letter) => letter.toUpperCase())] = value;
  }
  if (!options.run || !options.workflow || !options.branch) throw new Error("--run, --workflow, and --branch are required");
  return options;
}

async function main() {
  const options = parse(process.argv.slice(2));
  const run = JSON.parse(await readFile(resolve(options.run), "utf8"));
  const workflow = JSON.parse(await readFile(resolve(options.workflow), "utf8"));
  const branch = JSON.parse(await readFile(resolve(options.branch), "utf8"));
  const id = validateCiRunSelection(run, workflow, {
    expectedCommit: options.sourceCommit,
    expectedRepository: options.repository,
    requestedRunId: options.runId,
    branch,
  });
  process.stdout.write(`${id}\n`);
}

if (process.argv[1] !== undefined && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  await main().catch((error) => {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  });
}
