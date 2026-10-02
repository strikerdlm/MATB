"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Info, LockKeyhole } from "lucide-react";
import {
  abortOpenMatbVisualPreview,
  cloneOpenMatbVisualProfile,
  exportOpenMatbVisualProfile,
  getOpenMatbVisualPreview,
  importOpenMatbVisualProfile,
  listOpenMatbVisualProfiles,
  publishOpenMatbVisualProfile,
  startOpenMatbVisualPreview,
  updateOpenMatbVisualProfile,
  validateOpenMatbVisualProfile,
} from "@/lib/openmatb/api";
import { useAppLocale } from "@/lib/i18n";
import { openMatbErrorMessage } from "@/lib/openmatb/errors";
import type {
  OpenMatbVisualProfile,
  OpenMatbVisualProfileDocument,
  OpenMatbVisualProfilePalette,
  OpenMatbVisualPreview,
} from "@/types/openmatb";
import { ColorField, isHexColor } from "./ColorField";
import { CommunicationsPreview } from "./CommunicationsPreview";
import { CvdPreview } from "./CvdPreview";
import type { CvdType } from "./cvd";
import { PreviewPanel } from "./PreviewPanel";
import { ProfileManager } from "./ProfileManager";
import { ResourceManagementPreview } from "./ResourceManagementPreview";
import { SafetyColorControls } from "./SafetyColorControls";
import { SystemMonitoringPreview } from "./SystemMonitoringPreview";
import { ThemeToolbar } from "./ThemeToolbar";
import { TrackingPreview } from "./TrackingPreview";
import { WorkloadPreview } from "./WorkloadPreview";

const EMPTY_PREVIEW: OpenMatbVisualPreview = {
  lifecycle: "IDLE",
  profile_id: null,
  profile_version: null,
  profile_sha256: null,
  pid: null,
  artifact_root: null,
  last_error: null,
};

const PROFILE_ORDER = ["matb-daylight-avionics", "matb-fac-modern", "classic", "cockpit"];

type Modules = OpenMatbVisualProfileDocument["modules"];
type ModuleName = keyof Modules;

const deepCopy = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;
const identity = (profile: Pick<OpenMatbVisualProfile, "profile_id" | "version">) => `${profile.profile_id}@${profile.version}`;

function sortedProfiles(profiles: OpenMatbVisualProfile[]): OpenMatbVisualProfile[] {
  return [...profiles].sort((left, right) => {
    const leftIndex = PROFILE_ORDER.indexOf(left.profile_id);
    const rightIndex = PROFILE_ORDER.indexOf(right.profile_id);
    if (leftIndex !== rightIndex) return (leftIndex < 0 ? 99 : leftIndex) - (rightIndex < 0 ? 99 : rightIndex);
    return identity(left).localeCompare(identity(right));
  });
}

function ModuleColors<T extends object>({
  moduleName,
  values,
  labels,
  disabled,
  onPatch,
}: {
  moduleName: string;
  values: T;
  labels: Array<[keyof T, string]>;
  disabled: boolean;
  onPatch: (patch: Partial<T>) => void;
}) {
  return (
    <div className="fac-color-list">
      {labels.map(([key, label]) => (
        <ColorField
          key={String(key)}
          id={`${moduleName}-${String(key)}`}
          label={label}
          value={String(values[key])}
          disabled={disabled}
          onChange={(value) => onPatch({ [key]: value } as Partial<T>)}
        />
      ))}
    </div>
  );
}

function Toggle({
  id,
  label,
  checked,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  checked: boolean;
  disabled: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="fac-toggle" htmlFor={id}>
      <span>{label}</span>
      <input id={id} type="checkbox" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} />
    </label>
  );
}

