type Copy = (spanish: string, english: string) => string;
const messages: Record<string, [string, string]> = {
  participant_not_found: ["El participante no está registrado. Selecciónelo en la lista o regístrelo en Participantes antes de preparar la captura.", "The participant is not registered. Select one from the list or register them in Participants before preparing the recording."],
  participant_archived: ["El participante está archivado. Restáurelo en Participantes antes de preparar la captura.", "The participant is archived. Restore them in Participants before preparing the recording."],
  study_assignment_required: ["Seleccione la evaluación asignada en Asignaciones antes de preparar una captura de estudio.", "Select the assigned assessment in Assignments before preparing a study recording."],
  polar_request_invalid: ["Revise el participante, la sesión y los ajustes de captura; hay datos incompletos o no válidos.", "Review the participant, session and capture settings; some details are missing or invalid."],
  station_visit_reserved: ["Una visita asignada reserva la estación. Finalice esa visita antes de iniciar un registro independiente.", "An assigned visit reserves the station. Finish that visit before starting a standalone recording."],
  station_acquisition_conflict: ["Hay otra adquisición incompatible en curso. Finalícela antes de iniciar este registro.", "Another incompatible acquisition is active. Finish it before starting this recording."],
  station_heavy_work_active: ["La estación está procesando datos o en mantenimiento. Espere a que termine antes de iniciar el registro.", "The station is processing data or under maintenance. Wait for it to finish before starting recording."],
  station_recovery_required: ["La estación conserva una adquisición interrumpida. Revise su estado y recupérela desde Estación antes de iniciar.", "The station retains an interrupted acquisition. Review and recover it from Station before starting."],
  study_pvt_required: ["Primero complete una PVT de estudio válida para esta visita. Abra KSS + PVT en el catálogo.", "First complete a valid study PVT for this visit. Open KSS + PVT in the catalog."],
  study_context_required: ["El investigador debe guardar su asignación de protocolo en Participantes.", "The researcher must save your protocol assignment in Participants."],
  assigned_matb_first: ["Su protocolo requiere completar OpenMATB antes de Liftoff en esta visita.", "Your protocol requires OpenMATB before Liftoff for this visit."],
  liftoff_telemetry_not_ready: ["No se reciben datos de Liftoff. Abra el simulador y vuelva a comprobar la telemetría.", "No Liftoff data is arriving. Open the simulator and check telemetry again."],
  liftoff_invalid_lease: ["Falta la autorización de control de esta sesión. Abra la sesión desde la ventana donde la preparó.", "Session control authorization is missing. Open the session in the window where you prepared it."],
  polar_invalid_controller_lease: ["Esta pestaña no tiene autorización de control. Vuelva a la pestaña que inició la captura.", "This tab has no valid control lease. Return to the owning browser tab."],
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
