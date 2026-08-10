import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AppShell } from "./app/AppShell.js";
import "./styles/tokens.css";
import "./styles/operational.css";

const root = document.getElementById("root");
if (root === null) throw new Error("console root is missing");

createRoot(root).render(
  <StrictMode>
    <AppShell />
  </StrictMode>,
);

export { AppShell } from "./app/AppShell.js";
export { MissionSafetyStrip } from "./components/MissionSafetyStrip.js";
export { GateStatus } from "./components/GateStatus.js";
export { ChecklistPanel } from "./components/ChecklistPanel.js";
export { AlertTimeline } from "./components/AlertTimeline.js";
export { MapWorkspace } from "./components/MapWorkspace.js";
export { TelemetryPanel } from "./components/TelemetryPanel.js";
export { RiskPanel } from "./components/RiskPanel.js";
export { useMissionSafety } from "./hooks/useMissionSafety.js";
export { useTelemetry } from "./hooks/useTelemetry.js";
