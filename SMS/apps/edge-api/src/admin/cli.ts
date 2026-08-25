#!/usr/bin/env node
import { constants } from "node:fs";
import { open, readFile } from "node:fs/promises";
import { createPublicKey } from "node:crypto";
import { AuditLedger } from "../audit/ledger.js";
import { LocalIdentityStore } from "../auth/identity.js";
import { openDatabase, type EdgeDatabase } from "../db/migrate.js";
import { createDatabaseBackup, restoreDatabaseBackup, verifyDatabaseBackup } from "./backup.js";
import { RuntimeLease, RuntimeLeaseError } from "./runtime-lease.js";
import { MaintenanceLock } from "./maintenance-lock.js";
import { MissionService } from "../services/mission-service.js";
import { SafeModeService, SqliteTrustedKeyStore, type TrustedKeyAlgorithm, type TrustedKeyRecord, type TrustedKeyScope } from "../services/safe-mode.js";

export interface AdminIo {
  readonly stdin: () => Promise<string>;
  readonly stdinIsTty?: () => boolean;
  readonly promptSecret?: () => Promise<string>;
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
    let handle;
    try {
      handle = await open(passwordFile, constants.O_RDONLY | constants.O_NOFOLLOW);
    } catch (error) {
      throw new Error("password file must be a protected regular file and symbolic links are forbidden", { cause: error });
    }
    try {
      const metadata = await handle.stat();
      if (!metadata.isFile()) throw new Error("password file must be a regular file");
      if ((metadata.mode & 0o077) !== 0) throw new Error("password file must be protected with mode 0600 or stricter");
      if (typeof process.getuid === "function" && metadata.uid !== process.getuid()) throw new Error("password file must be owned by the current service account");
      value = await handle.readFile("utf8");
    } finally {
      await handle.close();
    }
  } else if (fromStdin) {
    if (io.stdinIsTty?.() === true) throw new Error("--password-stdin requires a pipe; use the masked TTY prompt instead");
    value = await io.stdin();
  } else {
    if (io.stdinIsTty?.() !== true || io.promptSecret === undefined) throw new Error("choose --password-stdin, --password-file, or an interactive masked prompt");
    value = await io.promptSecret();
  }
  value = value.replace(/[\r\n]+$/, "");
  if (value.length < 12) throw new Error("password must contain at least 12 characters");
  return value;
}

async function withOfflineLease<T>(databasePath: string, operation: (database: EdgeDatabase) => Promise<T> | T): Promise<T> {
  const maintenance = new MaintenanceLock(databasePath);
  maintenance.acquire();
  let database: EdgeDatabase | undefined;
  try {
    database = openDatabase(databasePath, 5_000, { maintenanceLock: maintenance });
  } catch (error) {
    maintenance.release();
    throw error;
  }
  const lease = new RuntimeLease(database, { holderId: `sms-admin:${process.pid}`, durationMs: 120_000 });
  let acquired = false;
  let renewalFailure: unknown;
  let renewalTimer: ReturnType<typeof setInterval> | undefined;
  try {
    lease.acquire();
    acquired = true;
    renewalTimer = setInterval(() => {
      try { lease.renew(); } catch (error) { renewalFailure = error; }
    }, 40_000);
    renewalTimer.unref();
    const result = await operation(database);
    if (renewalFailure !== undefined) throw new RuntimeLeaseError("offline operation lost its runtime lease", { cause: renewalFailure });
    return result;
  } finally {
    if (renewalTimer !== undefined) clearInterval(renewalTimer);
    if (acquired) lease.release();
    database.close();
    maintenance.release();
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
    const maintenance = new MaintenanceLock(databasePath);
    maintenance.acquire();
    try {
      restoreDatabaseBackup(option(parsed, "input")!, databasePath, maintenance);
    } finally {
      maintenance.release();
    }
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
    stdinIsTty: () => process.stdin.isTTY === true,
    promptSecret: maskedPasswordPrompt,
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

async function maskedPasswordPrompt(): Promise<string> {
  if (process.stdin.isTTY !== true || typeof process.stdin.setRawMode !== "function") throw new Error("a TTY is required for the masked password prompt");
  return new Promise<string>((resolve, reject) => {
    let secret = "";
    const wasRaw = process.stdin.isRaw;
    const cleanup = (): void => {
      process.stdin.off("data", onData);
      process.stdin.setRawMode(wasRaw);
      process.stdin.pause();
    };
    const onData = (chunk: Buffer | string): void => {
      for (const character of String(chunk)) {
        if (character === "\r" || character === "\n") {
          cleanup();
          process.stdout.write("\n");
          resolve(secret);
          return;
        }
        if (character === "\u0003") {
          cleanup();
          process.stdout.write("\n");
          reject(new Error("password prompt cancelled"));
          return;
        }
        if (character === "\u007f" || character === "\b") secret = secret.slice(0, -1);
        else if (character >= " ") secret += character;
      }
    };
    process.stdout.write("Password: ");
    process.stdin.setRawMode(true);
    process.stdin.resume();
    process.stdin.on("data", onData);
  });
}

if (process.argv[1]?.endsWith("cli.js")) void main();
