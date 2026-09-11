"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { getApiBase } from "@/lib/runtime-config";
import { useAppLocale } from "@/lib/i18n";
import { Button } from "@/components/ui/button";

export default function StudyRestorePage() {
  const { copy } = useAppLocale();
  const [actor, setActor] = useState("");
  const [reason, setReason] = useState("");
  const [maintenance, setMaintenance] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    void getApiBase()
      .then(async (api) => {
        const response = await fetch(api + "/station");
        if (!response.ok) throw new Error(String(response.status));
        const status = await response.json();
        if (active) setMaintenance(status.maintenance);
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
    };
  }, []);
  async function download() {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const api = await getApiBase();
      const response = await fetch(api + "/station/backups", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ actor, reason }),
      });
      if (!response.ok) {
        const result = await response.json();
        throw new Error(String(result.detail));
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "matb-whole-study.zip";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage(
        copy(
          "Copia verificada descargada. El mantenimiento permanece activo.",
          "Verified backup downloaded. Maintenance remains active.",
        ),
      );
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="mx-auto max-w-4xl space-y-4 p-4 sm:p-6">
      <h1 className="text-2xl font-semibold">
        {copy(
          "Copia y restauración del estudio",
          "Study backup and restoration",
        )}
      </h1>
      <p>
        {copy(
          "La copia incluye la base de datos, los registros originales, los planes y los resultados congelados. Requiere mantenimiento exclusivo con todos los registros detenidos.",
          "The backup includes the database, original recordings, plans and frozen results. It requires exclusive maintenance with all recording stopped.",
        )}
      </p>
      <Link className="underline" href="/station">
        {copy(
          "Gestionar mantenimiento de la estación",
          "Manage station maintenance",
        )}
      </Link>
      <p>
        {maintenance
          ? copy("Mantenimiento activo", "Maintenance active")
          : copy(
              "Inicie mantenimiento antes de descargar la copia.",
              "Begin maintenance before downloading the backup.",
            )}
      </p>
      <label className="block">
        {copy("Investigador", "Researcher")}
        <input
          className="native-input"
          value={actor}
          maxLength={200}
          onChange={(e) => setActor(e.target.value)}
        />
      </label>
      <label className="block">
        {copy("Motivo", "Reason")}
        <input
          className="native-input"
          value={reason}
          maxLength={2000}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      <Button
        disabled={!maintenance || busy || !actor.trim() || !reason.trim()}
        onClick={() => void download()}
      >
        {busy
          ? copy("Preparando copia…", "Preparing backup…")
          : copy("Descargar copia verificada", "Download verified backup")}
      </Button>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      <h2 className="text-lg font-semibold">
        {copy(
          "Restaurar en un espacio vacío",
          "Restore into an empty workspace",
        )}
      </h2>
      <p>
        {copy(
          "Con el servidor de destino detenido, ejecute la herramienta local con el identificador exacto del estudio. Nunca seleccione un espacio que ya contenga un estudio. La restauración verifica los archivos antes de activarlos y permanece en mantenimiento; las sesiones y los trabajos anteriores no se reanudan.",
          "With the destination server stopped, run the local tool with the exact study identifier. Choose a workspace that contains no study. Restoration verifies files before activation and remains in maintenance; previous sessions and jobs do not resume.",
        )}
      </p>
      <pre className="whitespace-pre-wrap break-all rounded border p-3 text-sm">
        {
          'python tools/study_workspace.py restore "matb-whole-study.zip" "empty-workspace" --study-id "study-id"\npython tools/study_workspace.py reproduce "empty-workspace" "offline-proof"'
        }
      </pre>
      <p>
        {copy(
          "Use las rutas y el nuevo archivo de credencial indicados en restore-report.json al iniciar el servidor restaurado. La reproducción instala exclusivamente las ruedas archivadas en un entorno nuevo, recalcula los descriptivos y conserva las figuras. Los archivos incompletos mantienen ese estado. La verificación de software no constituye validación física ni humana.",
          "Use the paths and new credential file recorded in restore-report.json when starting the restored server. Reproduction installs only archived wheels into a fresh environment, recalculates descriptive results and preserves figures. Incomplete artifacts remain incomplete. Software verification does not establish physical or human qualification.",
        )}
      </p>
    </main>
  );
}
