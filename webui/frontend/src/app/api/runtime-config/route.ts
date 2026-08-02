import { NextResponse } from "next/server";

const DEFAULT_BACKEND_PORT = 8000;

export const dynamic = "force-dynamic";

function backendPort(): number | null {
  const raw = process.env.MATB_BACKEND_PORT;
  if (raw === undefined || raw.trim() === "") return DEFAULT_BACKEND_PORT;
  if (!/^\d+$/.test(raw.trim())) return null;
  const value = Number(raw);
  return Number.isInteger(value) && value >= 1 && value <= 65535 ? value : null;
}

export function GET(): NextResponse {
  const port = backendPort();
  if (port === null) {
    return NextResponse.json(
      { detail: { code: "invalid_backend_port", message: "MATB_BACKEND_PORT must be an integer between 1 and 65535" } },
      { status: 500, headers: { "Cache-Control": "no-store" } },
    );
  }
  return NextResponse.json(
    { backend_port: port },
    { headers: { "Cache-Control": "no-store" } },
  );
}
