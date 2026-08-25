#!/usr/bin/env node
import { statSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { createPublicKey } from "node:crypto";
import { AuditLedger } from "../audit/ledger.js";
import { LocalIdentityStore } from "../auth/identity.js";
import { openDatabase, type EdgeDatabase } from "../db/migrate.js";
import { createDatabaseBackup, restoreDatabaseBackup, verifyDatabaseBackup } from "./backup.js";
import { RuntimeLease } from "./runtime-lease.js";
import { MissionService } from "../services/mission-service.js";
import { SafeModeService, SqliteTrustedKeyStore, type TrustedKeyAlgorithm, type TrustedKeyRecord, type TrustedKeyScope } from "../services/safe-mode.js";

export interface AdminIo {
  readonly stdin: () => Promise<string>;
  readonly stdout: (message: string) => void;
  readonly stderr: (message: string) => void;
}

function rejectArgvSecrets(argv: readonly string[]): void {
  for (const argument of argv) {
    const normalized = argument.toLowerCase();
    if (normalized === "--password" || normalized === "--secret" || normalized.startsWith("--password=") || normalized.startsWith("--secret=") || normalized.startsWith("password=") || normalized.startsWith("secret=")) {
      throw new Error("secrets are forbidden in argv; use protected files, stdin, or an interactive prompt");
    }
  }
}

interface ParsedArguments {
  readonly words: readonly string[];
  readonly options: ReadonlyMap<string, string | true>;
}

function parseArguments(argv: readonly string[]): ParsedArguments {
  const words: string[] = [];
  const options = new Map<string, string | true>();
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index]!;
    if (!argument.startsWith("--")) {
      words.push(argument);
      continue;
    }
    const name = argument.slice(2);
    const following = argv[index + 1];
    if (following !== undefined && !following.startsWith("--")) {
      options.set(name, following);
      index += 1;
    } else {
      options.set(name, true);
    }
  }
  return { words, options };
}

function option(parsed: ParsedArguments, name: string, required = true): string | undefined {
  const value = parsed.options.get(name);
  if (typeof value === "string" && value.trim() !== "") return value;
  if (required) throw new Error(`--${name} is required`);
  return undefined;
}

function list(value: string | undefined): string[] {
  return value === undefined ? [] : value.split(",").map((item) => item.trim()).filter(Boolean);
}

async function password(parsed: ParsedArguments, io: AdminIo): Promise<string> {
  const passwordFile = option(parsed, "password-file", false);
  const fromStdin = parsed.options.get("password-stdin") === true;
  if (passwordFile !== undefined && fromStdin) throw new Error("choose one password source");
  let value: string;
  if (passwordFile !== undefined) {
    if ((statSync(passwordFile).mode & 0o077) !== 0) throw new Error("password file must be protected with mode 0600 or stricter");
    value = await readFile(passwordFile, "utf8");
  } else {
    value = await io.stdin();
  }
  value = value.replace(/[\r\n]+$/, "");
  if (value.length < 12) throw new Error("password must contain at least 12 characters");
  return value;
}

async function withOfflineLease<T>(databasePath: string, operation: (database: EdgeDatabase) => Promise<T> | T): Promise<T> {
  const database = openDatabase(databasePath);
  const lease = new RuntimeLease(database, { holderId: `sms-admin:${process.pid}`, durationMs: 120_000 });
  let acquired = false;
  try {
    lease.acquire();
    acquired = true;
    return await operation(database);
  } finally {
    if (acquired) lease.release();
    database.close();
  }
}

function emit(io: AdminIo, value: unknown): void {
  io.stdout(JSON.stringify(value));
}

function offlinePackages(database: EdgeDatabase, packageDirectory: string): SafeModeService {
  const audit = new AuditLedger({ database });
  const missions = new MissionService({ database, auditLedger: audit });
  return new SafeModeService({ database, packageDirectory, auditLedger: audit, missionService: missions, trustedKeyStore: new SqliteTrustedKeyStore(database) });
}

