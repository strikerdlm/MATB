import type { FastifyInstance } from "fastify";

const MAX_JSON_DEPTH = 32;

export class StrictJsonError extends Error {
  public readonly statusCode = 400;
  public readonly code = "STRICT_JSON_INVALID";

  public constructor() {
    super("request body must be strict bounded JSON");
    this.name = "StrictJsonError";
  }
}

export function parseStrictJson(source: string, maxDepth = MAX_JSON_DEPTH): unknown {
  const parser = new StrictJsonParser(source, maxDepth);
  parser.parse();
  try {
    return JSON.parse(source) as unknown;
  } catch {
    throw new StrictJsonError();
  }
}

export function registerStrictJsonParser(app: FastifyInstance): void {
  app.removeContentTypeParser("application/json");
  app.addContentTypeParser("application/json", { parseAs: "string" }, (_request, body, done) => {
    try {
      done(null, parseStrictJson(typeof body === "string" ? body : body.toString("utf8")));
    } catch (error) {
      done(error as Error);
    }
  });
}

class StrictJsonParser {
  private offset = 0;

  public constructor(private readonly source: string, private readonly maxDepth: number) {}

  public parse(): void {
    this.skipWhitespace();
    this.value(0);
    this.skipWhitespace();
    if (this.offset !== this.source.length) this.fail();
  }

  private value(depth: number): void {
    if (depth > this.maxDepth) this.fail();
    const character = this.source[this.offset];
    if (character === "{") return this.object(depth);
    if (character === "[") return this.array(depth);
    if (character === '"') return void this.string();
    if (character === "t") return this.literal("true");
    if (character === "f") return this.literal("false");
    if (character === "n") return this.literal("null");
    this.number();
  }

  private object(depth: number): void {
    this.offset += 1;
    this.skipWhitespace();
    const keys = new Set<string>();
    if (this.consume("}")) return;
    while (true) {
      if (this.source[this.offset] !== '"') this.fail();
      const key = this.string();
      if (keys.has(key)) this.fail();
      keys.add(key);
      this.skipWhitespace();
      if (!this.consume(":")) this.fail();
      this.skipWhitespace();
      this.value(depth + 1);
      this.skipWhitespace();
      if (this.consume("}")) return;
      if (!this.consume(",")) this.fail();
      this.skipWhitespace();
    }
  }

  private array(depth: number): void {
    this.offset += 1;
    this.skipWhitespace();
    if (this.consume("]")) return;
    while (true) {
      this.value(depth + 1);
      this.skipWhitespace();
      if (this.consume("]")) return;
      if (!this.consume(",")) this.fail();
      this.skipWhitespace();
    }
  }

  private string(): string {
    const start = this.offset;
    this.offset += 1;
    while (this.offset < this.source.length) {
      const character = this.source[this.offset++];
      if (character === '"') {
        try {
          return JSON.parse(this.source.slice(start, this.offset)) as string;
        } catch {
          return this.fail();
        }
      }
      if (character === "\\") {
        const escaped = this.source[this.offset++];
        if (escaped === "u") {
          if (!/^[0-9a-fA-F]{4}$/.test(this.source.slice(this.offset, this.offset + 4))) this.fail();
          this.offset += 4;
        } else if (escaped === undefined || !'"\\/bfnrt'.includes(escaped)) this.fail();
      } else if (character === undefined || character.charCodeAt(0) < 0x20) this.fail();
    }
    return this.fail();
  }

  private number(): void {
    const match = /^-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/.exec(this.source.slice(this.offset));
    if (match === null) this.fail();
    this.offset += match[0].length;
  }

  private literal(literal: string): void {
    if (!this.source.startsWith(literal, this.offset)) this.fail();
    this.offset += literal.length;
  }

  private skipWhitespace(): void {
    while (this.source[this.offset] === " " || this.source[this.offset] === "\n" || this.source[this.offset] === "\r" || this.source[this.offset] === "\t") this.offset += 1;
  }

  private consume(character: string): boolean {
    if (this.source[this.offset] !== character) return false;
    this.offset += 1;
    return true;
  }

  private fail(): never {
    throw new StrictJsonError();
  }
}
