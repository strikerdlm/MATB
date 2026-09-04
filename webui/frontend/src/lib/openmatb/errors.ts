import { OpenMatbApiError } from "@/lib/openmatb/api";

type Copy = (spanish: string, english: string) => string;

const MESSAGES: Record<string, [string, string]> = {
  openmatb_station_not_ready: ["La estación dejó de estar lista. Revise pantalla y dependencias en Preparar.", "The station is no longer ready. Review display and dependencies in Prepare."],
  assigned_liftoff_first: ["Su protocolo requiere completar Liftoff antes de OpenMATB en esta visita.", "Your protocol requires Liftoff before OpenMATB for this visit."],
  openmatb_active_session: [
    "Ya existe una sesión OpenMATB activa. Termine o aborte esa sesión antes de crear otra.",
    "An OpenMATB session is already active. Finish or abort it before creating another.",
  ],
  openmatb_dependency_missing: [
    "Faltan dependencias de OpenMATB. Cierre la consola y vuelva a abrirla con “01 - Abrir consola UAS”.",
    "OpenMATB dependencies are missing. Close the console and reopen it with “01 - Open UAS console”.",
  ],
  openmatb_launch_failed: [
    "OpenMATB se cerró antes de mostrar su ventana. Revise las comprobaciones de la estación y el registro del servicio.",
    "OpenMATB closed before showing its window. Review the station checks and service log.",
  ],
  openmatb_ready_timeout: [
    "OpenMATB no confirmó su ventana en 20 segundos. Verifique la pantalla seleccionada y vuelva a intentarlo.",
    "OpenMATB did not confirm its window within 20 seconds. Check the selected display and try again.",
  ],
  openmatb_job_assignment_failed: [
    "Windows no pudo supervisar el proceso de OpenMATB. Reinicie la consola antes de repetir.",
    "Windows could not supervise the OpenMATB process. Restart the console before retrying.",
  ],
  openmatb_invalid_transition: [
    "Esta acción no corresponde al paso actual. Actualice el panel y siga la acción resaltada.",
    "This action does not match the current step. Refresh the console and follow the highlighted action.",
  ],
  openmatb_request_failed: [
    "No se pudo completar la solicitud de OpenMATB.",
    "The OpenMATB request could not be completed.",
  ],
  backend_restart: [
    "La consola se reinició durante la sesión. Cree una sesión nueva.",
    "The console restarted during the session. Create a new session.",
  ],
};

export function openMatbErrorMessage(reason: unknown, copy: Copy, fallback?: [string, string]): string {
  const code = reason instanceof OpenMatbApiError
    ? reason.code
    : typeof reason === "string" ? reason : null;
  const known = code ? MESSAGES[code] : undefined;
  if (known) return copy(known[0], known[1]);
  if (reason instanceof Error && reason.message) return reason.message;
  const value = fallback ?? ["No se pudo completar la acción de OpenMATB.", "The OpenMATB action could not be completed."];
  return copy(value[0], value[1]);
}
