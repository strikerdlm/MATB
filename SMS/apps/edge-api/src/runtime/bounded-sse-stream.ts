import { Readable } from "node:stream";

export interface BoundedSseStreamOptions {
  readonly maxQueuedRecords?: number;
  readonly maxQueuedBytes?: number;
  readonly highWaterMark?: number;
}

export class BoundedSseStream extends Readable {
  private readonly queue: string[] = [];
  private readonly maxQueuedRecords: number;
  private readonly maxQueuedBytes: number;
  private queuedBytes = 0;
  private blocked = false;
  private ending = false;

  public constructor(options: BoundedSseStreamOptions = {}) {
    super({ encoding: "utf8", highWaterMark: options.highWaterMark });
    this.maxQueuedRecords = options.maxQueuedRecords ?? 128;
    this.maxQueuedBytes = options.maxQueuedBytes ?? 2 * 1024 * 1024;
  }

  public enqueue(record: string): boolean {
    if (this.destroyed || this.ending) return false;
    if (!this.blocked && this.queue.length === 0) {
      this.blocked = !this.push(record);
      return true;
    }
    const bytes = Buffer.byteLength(record, "utf8");
    if (this.queue.length >= this.maxQueuedRecords || this.queuedBytes + bytes > this.maxQueuedBytes) {
      this.queue.length = 0;
      this.queuedBytes = 0;
      this.destroy();
      return false;
    }
    this.queue.push(record);
    this.queuedBytes += bytes;
    return true;
  }

  public endStream(): void {
    if (this.destroyed || this.ending) return;
    this.ending = true;
    if (this.queue.length === 0) this.push(null);
  }

  public queuedRecordCount(): number {
    return this.queue.length;
  }

  public override _read(): void {
    this.blocked = false;
    while (this.queue.length > 0) {
      const record = this.queue.shift()!;
      this.queuedBytes -= Buffer.byteLength(record, "utf8");
      if (!this.push(record)) {
        this.blocked = true;
        return;
      }
    }
    if (this.ending) this.push(null);
  }

  public override _destroy(error: Error | null, callback: (error?: Error | null) => void): void {
    this.queue.length = 0;
    this.queuedBytes = 0;
    callback(error);
  }
}
