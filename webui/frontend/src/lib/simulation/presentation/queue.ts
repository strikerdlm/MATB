/** Retains every discrete event until acknowledged; retries use the same event ID. */
export class ExposureQueue<T> {
  private pending: T[] = [];
  private running = false;
  failed = false;
  constructor(private send: (item: T) => Promise<unknown>, private fail: (error: unknown) => void, private limit = 128) {}
  push(item: T) {
    if (this.failed) return;
    if (this.pending.length >= this.limit) { this.failed = true; this.fail(new Error("Presentation recording queue exhausted")); return; }
    this.pending.push(item);
    void this.drain();
  }
  async flush() {
    const deadline = Date.now() + 20000;
    while (this.pending.length || this.running) {
      if (this.failed) throw new Error("Presentation recording failed; the session cannot be sealed as complete");
      if (Date.now() > deadline) throw new Error("Presentation recording is still pending");
      await new Promise(resolve => setTimeout(resolve, 20));
    }
    if (this.failed) throw new Error("Presentation recording failed");
  }
  private async drain() {
    if (this.running) return;
    this.running = true;
    try {
      while (this.pending.length && !this.failed) {
        let last: unknown;
        let sent = false;
        for (let attempt = 0; attempt < 3; attempt++) {
          try { await this.send(this.pending[0]); sent = true; break; }
          catch (error) { last = error; if (attempt < 2) await new Promise(r => setTimeout(r, 200 * (attempt + 1))); }
        }
        if (!sent) { this.failed = true; this.fail(last); break; }
        this.pending.shift();
      }
    } finally { this.running = false; }
  }
}
export const presentationQueues = new Map<string, ExposureQueue<Record<string, unknown>>>();
export async function flushPresentation(sessionId: string) { await presentationQueues.get(sessionId)?.flush(); }
