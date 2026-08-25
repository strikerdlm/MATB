#!/usr/bin/env node

import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { lstat, readFile, readdir } from "node:fs/promises";
import { isAbsolute, relative, resolve, sep } from "node:path";

function parse(argv) {
  const options = { root: undefined, json: false };
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === "--root") options.root = argv[++index];
    else if (argv[index] === "--json") options.json = true;
    else throw new Error(`unknown argument: ${argv[index]}`);
  }
  if (!options.root) throw new Error("--root is required");
  return options;
}

async function hash(path) {
  const digest = createHash("sha256");
  for await (const chunk of createReadStream(path)) digest.update(chunk);
  return digest.digest("hex");
}

async function files(root, directory = root) {
  const found = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const full = resolve(directory, entry.name);
    const path = relative(root, full).split(sep).join("/");
    if (entry.isSymbolicLink()) throw new Error(`symbolic links are forbidden: ${path}`);
    if (entry.isDirectory()) found.push(...await files(root, full));
    else if (entry.isFile()) found.push(path);
    else throw new Error(`unsupported filesystem entry: ${path}`);
  }
  return found.sort();
}

export async function verifyPlatformInventory(rootInput) {
  const root = resolve(rootInput);
  const inventoryPath = resolve(root, "inventory.json");
  const inventory = JSON.parse(await readFile(inventoryPath, "utf8"));
  if (inventory.schemaVersion !== "1.0" || inventory.inventoryPath !== "inventory.json" || !Array.isArray(inventory.files)) {
    throw new Error("unsupported platform inventory");
  }
  const expected = new Map();
  for (const item of inventory.files) {
    if (typeof item?.path !== "string" || item.path === "inventory.json" || isAbsolute(item.path) || item.path.split("/").includes("..") || expected.has(item.path)) {
      throw new Error("inventory contains an unsafe or duplicate path");
    }
    expected.set(item.path, item);
  }
  const actual = (await files(root)).filter((path) => path !== "inventory.json" && path !== "inventory.tsv");
  const actualSet = new Set(actual);
  const missing = [...expected.keys()].filter((path) => !actualSet.has(path)).sort();
  const unexpected = actual.filter((path) => !expected.has(path)).sort();
  const mismatched = [];
  for (const path of actual) {
    const item = expected.get(path);
    if (!item) continue;
    const info = await lstat(resolve(root, path));
    const actualHash = await hash(resolve(root, path));
    const actualMode = info.mode & 0o777;
    if (item.sha256 !== actualHash || item.sizeBytes !== info.size || item.mode !== actualMode) mismatched.push(path);
  }
  return { valid: missing.length === 0 && unexpected.length === 0 && mismatched.length === 0, missing, unexpected, mismatched };
}

if (import.meta.url === new URL(`file://${process.argv[1]}`).href) {
  try {
    const options = parse(process.argv.slice(2));
    const result = await verifyPlatformInventory(options.root);
    process.stdout.write(`${JSON.stringify(result, null, options.json ? 0 : 2)}\n`);
    if (!result.valid) process.exitCode = 1;
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
    process.exitCode = 1;
  }
}
