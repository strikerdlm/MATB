"use client";
import { useAppLocale } from "@/lib/i18n";
import type { Binding } from "@/lib/study";
type Property = {
  type?: string;
  enum?: unknown[];
  const?: unknown;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  title?: string;
};
export function LiftoffBinding({
  config,
  schema,
  onChange,
}: {
  config: Binding;
  schema: unknown;
  onChange: (config: Binding) => void;
}) {
  const { copy } = useAppLocale();
  const properties =
    (schema as { properties?: Record<string, Property> })?.properties ?? {};
  const values = (config.configuration ?? {}) as Binding;
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <p className="sm:col-span-3">
        {copy(
          "Registre la configuración exacta del simulador y controlador. La disponibilidad física se comprueba al iniciar.",
          "Record the exact simulator and controller configuration. Physical readiness is checked at launch.",
        )}
      </p>
      {Object.entries(properties).map(([key, p]) => (
        <label key={key}>
          {p.title ?? key}
          {p.type === "boolean" ? (
            <select
              className="native-select block"
              value={values[key] === undefined ? "" : String(values[key])}
              onChange={(e) =>
                onChange({
                  ...config,
                  configuration: {
                    ...values,
                    [key]: e.target.value === "true",
                  },
                })
              }
            >
              <option value="">—</option>
              <option value="true">{copy("Sí", "Yes")}</option>
              <option value="false">No</option>
            </select>
          ) : p.const !== undefined ? (
            <p>{String(p.const)}</p>
          ) : (
            <input
              className="native-input block w-full"
              type={
                p.type === "number" || p.type === "integer" ? "number" : "text"
              }
              min={p.minimum ?? p.exclusiveMinimum}
              max={p.maximum}
              value={String(values[key] ?? "")}
              onChange={(e) =>
                onChange({
                  ...config,
                  configuration: {
                    ...values,
                    [key]:
                      p.type === "number" || p.type === "integer"
                        ? Number(e.target.value)
                        : e.target.value,
                  },
                })
              }
            />
          )}
        </label>
      ))}
    </div>
  );
}
export function MissionBinding({
  config,
  scenarios,
  onChange,
}: {
  config: Binding;
  scenarios: unknown;
  onChange: (config: Binding) => void;
}) {
  const { copy } = useAppLocale();
  const rows = (scenarios ?? []) as { id: string; sha256: string }[];
  return (
    <div className="space-y-3">
      <label>
        {copy(
          "Escenario publicado y huella exacta",
          "Published scenario and exact fingerprint",
        )}
        <select
          className="native-select block"
          value={JSON.stringify(config.scenario ?? {})}
          onChange={(e) =>
            onChange({ ...config, scenario: JSON.parse(e.target.value) })
          }
        >
          <option value="{}">—</option>
          {rows.map((row) => (
            <option key={row.id} value={JSON.stringify(row)}>
              {row.id} · {row.sha256.slice(0, 8)}
            </option>
          ))}
        </select>
      </label>
      <p>
        {copy(
          "Presentación estándar 2D con controles existentes. El protocolo de misión incluye su bloque de práctica; el orden LOW/MEDIUM/HIGH se define por brazo.",
          "Standard 2D presentation with existing controls. The mission protocol includes its practice block; each arm defines the LOW/MEDIUM/HIGH order.",
        )}
      </p>
    </div>
  );
}
