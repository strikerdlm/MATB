import { OpenMatbApiError } from "@/lib/openmatb/api";

type Copy = (spanish: string, english: string) => string;

const MESSAGES: Record<string, [string, string]> = {
  openmatb_recovery_not_pending: ["La prueba ya comenzó. Use la pestaña que controla esa sesión.", "The test has already started. Use the tab controlling that session."],
  openmatb_native_recovery_required: ["Una tarea de la conexión anterior sigue abierta. Cierre esa ventana nativa y actualice la consola antes de continuar.", "A task from the previous connection is still open. Close that native window and refresh the console before continuing."],
  openmatb_display_discovery_failed: ["No se pudieron detectar las pantallas. Compruebe que la estación tenga una sesión gráfica activa y vuelva a comprobar.", "Displays could not be detected. Check that the station has an active desktop session, then check again."],
  openmatb_display_unavailable: ["La pantalla seleccionada ya no está conectada. Vuelva a Preparar y seleccione una pantalla disponible.", "The selected display is no longer connected. Return to Prepare and select an available display."],
  openmatb_evidence_processing_active: ["Se están procesando los resultados de la sesión anterior. Espere a que termine el procesamiento antes de abrir otra tarea.", "The previous session’s results are being processed. Wait for processing to finish before opening another task."],
  openmatb_block_identity_required: ["No se pudo identificar este bloque. Actualice la sesión antes de guardar las respuestas.", "This block could not be identified. Refresh the session before saving your ratings."],
  openmatb_block_mismatch: ["Estas respuestas pertenecen a otro bloque. Actualice la sesión; las respuestas no se transfieren entre bloques.", "These ratings belong to a different block. Refresh the session; ratings cannot transfer between blocks."],
  openmatb_scale_already_saved: ["Este bloque ya tiene respuestas guardadas. Actualice la sesión para continuar.", "Ratings for this block are already saved. Refresh the session to continue."],
  openmatb_evidence_wait_for_completion: ["El procesamiento comienza al finalizar o interrumpir la sesión.", "Processing starts after the session finishes or is interrupted."],
  openmatb_station_not_ready: ["La estación dejó de estar lista. Revise pantalla y dependencias en Preparar.", "The station is no longer ready. Review display and dependencies in Prepare."],
  assigned_liftoff_first: ["Su protocolo requiere completar Liftoff antes de OpenMATB en esta visita.", "Your protocol requires Liftoff before OpenMATB for this visit."],
  openmatb_active_session: [
    "Hay una sesión preparada en esta estación. Use Retomar sesión o Cerrar sesión pendiente antes de abrir otra.",
    "A session is already prepared on this station. Use Resume session or Close pending session before opening another.",
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
  visual_profile_already_exists: [
    "Ya existe un perfil visual con ese identificador y versión.",
    "A visual profile with that identifier and version already exists.",
  ],
  visual_profile_identity_mismatch: [
    "El identificador o la versión del documento no coincide con el perfil seleccionado.",
    "The document identifier or version does not match the selected profile.",
  ],
  visual_profile_import_collision: [
    "El perfil importado entra en conflicto con una versión existente.",
    "The imported profile conflicts with an existing version.",
  ],
  visual_profile_accessibility_errors: [
    "Corrija los errores esenciales de contraste antes de publicar.",
    "Fix the essential contrast errors before publishing.",
  ],
  visual_profile_warning_acknowledgement_invalid: [
    "Una advertencia reconocida ya no corresponde a la validación actual. Valide nuevamente.",
    "An acknowledged warning no longer matches the current validation. Validate again.",
  ],
  visual_profile_warning_acknowledgement_required: [
    "Reconozca todas las advertencias de discriminación visual antes de publicar.",
    "Acknowledge every visual-discrimination warning before publishing.",
  ],
  visual_profile_record_corrupt: [
    "El registro del perfil visual no supera la verificación de integridad.",
    "The visual-profile record failed its integrity check.",
  ],
  visual_profile_not_found: [
    "No se encontró el perfil visual solicitado.",
    "The requested visual profile was not found.",
  ],
  published_visual_profile_not_found: [
    "Seleccione una versión publicada del perfil visual.",
    "Select a published visual-profile version.",
  ],
  published_configuration_immutable: [
    "Las versiones publicadas son inmutables. Clone esta versión para editarla.",
    "Published versions are immutable. Clone this version to edit it.",
  ],
  openmatb_visual_profile_tampered: [
    "El perfil congelado de la sesión cambió o no coincide con su huella. Cree una sesión nueva.",
    "The session's frozen profile changed or no longer matches its hash. Create a new session.",
  ],
  openmatb_visual_preview_active: [
    "Ya hay una vista previa nativa activa. Ciérrela antes de continuar.",
    "A native preview is already active. Close it before continuing.",
  ],
  openmatb_controlled_process_active: [
    "No se puede abrir una vista previa mientras una sesión controlada está activa.",
    "A preview cannot be opened while a controlled session is active.",
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
