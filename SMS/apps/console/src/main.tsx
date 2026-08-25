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
