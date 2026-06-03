"use client";
import type { TrackerCell } from "@/types";
export function CellDetailDialog({ cell, onClose }: { cell: TrackerCell | null; onClose: () => void }) {
  void onClose;
  return cell ? null : null;
}
