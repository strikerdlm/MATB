"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { getApiBase } from "@/lib/runtime-config";
import { useAppLocale } from "@/lib/i18n";
import { Button } from "@/components/ui/button";

type Job = {
  id: string;
  kind: string;
  status: string;
  error: string | null;
  result_json: string | null;
  started_at: string | null;
};
type State = {
  reservation: {
    owner: string;
    participant?: string;
    visit?: number;
    uncertain?: boolean;
  } | null;
  acquisitions: Record<string, { instrument: string; held: boolean }>;
  maintenance: boolean;
  queue_limit: number;
};
export default function StationPage() {
  const { copy } = useAppLocale();
  const [state, setState] = useState<State | null>(null),
    [jobs, setJobs] = useState<Job[]>([]),
    [error, setError] = useState("");
  const [actor, setActor] = useState(""),
    [reason, setReason] = useState(""),
    [api, setApi] = useState(""),
    [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    const base = await getApiBase();
    setApi(base);
    const [station, pending] = await Promise.all([
      fetch(base + "/station"),
      fetch(base + "/station/jobs"),
    ]);
    if (!station.ok || !pending.ok)
      throw new Error("Station status unavailable");
    setState(await station.json());
    setJobs(await pending.json());
  }, []);
  useEffect(() => {
    void load().catch((e) => setError(String(e)));
    const timer = setInterval(
      () => void load().catch((e) => setError(String(e))),
      2000,
    );
    return () => clearInterval(timer);
  }, [load]);
  async function action(path: string, body: unknown = { actor, reason }) {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(api + "/station" + path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const result = await response.json();
      if (!response.ok)
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : result.detail?.message,
        );
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="mx-auto max-w-4xl space-y-4 p-6">
      <h1 className="text-2xl font-semibold">
        {copy("Estación y trabajos pendientes", "Station and pending work")}
      </h1>
      {error && <p role="alert">{error}</p>}
      <p>
        {state?.reservation
          ? copy(
              "Visita protegida: las tareas pesadas esperan al cierre explícito.",
              "Visit protected: heavy work waits for explicit closure.",
            )
          : state?.maintenance
            ? copy(
                "Mantenimiento activo; la adquisición está bloqueada.",
                "Maintenance active; acquisition is blocked.",
              )
            : copy(
                "Sin reserva de visita. Un trabajo activo bloquea la adquisición.",
                "No visit reservation. An active job blocks acquisition.",
              )}
      </p>
      {state?.reservation && (
        <p>
          {state.reservation.owner} · {state.reservation.participant} ·{" "}
          {state.reservation.visit}
        </p>
      )}
      {state?.reservation?.uncertain && (
        <p role="status">
          {copy(
            "Propiedad incierta: cierre el navegador de adquisición, detenga los registros y verifique físicamente la estación antes de recuperar.",
            "Ownership uncertain: close the acquisition browser, stop recordings and physically check the station before idle recovery.",
          )}
        </p>
      )}
      <ul>
        {Object.entries(state?.acquisitions ?? {}).map(([id, a]) => (
          <li key={id}>
            {a.instrument} · {id} ·{" "}
            {a.held
              ? copy("preparado en espera", "held preflight")
              : copy("adquisición", "acquisition")}
          </li>
        ))}
      </ul>
      <p>
        {copy(
          "Use el control de cada instrumento para detener la tarea y cerrar su registro. Las escalas y la recuperación permanecen protegidas.",
          "Use each instrument controller to stop its task and close its recording. Ratings and recovery remain protected.",
        )}
      </p>
      <div className="flex gap-4">
        <Link href="/study/participant">
          {copy("Visita asignada", "Assigned visit")}
        </Link>
        <Link href="/physiology/polar-h10">
          {copy("Control H10", "H10 controller")}
        </Link>
        <Link href="/openmatb/setup">
          {copy("Control MATB", "MATB controller")}
        </Link>
      </div>
      <label className="block">
        {copy("Investigador", "Researcher")}
        <input
          className="native-input"
          value={actor}
          onChange={(e) => setActor(e.target.value)}
        />
      </label>
      <label className="block">
        {copy("Motivo y verificación", "Reason and verification")}
        <input
          className="native-input"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      <div className="flex flex-wrap gap-2">
        <Button
          disabled={busy || !actor.trim() || !reason.trim()}
          onClick={() => void action("/close")}
        >
          {copy("Cerrar visita", "Close visit")}
        </Button>
        <Button
          disabled={busy || !actor.trim() || !reason.trim()}
          onClick={() => void action("/recover-idle")}
        >
          {copy("Confirmar estación inactiva", "Confirm station idle")}
        </Button>
        <Button
          disabled={busy || !actor.trim() || !reason.trim()}
          onClick={() =>
            void action("/maintenance", {
              actor,
              reason,
              enabled: !state?.maintenance,
            })
          }
        >
          {state?.maintenance
            ? copy("Terminar mantenimiento", "End maintenance")
            : copy("Iniciar mantenimiento", "Begin maintenance")}
        </Button>
      </div>
      <Link className="underline" href="/study/restore">
        {copy(
          "Copia y restauración del estudio",
          "Study backup and restoration",
        )}
      </Link>
      <h2>
        {copy("Cola durable", "Durable queue")} · {state?.queue_limit}
      </h2>
      {jobs.map((job) => (
        <article key={job.id} className="rounded border p-3">
          <p>
            {job.kind} · {job.status} · {job.id}
          </p>
          {job.error && <p>{job.error}</p>}
          {["queued", "waiting_capacity", "running", "cancelling"].includes(
            job.status,
          ) && (
            <Button
              disabled={busy || job.status === "cancelling"}
              onClick={() => void action("/jobs/" + job.id + "/cancel", {})}
            >
              {copy("Solicitar cancelación", "Request cancellation")}
            </Button>
          )}
          {job.status === "cancelling" && (
            <p>
              {copy(
                "La capacidad sigue ocupada hasta que el trabajo termine realmente.",
                "Capacity remains owned until the actual worker ends.",
              )}
            </p>
          )}
          {job.result_json && (
            <a href={api + "/station/jobs/" + job.id + "/artifact"}>
              {copy("Abrir resultado del trabajo", "Open job result")}
            </a>
          )}
        </article>
      ))}
    </div>
  );
}
