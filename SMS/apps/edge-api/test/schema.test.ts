import { describe, expect, it } from "vitest";
import { openDatabase } from "../src/db/migrate.js";

describe("edge operational database", () => {
  it("enables foreign keys and records the current schema version", () => {
    const database = openDatabase(":memory:");

    expect(database.pragma("foreign_keys")).toBe(1);
    expect(database.schemaVersion()).toBe(1);
    expect(database.tableNames()).toEqual([
      "schema_migrations",
      "service_state",
    ]);

    database.close();
  });

  it("can rerun migrations without changing the schema", () => {
    const database = openDatabase(":memory:");
    const firstVersion = database.schemaVersion();

    database.migrate();

    expect(database.schemaVersion()).toBe(firstVersion);
    expect(database.tableNames()).toHaveLength(2);
    database.close();
  });
});
