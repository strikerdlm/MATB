import type { OpenMatbVisualProfilePalette } from "@/types/openmatb";
import { useAppLocale } from "@/lib/i18n";
import { ColorField } from "./ColorField";

type PaletteField = [keyof OpenMatbVisualProfilePalette, string, string];

const SURFACE_FIELDS: PaletteField[] = [
  ["app_background", "Aplicación", "Application"],
  ["panel_background", "Panel", "Panel"],
  ["instrument_background", "Instrumento", "Instrument"],
  ["panel_header", "Encabezado de panel", "Panel header"],
  ["panel_header_text", "Texto de encabezado", "Header text"],
  ["border", "Bordes", "Borders"],
  ["grid", "Cuadrícula", "Grid"],
  ["disabled", "Deshabilitado", "Disabled"],
];

const TEXT_FIELDS: PaletteField[] = [
  ["text", "Texto principal", "Primary text"],
  ["muted_text", "Texto secundario", "Muted text"],
  ["control_background", "Fondo de control", "Control fill"],
  ["control_foreground", "Texto de control", "Control text"],
  ["accent", "Acento", "Accent"],
];

const SAFETY_FIELDS: PaletteField[] = [
  ["safe", "Seguro / positivo", "Safe / positive"],
  ["warning", "Advertencia", "Warning"],
  ["critical", "Crítico / falla", "Critical / failure"],
];

function FieldSet({
  legend,
  fields,
  translate,
  palette,
  disabled,
  onChange,
}: {
  legend: string;
  fields: PaletteField[];
  translate: (spanish: string, english: string) => string;
  palette: OpenMatbVisualProfilePalette;
  disabled: boolean;
  onChange: (key: keyof OpenMatbVisualProfilePalette, value: string) => void;
}) {
  return (
    <fieldset className="fac-control-group">
      <legend>{legend}</legend>
      <div className="fac-color-list">
        {fields.map(([key, spanish, english]) => (
          <ColorField
            key={key}
            id={`palette-${key}`}
            label={translate(spanish, english)}
            value={palette[key]}
            disabled={disabled}
            onChange={(value) => onChange(key, value)}
          />
        ))}
      </div>
    </fieldset>
  );
}

export function SafetyColorControls({
  palette,
  disabled,
  onChange,
  onApplySafety,
}: {
  palette: OpenMatbVisualProfilePalette;
  disabled: boolean;
  onChange: (key: keyof OpenMatbVisualProfilePalette, value: string) => void;
  onApplySafety: () => void;
}) {
  const { copy } = useAppLocale();
  return (
    <div className="fac-controls-stack">
      <FieldSet legend={copy("Superficies", "Surfaces")} fields={SURFACE_FIELDS} translate={copy} palette={palette} disabled={disabled} onChange={onChange} />
      <FieldSet legend={copy("Texto y controles", "Text & controls")} fields={TEXT_FIELDS} translate={copy} palette={palette} disabled={disabled} onChange={onChange} />
      <FieldSet legend={copy("Colores de seguridad", "Safety colors")} fields={SAFETY_FIELDS} translate={copy} palette={palette} disabled={disabled} onChange={onChange} />
      <button className="fac-button fac-button-secondary" type="button" disabled={disabled} onClick={onApplySafety}>
        {copy("Aplicar colores de seguridad a los módulos", "Apply safety colors to modules")}
      </button>
    </div>
  );
}
