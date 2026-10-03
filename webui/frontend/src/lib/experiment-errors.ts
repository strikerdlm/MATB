type Copy = (spanish: string, english: string) => string;
const messages: Record<string, [string, string]> = {
  study_pvt_required: ["Primero complete una PVT de estudio válida para esta visita. Abra KSS + PVT en el catálogo.", "First complete a valid study PVT for this visit. Open KSS + PVT in the catalog."],
  study_context_required: ["El investigador debe guardar su asignación de protocolo en Participantes.", "The researcher must save your protocol assignment in Participants."],
  assigned_matb_first: ["Su protocolo requiere completar OpenMATB antes de Liftoff en esta visita.", "Your protocol requires OpenMATB before Liftoff for this visit."],
  liftoff_telemetry_not_ready: ["No se reciben datos de Liftoff. Abra el simulador y vuelva a comprobar la telemetría.", "No Liftoff data is arriving. Open the simulator and check telemetry again."],
  liftoff_invalid_lease: ["Falta la autorización de control de esta sesión. Abra la sesión desde la ventana donde la preparó.", "Session control authorization is missing. Open the session in the window where you prepared it."],
  station_visit_reserved: ["Otra visita ocupa la estación. Abra Estación y finalice la sesión correspondiente; no se omitirán los bloqueos.", "Another visit owns the station. Open Station and finish the owning session; locks will not be bypassed."],
  station_acquisition_conflict: ["Hay otra adquisición incompatible activa. Deténgala desde sus propios controles antes de iniciar esta captura.", "Another incompatible acquisition is active. Stop it through its own controls before starting this capture."],
  station_recovery_required: ["La estación requiere recuperación explícita. Revise su estado en Estación.", "The station requires explicit recovery. Review its status on Station."],
  polar_invalid_controller_lease: ["Esta pestaña no tiene autorización de control. Vuelva a la pestaña que inició la captura.", "This tab has no valid control lease. Return to the owning browser tab."],
  polar_request_invalid: ["La solicitud fue rechazada por validación. Revise los campos y que la interfaz y el servidor en ejecución correspondan a la misma versión.", "Request validation failed. Check the fields and that the interface and running backend use matching versions."],
  participant_not_found: ["Este pseudónimo no está registrado. Use el pseudónimo previsto de Participantes o registre uno nuevo; no use el de otra persona.", "This pseudonym is not registered. Use the intended pseudonym from Participants or register a new one; do not use another person’s identity."],
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
