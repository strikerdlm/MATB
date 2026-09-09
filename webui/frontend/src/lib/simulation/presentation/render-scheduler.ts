/** Coalesce invalidations into one submission; idle scenes own no frame loop. */
export function renderScheduler(draw: () => void) {
  let frame: number | null = null, disposed = false;
  const flush = () => {
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
    if (!disposed) draw();
  };
  return {
    request() {
      if (disposed || frame !== null) return;
      frame = requestAnimationFrame(flush);
    },
    flush,
    dispose() {
      disposed = true;
      if (frame !== null) cancelAnimationFrame(frame);
      frame = null;
    },
  };
}
