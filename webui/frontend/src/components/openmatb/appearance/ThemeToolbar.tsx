import { Copy, Download, Play, Save, ShieldCheck, Square, Upload } from "lucide-react";
import { useAppLocale } from "@/lib/i18n";
import type { OpenMatbVisualProfile, OpenMatbVisualPreview } from "@/types/openmatb";

export function ThemeToolbar({
  profiles,
  selected,
  dirty,
  busy,
  localInvalid,
  preview,
  displayIndex,
  onSelect,
  onClone,
  onSave,
  onValidate,
  onPublish,
  onImport,
  onExport,
  onPreview,
  onAbortPreview,
  onDisplayIndex,
}: {
  profiles: OpenMatbVisualProfile[];
  selected: OpenMatbVisualProfile;
  dirty: boolean;
  busy: string | null;
  localInvalid: boolean;
  preview: OpenMatbVisualPreview;
  displayIndex: number;
  onSelect: (identity: string) => void;
  onClone: () => void;
  onSave: () => void;
  onValidate: () => void;
  onPublish: () => void;
  onImport: () => void;
  onExport: () => void;
  onPreview: () => void;
  onAbortPreview: () => void;
  onDisplayIndex: (value: number) => void;
}) {
  const { copy } = useAppLocale();
  const editable = selected.status === "draft";
  const previewActive = preview.lifecycle === "STARTING" || preview.lifecycle === "RUNNING";
  const previewState = {
    STARTING: copy("iniciando", "starting"),
    RUNNING: copy("activa", "running"),
    FAILED: copy("fallida", "failed"),
  } as const;
  const publishDisabled = dirty || localInvalid || selected.validation.errors.length > 0
    || selected.validation.unacknowledged_warning_codes.length > 0;
  return (
    <section className="fac-toolbar" aria-label={copy("Acciones del perfil visual", "Visual profile actions")}>
      <label className="fac-profile-select">
        <span>{copy("Perfil visual", "Visual profile")}</span>
        <select
          aria-label={copy("Perfil visual", "Visual profile")}
          value={`${selected.profile_id}@${selected.version}`}
          onChange={(event) => onSelect(event.target.value)}
        >
          {profiles.map((profile) => (
            <option key={`${profile.profile_id}@${profile.version}`} value={`${profile.profile_id}@${profile.version}`}>
              {profile.label} · {profile.version} · {profile.status === "published" ? copy("publicado", "published") : copy("borrador", "draft")}
            </option>
          ))}
        </select>
      </label>
      <div className="fac-toolbar-actions">
        <button className="fac-button fac-button-secondary" type="button" disabled={Boolean(busy)} onClick={onClone}><Copy aria-hidden="true" />{copy("Clonar", "Clone")}</button>
        <button className="fac-button fac-button-primary" type="button" disabled={!editable || !dirty || localInvalid || Boolean(busy)} onClick={onSave}><Save aria-hidden="true" />{copy("Guardar borrador", "Save draft")}</button>
        <button className="fac-button fac-button-secondary" type="button" disabled={dirty || localInvalid || Boolean(busy)} onClick={onValidate}><ShieldCheck aria-hidden="true" />{copy("Validar", "Validate")}</button>
        <button className="fac-button fac-button-success" type="button" disabled={!editable || publishDisabled || Boolean(busy)} onClick={onPublish}><ShieldCheck aria-hidden="true" />{copy("Publicar", "Publish")}</button>
        <button className="fac-button fac-button-secondary" type="button" disabled={Boolean(busy)} onClick={onImport}><Upload aria-hidden="true" />{copy("Importar", "Import")}</button>
        <button className="fac-button fac-button-secondary" type="button" disabled={Boolean(busy)} onClick={onExport}><Download aria-hidden="true" />{copy("Exportar", "Export")}</button>
      </div>
      <div className="fac-native-preview-controls">
        <label>
          <span>{copy("Pantalla", "Display")}</span>
          <input min="0" max="15" type="number" value={displayIndex} onChange={(event) => onDisplayIndex(Number(event.target.value))} />
        </label>
        {previewActive ? (
          <button className="fac-button fac-button-danger" type="button" disabled={Boolean(busy)} onClick={onAbortPreview}><Square aria-hidden="true" />{copy("Cerrar vista nativa", "Stop native preview")}</button>
        ) : (
          <button className="fac-button fac-button-primary" type="button" disabled={dirty || localInvalid || Boolean(busy)} onClick={onPreview}><Play aria-hidden="true" />{copy("Abrir vista nativa", "Open native preview")}</button>
        )}
        <span className={`fac-preview-state fac-preview-state-${preview.lifecycle.toLowerCase()}`} role="status">
          {preview.lifecycle === "IDLE"
            ? copy("Vista inactiva", "Preview idle")
            : `${copy("Vista", "Preview")} ${previewState[preview.lifecycle]}`}
        </span>
      </div>
    </section>
  );
}
