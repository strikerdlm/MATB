import { useAppLocale } from "@/lib/i18n";
import type { OpenMatbBlockReceipt, OpenMatbReceipt, OpenMatbSession } from "@/types/openmatb";

const PROFILE: Record<string, [string, string]> = { PRACTICE: ["Práctica", "Practice"], LOW: ["Bajo", "Low"], MEDIUM: ["Medio", "Medium"], HIGH: ["Alto", "High"] };
const TASK: Record<string, [string, string]> = { starting: ["Abriendo", "Opening"], running: ["En curso", "In progress"], completed: ["Completada", "Completed"], failed: ["Error", "Failed"], aborted: ["Abortada", "Aborted"], interrupted: ["Interrumpida", "Interrupted"] };

export function BlockProgress({ session, receipt }: { session: OpenMatbSession; receipt: OpenMatbReceipt | null }) {
  const { copy } = useAppLocale();
  function outcomes(attempt: OpenMatbBlockReceipt, practice: boolean) {
    const saved = attempt.artifact_status === "saved" && (practice || attempt.ratings_status === "saved");
    return <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-2 text-sm">
      <div><dt className="inline text-muted-foreground">{copy("Tarea", "Task")}: </dt><dd className="inline">{TASK[attempt.task_status] ? copy(...TASK[attempt.task_status]) : copy("Sin confirmar", "Unconfirmed")}</dd></div>
      <div><dt className="inline text-muted-foreground">{copy("Escalas", "Ratings")}: </dt><dd className="inline">{practice ? copy("No se requieren", "Not required") : attempt.ratings_status === "saved" ? copy("Guardadas", "Saved") : copy("Pendientes", "Pending")}</dd></div>
      <div><dt className="inline text-muted-foreground">{copy("Guardado", "Saved")}: </dt><dd className="inline">{saved ? copy("Confirmado", "Confirmed") : copy("Por confirmar", "Not yet confirmed")}</dd></div>
    </dl>;
  }
  return <section aria-label={copy("Progreso de los bloques", "Block progress")} className="space-y-3">
    <h2 className="text-xl font-semibold">{copy("Bloques de la sesión", "Session blocks")}</h2>
    <ol className="grid gap-3 lg:grid-cols-2">{session.block_order.map((profile, index) => {
      const attempts = receipt?.attempts.filter(attempt => attempt.block_index === index) ?? [];
      const current = session.current_block_index === index;
      const awaitingActiveAttempt = current && Boolean(session.active_block) && !attempts.some(attempt => attempt.block_instance_id === session.active_block_instance_id);
      return <li key={`${profile}-${index}`} aria-current={current ? "step" : undefined} className={`min-w-0 rounded border p-4 ${current ? "border-info/50 bg-info/5" : "border-border"}`}>
        <h3 className="font-semibold">{index + 1}. {copy(...PROFILE[profile])}{current && <span className="ml-2 text-sm font-normal text-info">{copy("Actual", "Current")}</span>}</h3>
        {attempts.map((attempt, attemptIndex) => <div key={attempt.block_instance_id} className="mt-3 border-t border-border/50 pt-2">
          <p className="text-sm">{copy("Intento", "Attempt")} {attemptIndex + 1}</p>{outcomes(attempt, profile === "PRACTICE")}
        </div>)}
        {awaitingActiveAttempt && <div className="mt-3 border-t border-border/50 pt-2 text-sm" role="status"><p className="font-medium">{copy("Intento actual", "Current attempt")}</p><p>{copy("Consultando el estado de guardado de este intento…", "Checking save status for this attempt…")}</p></div>}
        {!attempts.length && !awaitingActiveAttempt && <p className="mt-2 text-sm text-muted-foreground">{index < session.current_block_index ? copy("Estado de guardado sin confirmar", "Save status unconfirmed") : current ? copy("Listo para iniciar cuando se cumplan los requisitos", "Ready to start when requirements are met") : copy("Pendiente", "Pending")}</p>}
        {current && !session.active_block && attempts.length > 0 && <p className="mt-3 text-sm">{copy("El siguiente inicio creará otro intento de este bloque.", "The next start will create another attempt of this block.")}</p>}
      </li>;
    })}</ol>
  </section>;
}
