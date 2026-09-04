type Copy = (spanish: string, english: string) => string;
const messages: Record<string, [string, string]> = {
  study_pvt_required: ["Primero complete una PVT de estudio válida para esta visita. Abra KSS + PVT en el catálogo.", "First complete a valid study PVT for this visit. Open KSS + PVT in the catalog."],
  study_context_required: ["El investigador debe guardar su asignación de protocolo en Participantes.", "The researcher must save your protocol assignment in Participants."],
  assigned_matb_first: ["Su protocolo requiere completar OpenMATB antes de Liftoff en esta visita.", "Your protocol requires OpenMATB before Liftoff for this visit."],
  liftoff_telemetry_not_ready: ["No se reciben datos de Liftoff. Abra el simulador y vuelva a comprobar la telemetría.", "No Liftoff data is arriving. Open the simulator and check telemetry again."],
  liftoff_invalid_lease: ["Falta la autorización de control de esta sesión. Abra la sesión desde la ventana donde la preparó.", "Session control authorization is missing. Open the session in the window where you prepared it."],
  polar_device_not_connected: ["Conecte el Polar H10 antes de preparar la captura.", "Connect Polar H10 before preparing the recording."],
  polar_session_identity_or_purpose_mismatch: ["La sesión y la captura deben usar el mismo participante y modo. Revise los datos seleccionados.", "The session and recording must use the same participant and mode. Review the selected details."],
  polar_capture_already_active: ["Ya hay una captura activa. Finalícela antes de preparar otra.", "A recording is already active. Finish it before preparing another."],
};
export function experimentErrorMessage(reason: unknown, copy: Copy): string {
  const code = reason && typeof reason === "object" && "code" in reason ? String(reason.code) : "";
  const known = messages[code];
  if (known) return copy(...known);
  return copy("No se pudo completar la operación. Compruebe la conexión y el paso actual; sus selecciones se conservan.", "Could not complete the operation. Check the connection and current step; your selections are preserved.");
}