export async function runAdminCli(argv: readonly string[], io: AdminIo): Promise<number> {
  rejectArgvSecrets(argv);
  const parsed = parseArguments(argv);
  const [command, subcommand] = parsed.words;
  if (command === "init") {
    const databasePath = option(parsed, "database")!;
    const secret = await password(parsed, io);
    await withOfflineLease(databasePath, (database) => {
      const identities = new LocalIdentityStore({ database });
      identities.register({ userId: option(parsed, "user-id")!, displayName: option(parsed, "display-name")!, roles: ["administrator"], missionIds: ["*"], password: secret });
    });
    emit(io, { ok: true, command: "init" });
    return 0;
  }
  if (command === "users" && subcommand === "create") {
    const secret = await password(parsed, io);
    await withOfflineLease(option(parsed, "database")!, (database) => {
      new LocalIdentityStore({ database }).register({ userId: option(parsed, "user-id")!, displayName: option(parsed, "display-name")!, roles: list(option(parsed, "roles")) as never, missionIds: list(option(parsed, "mission-ids", false)), qualificationRefs: list(option(parsed, "qualification-refs", false)), password: secret });
    });
    emit(io, { ok: true, command: "users create" });
    return 0;
  }
  if (command === "users" && subcommand === "disable") {
    await withOfflineLease(option(parsed, "database")!, (database) => new LocalIdentityStore({ database }).disable(option(parsed, "user-id")!));
    emit(io, { ok: true, command: "users disable" });
    return 0;
  }
  if (command === "users" && subcommand === "assign") {
    await withOfflineLease(option(parsed, "database")!, (database) => new LocalIdentityStore({ database }).assign(option(parsed, "user-id")!, { roles: list(option(parsed, "roles")) as never, missionIds: list(option(parsed, "mission-ids", false)), qualificationRefs: list(option(parsed, "qualification-refs", false)) }));
    emit(io, { ok: true, command: "users assign" });
    return 0;
  }
  if (command === "trust" && subcommand === "add") {
    await withOfflineLease(option(parsed, "database")!, async (database) => {
      const publicKeyPem = await readFile(option(parsed, "public-key-file")!, "utf8");
      const algorithm = option(parsed, "algorithm") as TrustedKeyAlgorithm;
      const keyType = createPublicKey(publicKeyPem).asymmetricKeyType;
      if ((algorithm === "ed25519" && keyType !== "ed25519") || (algorithm === "rsa-sha256" && keyType !== "rsa" && keyType !== "rsa-pss")) {
        throw new Error("trusted key algorithm does not match the public key file");
      }
      if (algorithm !== "ed25519" && algorithm !== "rsa-sha256") throw new Error("trusted key algorithm is unsupported");
      const record: TrustedKeyRecord = { keyId: option(parsed, "key-id")!, scope: option(parsed, "scope") as TrustedKeyScope, algorithm, publicKeyPem, addedAtUtc: new Date().toISOString(), addedByUserId: option(parsed, "added-by")! };
      new SqliteTrustedKeyStore(database).add(record);
    });
    emit(io, { ok: true, command: "trust add" });
    return 0;
  }
  if (command === "trust" && subcommand === "list") {
    const database = openDatabase(option(parsed, "database")!);
    try {
      emit(io, { ok: true, trustedKeys: new SqliteTrustedKeyStore(database).list() });
      return 0;
    } finally {
      database.close();
    }
  }
  if (command === "packages" && subcommand === "import") {
    const manifest = JSON.parse(await readFile(option(parsed, "manifest-file")!, "utf8")) as { keyId?: unknown };
    const packageDirectory = option(parsed, "package-directory")!;
    const record = await withOfflineLease(option(parsed, "database")!, (database) => offlinePackages(database, packageDirectory).importPackage({ directory: option(parsed, "directory")!, manifest, keyId: option(parsed, "key-id", false) ?? manifest.keyId }, { actorUserId: option(parsed, "actor-user-id")!, clientSessionId: "offline-sms-admin", occurredAtUtc: new Date().toISOString() }));
    emit(io, { ok: true, package: record });
    return 0;
  }
  if (command === "packages" && subcommand === "activate") {
    const packageDirectory = option(parsed, "package-directory")!;
    const record = await withOfflineLease(option(parsed, "database")!, (database) => offlinePackages(database, packageDirectory).activatePackage({ packageId: option(parsed, "package-id")!, version: option(parsed, "version")!, keyId: option(parsed, "key-id")! }, { actorUserId: option(parsed, "actor-user-id")!, clientSessionId: "offline-sms-admin", occurredAtUtc: new Date().toISOString() }));
    emit(io, { ok: true, package: record });
    return 0;
  }
  if (command === "packages" && subcommand === "list") {
    const packageDirectory = option(parsed, "package-directory")!;
    const state = await withOfflineLease(option(parsed, "database")!, (database) => offlinePackages(database, packageDirectory).getPackageState());
    emit(io, { ok: true, ...state });
    return 0;
  }
  if (command === "backup" && subcommand === "create") {
    const databasePath = option(parsed, "database")!;
    const result = await withOfflineLease(databasePath, () => createDatabaseBackup(databasePath, option(parsed, "output")!));
    emit(io, result);
    return 0;
  }
  if (command === "backup" && subcommand === "verify") {
    emit(io, verifyDatabaseBackup(option(parsed, "input")!));
    return 0;
  }
  if (command === "backup" && subcommand === "restore") {
    const databasePath = option(parsed, "database")!;
    await withOfflineLease(databasePath, () => undefined);
    restoreDatabaseBackup(option(parsed, "input")!, databasePath);
    emit(io, { ok: true, command: "backup restore" });
    return 0;
  }
  if (command === "diagnose") {
    const database = openDatabase(option(parsed, "database")!);
    try {
      const audit = await new AuditLedger({ database }).verifyAuditChain();
      emit(io, { ok: audit.ok, schemaVersion: database.schemaVersion(), audit });
      return audit.ok ? 0 : 2;
    } finally {
      database.close();
    }
  }
  throw new Error("unsupported sms-admin command");
}

async function main(): Promise<void> {
  const io: AdminIo = {
    stdin: async () => {
      const chunks: Buffer[] = [];
      for await (const chunk of process.stdin) chunks.push(Buffer.from(chunk));
      return Buffer.concat(chunks).toString("utf8");
    },
    stdout: (message) => process.stdout.write(`${message}\n`),
    stderr: (message) => process.stderr.write(`${message}\n`),
  };
  try {
    process.exitCode = await runAdminCli(process.argv.slice(2), io);
  } catch (error) {
    io.stderr(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}

if (process.argv[1]?.endsWith("cli.js")) void main();