export function AppearanceWorkbench() {
  const { copy } = useAppLocale();
  const appearanceError = useCallback(
    (reason: unknown) => openMatbErrorMessage(
      reason,
      copy,
      ["No se pudo completar la acción de apariencia.", "The appearance action could not be completed."],
    ),
    [copy],
  );
  const [profiles, setProfiles] = useState<OpenMatbVisualProfile[]>([]);
  const [selected, setSelected] = useState<OpenMatbVisualProfile | null>(null);
  const [preview, setPreview] = useState<OpenMatbVisualPreview>(EMPTY_PREVIEW);
  const [displayIndex, setDisplayIndex] = useState(1);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<string | null>("load");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cloneOpen, setCloneOpen] = useState(false);
  const [cvdType, setCvdType] = useState<CvdType>("normal");
  const [cvdSeverity, setCvdSeverity] = useState(100);
  const importRef = useRef<HTMLInputElement>(null);

  const replaceProfile = useCallback((profile: OpenMatbVisualProfile) => {
    setProfiles((current) => sortedProfiles([
      ...current.filter((candidate) => identity(candidate) !== identity(profile)),
      profile,
    ]));
    setSelected(deepCopy(profile));
    setDirty(false);
  }, []);

  useEffect(() => {
    let active = true;
    void Promise.all([listOpenMatbVisualProfiles(), getOpenMatbVisualPreview()])
      .then(([loadedProfiles, loadedPreview]) => {
        if (!active) return;
        const ordered = sortedProfiles(loadedProfiles);
        const preferred = ordered.find((profile) => profile.profile_id === "matb-daylight-avionics") ?? ordered[0];
        setProfiles(ordered);
        setSelected(preferred ? deepCopy(preferred) : null);
        setPreview(loadedPreview);
        setError(null);
      })
      .catch((caught) => { if (active) setError(appearanceError(caught)); })
      .finally(() => { if (active) setBusy(null); });
    return () => { active = false; };
  }, [appearanceError]);

  useEffect(() => {
    if (preview.lifecycle !== "STARTING" && preview.lifecycle !== "RUNNING") return;
    const timer = window.setInterval(() => {
      void getOpenMatbVisualPreview().then(setPreview).catch(() => undefined);
    }, 1200);
    return () => window.clearInterval(timer);
  }, [preview.lifecycle]);

  const edit = useCallback((updater: (profile: OpenMatbVisualProfile) => OpenMatbVisualProfile) => {
    setSelected((current) => current ? updater(deepCopy(current)) : current);
    setDirty(true);
    setNotice(null);
  }, []);

  const patchModule = useCallback(<K extends ModuleName>(name: K, patch: Partial<Modules[K]>) => {
    edit((profile) => {
      profile.payload.modules[name] = { ...profile.payload.modules[name], ...patch };
      return profile;
    });
  }, [edit]);

  const patchPalette = useCallback((key: keyof OpenMatbVisualProfilePalette, value: string) => {
    edit((profile) => {
      profile.payload.palette[key] = value;
      return profile;
    });
  }, [edit]);

  const allColorValues = useMemo(() => {
    if (!selected) return [];
    const moduleValues = Object.values(selected.payload.modules).flatMap((module) =>
      Object.values(module).filter((value): value is string => typeof value === "string" && value.startsWith("#")),
    );
    return [...Object.values(selected.payload.palette), ...moduleValues];
  }, [selected]);
  const localInvalid = allColorValues.some((value) => !isHexColor(value));

  const run = useCallback(async (name: string, action: () => Promise<OpenMatbVisualProfile>, message: string) => {
    setBusy(name); setError(null); setNotice(null);
    try {
      const result = await action();
      replaceProfile(result);
      setNotice(message);
    } catch (caught) {
      setError(appearanceError(caught));
    } finally {
      setBusy(null);
    }
  }, [appearanceError, replaceProfile]);

  if (busy === "load" && !selected) {
    return <div className="fac-loading" role="status">{copy("Cargando perfiles visuales…", "Loading visual profiles…")}</div>;
  }
  if (!selected) {
    return (
      <div className="fac-load-error" role="alert">
        <strong>{copy("No se pudo abrir Apariencia.", "Appearance could not be opened.")}</strong>
        <span>{error ?? copy("No hay perfiles visuales disponibles.", "No visual profiles are available.")}</span>
      </div>
    );
  }

  const editable = selected.status === "draft";
  const moduleThemes = selected.payload.modules;
  const selectProfile = (nextIdentity: string) => {
    if (dirty && !window.confirm(copy("¿Descartar los cambios no guardados?", "Discard unsaved changes?"))) return;
    const next = profiles.find((profile) => identity(profile) === nextIdentity);
    if (next) { setSelected(deepCopy(next)); setDirty(false); setError(null); setNotice(null); }
  };
  const toggleWarning = (code: string, acknowledged: boolean) => {
    edit((profile) => {
      const codes = new Set(profile.warning_acknowledgements);
      if (acknowledged) codes.add(code); else codes.delete(code);
      profile.warning_acknowledgements = [...codes].sort();
      return profile;
    });
  };
  const applySafety = () => edit((profile) => {
    const { safe, warning, critical } = profile.payload.palette;
    profile.payload.modules.tracking.cursor_outside = critical;
    profile.payload.modules.system_monitoring.feedback_positive = safe;
    profile.payload.modules.system_monitoring.feedback_negative = critical;
    profile.payload.modules.communications.positive = safe;
    profile.payload.modules.communications.negative = critical;
    profile.payload.modules.resource_management.pipe_on = safe;
    profile.payload.modules.resource_management.pump_on = safe;
    profile.payload.modules.resource_management.pump_failure = critical;
    profile.payload.modules.resource_management.tolerance = warning;
    return profile;
  });
  const exportProfile = async () => {
    setBusy("export"); setError(null);
    try {
      const payload = await exportOpenMatbVisualProfile(selected);
      const url = URL.createObjectURL(new Blob([`${JSON.stringify(payload, null, 2)}\n`], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${selected.profile_id}-${selected.version}.visual-profile.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      setNotice(copy("Perfil exportado.", "Profile exported."));
    } catch (caught) { setError(appearanceError(caught)); }
    finally { setBusy(null); }
  };
  const importProfile = async (file: File | undefined) => {
    if (!file) return;
    setBusy("import"); setError(null);
    try {
      const payload = JSON.parse(await file.text()) as OpenMatbVisualProfileDocument;
      replaceProfile(await importOpenMatbVisualProfile(payload));
      setNotice(copy("Perfil importado como borrador.", "Profile imported as a draft."));
    } catch (caught) { setError(appearanceError(caught)); }
    finally { setBusy(null); if (importRef.current) importRef.current.value = ""; }
  };
  const startPreview = async () => {
    setBusy("preview"); setError(null);
    try {
      setPreview(await startOpenMatbVisualPreview(selected, { display_index: displayIndex, windowed: true }));
      setNotice(copy("Vista previa nativa iniciada fuera de cualquier sesión de estudio.", "Native preview started outside every study session."));
    } catch (caught) { setError(appearanceError(caught)); }
    finally { setBusy(null); }
  };
  const stopPreview = async () => {
    setBusy("abort-preview"); setError(null);
    try { setPreview(await abortOpenMatbVisualPreview()); setNotice(copy("Vista previa nativa cerrada.", "Native preview closed.")); }
    catch (caught) { setError(appearanceError(caught)); }
    finally { setBusy(null); }
  };

  return (
    <div className="fac-workbench">
      <header className="fac-workbench-header">
        <div className="fac-brand-mark" aria-hidden="true">M</div>
        <div>
          <p>{copy("Consola de investigación · Apariencia", "Research Console · Appearance")}</p>
          <h1>MATB - FAC</h1>
        </div>
        <div className="fac-header-boundary">
          <LockKeyhole aria-hidden="true" />
          <span>{copy("Configuración del investigador", "Researcher configuration")}</span>
        </div>
      </header>

      <ThemeToolbar
        profiles={profiles}
        selected={selected}
        dirty={dirty}
        busy={busy}
        localInvalid={localInvalid}
        preview={preview}
        displayIndex={displayIndex}
        onSelect={selectProfile}
        onClone={() => setCloneOpen(true)}
        onSave={() => void run("save", () => updateOpenMatbVisualProfile(selected), copy("Borrador guardado.", "Draft saved."))}
        onValidate={() => void run("validate", () => validateOpenMatbVisualProfile(selected), copy("Validación actualizada.", "Validation refreshed."))}
        onPublish={() => void run("publish", () => publishOpenMatbVisualProfile(selected), copy("Perfil publicado e inmutable.", "Profile published and immutable."))}
        onImport={() => importRef.current?.click()}
        onExport={() => void exportProfile()}
        onPreview={() => void startPreview()}
        onAbortPreview={() => void stopPreview()}
        onDisplayIndex={(value) => setDisplayIndex(Math.min(15, Math.max(0, value || 0)))}
      />
      <input
        ref={importRef}
        className="sr-only"
        type="file"
        accept="application/json,.json"
        aria-label={copy("Importar perfil visual JSON", "Import visual profile JSON")}
        onChange={(event) => void importProfile(event.target.files?.[0])}
      />

      {(error || notice || dirty) && (
        <div className={`fac-status-banner ${error ? "fac-status-error" : dirty ? "fac-status-dirty" : "fac-status-success"}`} role={error ? "alert" : "status"}>
          {error ? <AlertTriangle aria-hidden="true" /> : dirty ? <Info aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}
          <span>{error ?? (dirty ? copy("Cambios sin guardar: la validación y la vista nativa corresponden a la última versión guardada.", "Unsaved changes: validation and native preview still refer to the last saved version.") : notice)}</span>
        </div>
      )}

      <div className="fac-workbench-grid">
        <aside className="fac-editor-column" aria-label={copy("Controles de apariencia", "Appearance controls")}>
          <section className="fac-editor-section">
            <div className="fac-section-heading"><h2>{copy("Identidad", "Identity")}</h2><span className={`fac-status-chip fac-status-${selected.status}`}>{selected.status === "published" ? copy("publicado", "published") : copy("borrador", "draft")}</span></div>
            <label className="fac-text-control"><span>{copy("Etiqueta", "Label")}</span><input disabled={!editable} value={selected.payload.label} onChange={(event) => edit((profile) => { profile.label = event.target.value; profile.payload.label = event.target.value; return profile; })} /></label>
            <dl className="fac-identity-data">
              <div><dt>ID</dt><dd>{selected.profile_id}</dd></div>
              <div><dt>{copy("Versión", "Version")}</dt><dd>{selected.version}</dd></div>
              <div><dt>SHA-256</dt><dd title={selected.sha256}>{selected.sha256.slice(0, 12)}…</dd></div>
              <div><dt>{copy("Geometría", "Geometry")}</dt><dd>preserve_openmatb_v1</dd></div>
            </dl>
            {!editable && <p className="fac-readonly-note"><LockKeyhole aria-hidden="true" />{copy("Publicado: clone para editar.", "Published: clone to edit.")}</p>}
          </section>

          <section className="fac-editor-section">
            <h2>{copy("Diseño y fondo", "Layout & background")}</h2>
            <div className="fac-metric-grid">
              <label><span>{copy("Ancho de línea", "Line width")}</span><input disabled={!editable} type="number" min="1" max="6" step="1" value={selected.payload.metrics.line_width} onChange={(event) => edit((profile) => { profile.payload.metrics.line_width = Number(event.target.value); return profile; })} /></label>
              <label><span>{copy("Radio de panel", "Panel radius")}</span><input disabled={!editable} type="number" min="0" max="24" step="1" value={selected.payload.metrics.panel_radius} onChange={(event) => edit((profile) => { profile.payload.metrics.panel_radius = Number(event.target.value); return profile; })} /></label>
              <label><span>{copy("Marcas de esquina", "Corner marks")}</span><input disabled={!editable} type="number" min="0" max="0.2" step="0.005" value={selected.payload.metrics.corner_mark_ratio} onChange={(event) => edit((profile) => { profile.payload.metrics.corner_mark_ratio = Number(event.target.value); return profile; })} /></label>
            </div>
          </section>

          <details className="fac-editor-section" open>
            <summary>{copy("Paleta global", "Global palette")}</summary>
            <SafetyColorControls palette={selected.payload.palette} disabled={!editable} onChange={patchPalette} onApplySafety={applySafety} />
          </details>

          <details className="fac-editor-section" open>
            <summary>TRACK</summary>
            <ModuleColors moduleName="tracking" values={moduleThemes.tracking} disabled={!editable} onPatch={(patch) => patchModule("tracking", patch)} labels={[
              ["panel", "Panel"], ["axis", copy("Eje", "Axis")], ["grid", copy("Cuadrícula", "Grid")], ["target", copy("Objetivo", "Target")], ["target_fill", copy("Relleno del objetivo", "Target fill")], ["cursor", "Cursor"], ["cursor_outside", copy("Cursor fuera", "Cursor outside")],
            ]} />
            <div className="fac-toggle-list">
              <Toggle id="tracking-panel" label={copy("Mostrar panel", "Show panel")} checked={moduleThemes.tracking.show_panel} disabled={!editable} onChange={(value) => patchModule("tracking", { show_panel: value })} />
              <Toggle id="tracking-grid" label={copy("Mostrar cuadrícula", "Show grid")} checked={moduleThemes.tracking.show_grid} disabled={!editable} onChange={(value) => patchModule("tracking", { show_grid: value })} />
              <Toggle id="tracking-border" label={copy("Borde cerrado del objetivo", "Closed target border")} checked={moduleThemes.tracking.closed_target_border} disabled={!editable} onChange={(value) => patchModule("tracking", { closed_target_border: value })} />
            </div>
          </details>

          <details className="fac-editor-section">
            <summary>SYSMON</summary>
            <ModuleColors moduleName="sysmon" values={moduleThemes.system_monitoring} disabled={!editable} onPatch={(patch) => patchModule("system_monitoring", patch)} labels={[
              ["panel", "Panel"], ["lamp_1", copy("Lámpara 1", "Lamp 1")], ["lamp_2", copy("Lámpara 2", "Lamp 2")], ["lamp_3", copy("Lámpara 3", "Lamp 3")], ["lamp_4", copy("Lámpara 4", "Lamp 4")], ["lamp_off", copy("Lámpara apagada", "Lamp off")], ["lamp_border", copy("Borde de lámpara", "Lamp border")], ["scale", copy("Escala", "Scale")], ["pointer", copy("Indicador", "Pointer")], ["feedback_positive", copy("Positivo", "Positive")], ["feedback_negative", copy("Negativo", "Negative")],
            ]} />
            <button className="fac-button fac-button-secondary fac-full-button" type="button" disabled={!editable} onClick={() => patchModule("system_monitoring", { lamp_2: moduleThemes.system_monitoring.lamp_1, lamp_3: moduleThemes.system_monitoring.lamp_1, lamp_4: moduleThemes.system_monitoring.lamp_1 })}>{copy("Igualar colores de lámparas", "Match all lamp colors")}</button>
            <label className="fac-text-control"><span>{copy("Forma de lámpara", "Lamp shape")}</span><select disabled={!editable} value={moduleThemes.system_monitoring.lamp_shape} onChange={(event) => patchModule("system_monitoring", { lamp_shape: event.target.value as "circle" | "rectangle" })}><option value="circle">{copy("Círculo", "Circle")}</option><option value="rectangle">{copy("Rectángulo", "Rectangle")}</option></select></label>
          </details>

          <details className="fac-editor-section">
            <summary>COMM</summary>
            <ModuleColors moduleName="communications" values={moduleThemes.communications} disabled={!editable} onPatch={(patch) => patchModule("communications", patch)} labels={[
              ["panel", "Panel"], ["display_background", copy("Pantalla", "Display")], ["display_border", copy("Borde de pantalla", "Display border")], ["active", copy("Activo", "Active")], ["inactive", copy("Inactivo", "Inactive")], ["positive", copy("Positivo", "Positive")], ["negative", copy("Negativo", "Negative")],
            ]} />
            <Toggle id="comm-bezel" label={copy("Mostrar marco de pantalla", "Show display bezel")} checked={moduleThemes.communications.show_display_bezel} disabled={!editable} onChange={(value) => patchModule("communications", { show_display_bezel: value })} />
          </details>

          <details className="fac-editor-section">
            <summary>RESMAN</summary>
            <ModuleColors moduleName="resource-management" values={moduleThemes.resource_management} disabled={!editable} onPatch={(patch) => patchModule("resource_management", patch)} labels={[
              ["panel", "Panel"], ["tank_1", copy("Tanque 1", "Tank 1")], ["tank_2", copy("Tanque 2", "Tank 2")], ["tank_3", copy("Tanque 3", "Tank 3")], ["tank_4", copy("Tanque 4", "Tank 4")], ["tank_5", copy("Tanque 5", "Tank 5")], ["tank_6", copy("Tanque 6", "Tank 6")], ["fluid", copy("Fluido", "Fluid")], ["pipe_on", copy("Tubería activa", "Pipe on")], ["pipe_off", copy("Tubería inactiva", "Pipe off")], ["pump_on", copy("Bomba activa", "Pump on")], ["pump_off", copy("Bomba apagada", "Pump off")], ["pump_failure", copy("Falla de bomba", "Pump failure")], ["tolerance", copy("Tolerancia", "Tolerance")], ["meter", copy("Medidor", "Meter")],
            ]} />
            <button className="fac-button fac-button-secondary fac-full-button" type="button" disabled={!editable} onClick={() => patchModule("resource_management", { tank_2: moduleThemes.resource_management.tank_1, tank_3: moduleThemes.resource_management.tank_1, tank_4: moduleThemes.resource_management.tank_1, tank_5: moduleThemes.resource_management.tank_1, tank_6: moduleThemes.resource_management.tank_1 })}>{copy("Igualar colores de tanques", "Match all tank colors")}</button>
            <Toggle id="pump-ring" label={copy("Mostrar anillo de bomba", "Show pump ring")} checked={moduleThemes.resource_management.show_pump_ring} disabled={!editable} onChange={(value) => patchModule("resource_management", { show_pump_ring: value })} />
          </details>

          <details className="fac-editor-section">
            <summary>{copy("Carga subjetiva", "Subjective workload")}</summary>
            <ModuleColors moduleName="workload" values={moduleThemes.workload} disabled={!editable} onPatch={(patch) => patchModule("workload", patch)} labels={[["panel", "Panel"], ["scale", copy("Escala", "Scale")], ["marker", copy("Marcador", "Marker")]]} />
          </details>
        </aside>

        <main className="fac-preview-column">
          <CvdPreview type={cvdType} severity={cvdSeverity} onTypeChange={setCvdType} onSeverityChange={setCvdSeverity}>
            <div className="fac-preview-grid" style={{ background: selected.payload.palette.app_background }}>
              <PreviewPanel title="TRACK" className="fac-preview-tracking" headerColor={selected.payload.palette.panel_header} headerText={selected.payload.palette.panel_header_text} borderColor={selected.payload.palette.border} radius={selected.payload.metrics.panel_radius}><TrackingPreview profile={selected.payload} /></PreviewPanel>
              <PreviewPanel title="SYSMON" headerColor={selected.payload.palette.panel_header} headerText={selected.payload.palette.panel_header_text} borderColor={selected.payload.palette.border} radius={selected.payload.metrics.panel_radius}><SystemMonitoringPreview profile={selected.payload} /></PreviewPanel>
              <PreviewPanel title="COMM" headerColor={selected.payload.palette.panel_header} headerText={selected.payload.palette.panel_header_text} borderColor={selected.payload.palette.border} radius={selected.payload.metrics.panel_radius}><CommunicationsPreview profile={selected.payload} /></PreviewPanel>
              <PreviewPanel title="RESMAN" className="fac-preview-resman" headerColor={selected.payload.palette.panel_header} headerText={selected.payload.palette.panel_header_text} borderColor={selected.payload.palette.border} radius={selected.payload.metrics.panel_radius}><ResourceManagementPreview profile={selected.payload} /></PreviewPanel>
              <PreviewPanel title={copy("Carga subjetiva", "Subjective workload")} className="fac-preview-workload" headerColor={selected.payload.palette.panel_header} headerText={selected.payload.palette.panel_header_text} borderColor={selected.payload.palette.border} radius={selected.payload.metrics.panel_radius}><WorkloadPreview profile={selected.payload} /></PreviewPanel>
            </div>
          </CvdPreview>
        </main>

        <aside className="fac-audit-column">
          <section className="fac-audit-card">
            <div className="fac-section-heading"><h2>{copy("Validación", "Validation")}</h2>{selected.validation.valid ? <CheckCircle2 aria-label={copy("Válido", "Valid")} /> : <AlertTriangle aria-label={copy("Inválido", "Invalid")} />}</div>
            {localInvalid && <p className="fac-issue fac-issue-error">{copy("Todos los colores deben usar #RRGGBB.", "Every color must use #RRGGBB.")}</p>}
            {selected.validation.errors.length === 0 && selected.validation.warnings.length === 0 && <p className="fac-empty-state">{copy("Sin problemas detectados.", "No issues detected.")}</p>}
            {selected.validation.errors.map((issue) => <div className="fac-issue fac-issue-error" key={issue.code}><strong>{copy(`El contraste ${issue.ratio.toFixed(2)}:1 es inferior a ${issue.minimum.toFixed(1)}:1`, issue.message)}</strong><span>{issue.ratio.toFixed(2)} : 1 · min {issue.minimum.toFixed(1)}</span></div>)}
            {selected.validation.warnings.map((issue) => {
              const checked = selected.warning_acknowledgements.includes(issue.code);
              return <label className="fac-warning-check" key={issue.code}><input type="checkbox" disabled={!editable} checked={checked} onChange={(event) => toggleWarning(issue.code, event.target.checked)} /><span><strong>{copy(`El contraste del estímulo ${issue.ratio.toFixed(2)}:1 es inferior al umbral de revisión ${issue.minimum.toFixed(1)}:1`, issue.message)}</strong><small>{issue.ratio.toFixed(2)} : 1 · min {issue.minimum.toFixed(1)}</small></span></label>;
            })}
            {dirty && <p className="fac-validation-stale">{copy("Guarde y vuelva a validar antes de publicar.", "Save and validate again before publishing.")}</p>}
          </section>

          <section className="fac-audit-card">
            <div className="fac-section-heading"><h2>{copy("Controles experimentales", "Experimental controls")}</h2><LockKeyhole aria-hidden="true" /></div>
            <p>{copy("Solo lectura aquí. Estos valores pertenecen al escenario o al preset de carga.", "Read-only here. These values belong to the scenario or workload preset.")}</p>
            <dl className="fac-behavior-list">
              <div><dt>{copy("Automatización", "Automation")}</dt><dd>{copy("Escenario", "Scenario")}</dd></div>
              <div><dt>VOG</dt><dd>{copy("Escenario", "Scenario")}</dd></div>
              <div><dt>{copy("Bombas / fallas", "Pump / failures")}</dt><dd>OpenMATB</dd></div>
              <div><dt>{copy("Tiempo de sondeos", "Probe timing")}</dt><dd>{copy("Preajuste", "Preset")}</dd></div>
              <div><dt>{copy("Activación de tareas", "Task activation")}</dt><dd>{copy("Escenario", "Scenario")}</dd></div>
              <div><dt>{copy("CVD del participante", "Participant CVD")}</dt><dd>{copy("No habilitado", "Not enabled")}</dd></div>
            </dl>
            <Link className="fac-inline-link" href="/openmatb/settings">{copy("Abrir configuración experimental", "Open experimental settings")}</Link>
          </section>

          <section className="fac-audit-card fac-boundary-card">
            <Info aria-hidden="true" />
            <p><strong>{copy("Límite de validez", "Validity boundary")}</strong></p>
            <p>{copy("La equivalencia del software no demuestra equivalencia perceptual, de carga de trabajo ni operacional entre apariencias.", "Software equivalence does not establish perceptual, workload, or operational equivalence between appearances.")}</p>
          </section>
        </aside>
      </div>

      <ProfileManager
        open={cloneOpen}
        source={selected}
        busy={busy === "clone"}
        onOpenChange={setCloneOpen}
        onClone={(value) => {
          setCloneOpen(false);
          void run("clone", () => cloneOpenMatbVisualProfile(selected, value), copy("Borrador clonado.", "Draft cloned."));
        }}
      />
    </div>
  );
}
