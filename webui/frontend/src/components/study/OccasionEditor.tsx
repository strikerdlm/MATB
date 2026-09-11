"use client";
import { LiftoffBinding, MissionBinding } from "./OptionalBindings";
import { Button } from "@/components/ui/button";
import { useAppLocale } from "@/lib/i18n";
import type { Binding, StudyOccasion, StudyPayload } from "@/lib/study";

export function OccasionEditor({
  occasion: o,
  study,
  bindings,
  onChange,
  onRemove,
}: {
  occasion: StudyOccasion;
  study: StudyPayload["study"];
  bindings: Record<string, unknown>;
  onChange: (next: StudyOccasion) => void;
  onRemove: () => void;
}) {
  const { copy } = useAppLocale();
  const native = bindings.openmatb as
    | Record<string, { id: string; version: string; sha256: string }[]>
    | undefined;
  function changeInstrument(instrument: StudyOccasion["instrument"]) {
    let config: Binding =
      (bindings[instrument] as Binding[] | undefined)?.[0] ?? {};
    if (instrument === "openmatb")
      config = {
        preset: native?.presets[0] ?? {},
        instructions: native?.instructions[0] ?? {},
        visual: native?.visuals[0] ?? {},
        input_mapping: "openmatb-default",
        scenario_generator: "published-preset-v1",
        scoring: "openmatb-current",
      };
    if (instrument === "liftoff")
      config = {
        binding_id: "liftoff-telemetry-all-v1",
        input_mapping: "liftoff-telemetry-all-v1",
        scoring: "liftoff-current",
        configuration: { telemetry_profile: "liftoff-telemetry-all-v1" },
      };
    if (instrument === "suas")
      config = {
        binding_id: "suas-protocol-v1",
        input_mapping: "suas-default",
        scoring: "suas-current",
        practice_included: true,
        presentation: null,
        scenario: (bindings.suas as Binding[] | undefined)?.[0] ?? {},
      };
    if (instrument === "questionnaire")
      config = {
        binding_id: "MATB-FAC-WORKLOAD-1.0",
        input_mapping: "browser-ratings",
        scoring: "rtlx-mean-bedford",
      };
    onChange({ ...o, instrument, config });
  }
  return (
    <fieldset className="space-y-3 rounded border border-white/15 p-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <label>
          {copy("Identidad de ocasión", "Occasion key")}
          <input
            className="native-input block w-full"
            value={o.key}
            onChange={(e) => onChange({ ...o, key: e.target.value })}
          />
        </label>
        <label>
          {copy("Visita", "Visit")}
          <select
            className="native-select block w-full"
            value={o.visit_ordinal}
            onChange={(e) =>
              onChange({ ...o, visit_ordinal: Number(e.target.value) })
            }
          >
            {study.visits.map((v) => (
              <option key={v.ordinal} value={v.ordinal}>
                {v.code}
              </option>
            ))}
          </select>
        </label>
        <label>
          {copy("Instrumento", "Instrument")}
          <select
            className="native-select block w-full"
            value={o.instrument}
            onChange={(e) =>
              changeInstrument(e.target.value as StudyOccasion["instrument"])
            }
          >
            {[
              "pvt",
              "screen",
              ...(bindings.openmatb ? ["openmatb", "questionnaire"] : []),
              ...(bindings.physiology ? ["physiology"] : []),
              ...(bindings.liftoff_schema ? ["liftoff"] : []),
              ...(bindings.suas ? ["suas"] : []),
            ].map((i) => (
              <option key={i}>{i}</option>
            ))}
          </select>
        </label>
        <label>
          {copy("Fase", "Phase")}
          <input
            className="native-input block w-full"
            value={o.phase}
            onChange={(e) => onChange({ ...o, phase: e.target.value })}
          />
        </label>
        <label>
          {copy("Orden", "Order")}
          <input
            type="number"
            min={1}
            className="native-input block w-full"
            value={o.order}
            onChange={(e) => onChange({ ...o, order: Number(e.target.value) })}
          />
        </label>
        <label>
          {copy("Idioma congelado", "Frozen language")}
          <select
            className="native-select block w-full"
            value={o.locale}
            onChange={(e) =>
              onChange({
                ...o,
                locale: e.target.value as StudyOccasion["locale"],
              })
            }
          >
            <option value="es-419">Español</option>
            <option value="en">English</option>
          </select>
        </label>
      </div>
      <div className="flex flex-wrap gap-3">
        {study.arms.map((arm) => (
          <label key={arm}>
            {copy("Condición para", "Condition for")} {arm}
            {o.instrument === "openmatb" || o.instrument === "suas" ? (
              <select
                className="native-select block"
                value={o.condition_by_arm[arm] ?? ""}
                onChange={(e) =>
                  onChange({
                    ...o,
                    condition_by_arm: {
                      ...o.condition_by_arm,
                      [arm]: e.target.value,
                    },
                  })
                }
              >
                <option value="">—</option>
                {(o.instrument === "suas"
                  ? [
                      "LOW_MEDIUM_HIGH",
                      "LOW_HIGH_MEDIUM",
                      "MEDIUM_LOW_HIGH",
                      "MEDIUM_HIGH_LOW",
                      "HIGH_LOW_MEDIUM",
                      "HIGH_MEDIUM_LOW",
                    ]
                  : ["LOW", "MEDIUM", "HIGH"]
                ).map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            ) : (
              <input
                className="native-input block"
                value={o.condition_by_arm[arm] ?? ""}
                onChange={(e) =>
                  onChange({
                    ...o,
                    condition_by_arm: {
                      ...o.condition_by_arm,
                      [arm]: e.target.value,
                    },
                  })
                }
              />
            )}
          </label>
        ))}
      </div>
      {o.instrument === "openmatb" && (
        <div className="grid gap-3 sm:grid-cols-3">
          {(
            [
              ["preset", "presets"],
              ["instructions", "instructions"],
              ["visual", "visuals"],
            ] as const
          ).map(([key, group]) => (
            <label key={key}>
              {key === "preset"
                ? copy("Preajuste publicado", "Published preset")
                : key === "instructions"
                  ? copy("Instrucciones publicadas", "Published instructions")
                  : copy("Perfil visual publicado", "Published visual profile")}
              <select
                className="native-select block w-full"
                value={JSON.stringify(o.config[key] ?? {})}
                onChange={(e) =>
                  onChange({
                    ...o,
                    config: { ...o.config, [key]: JSON.parse(e.target.value) },
                  })
                }
              >
                <option value="{}">—</option>
                {native?.[group]?.map((v) => (
                  <option
                    key={`${v.id}@${v.version}`}
                    value={JSON.stringify(v)}
                  >
                    {v.id} · {v.version} · {v.sha256.slice(0, 8)}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      )}
      {o.instrument === "liftoff" && (
        <LiftoffBinding
          config={o.config}
          schema={bindings.liftoff_schema}
          onChange={(config) => onChange({ ...o, config })}
        />
      )}
      {o.instrument === "suas" && (
        <MissionBinding
          config={o.config}
          scenarios={bindings.suas}
          onChange={(config) => onChange({ ...o, config })}
        />
      )}
      {o.instrument === "physiology" && (
        <div className="flex flex-wrap gap-3">
          {Object.entries(
            (o.config.settings ?? {}) as Record<string, number>,
          ).map(([key, value]) => (
            <label key={key}>
              {key}
              <select
                className="native-select block"
                value={value}
                onChange={(e) =>
                  onChange({
                    ...o,
                    config: {
                      ...o.config,
                      settings: {
                        ...(o.config.settings as object),
                        [key]: Number(e.target.value),
                      },
                    },
                  })
                }
              >
                {(key === "acc_sample_rate_hz"
                  ? [25, 50, 100, 200]
                  : key === "acc_range_g"
                    ? [2, 4, 8]
                    : [value]
                ).map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
          ))}
        </div>
      )}
      {(o.instrument === "pvt" || o.instrument === "screen") && (
        <p className="break-all text-xs">
          {String(o.config.binding_id ?? "")} · {String(o.config.sha256 ?? "")}
        </p>
      )}
      {o.instrument === "questionnaire" && (
        <p className="text-sm">
          {copy(
            "Escalas inmediatamente después de la tarea nativa; se permite el H10 acompañante. Solo la tarea destinataria exacta puede ser un requisito previo. No se admiten cuestionarios diferidos.",
            "Ratings immediately after the native task; accompanying H10 is allowed. Only the exact target task may be a prerequisite. Delayed questionnaires are unsupported.",
          )}
        </p>
      )}
      {o.instrument === "questionnaire" && (
        <label>
          {copy("Tarea destinataria exacta", "Exact target task")}
          <select
            className="native-select block"
            value={o.target_key ?? ""}
            onChange={(e) =>
              onChange({ ...o, target_key: e.target.value || null })
            }
          >
            <option value="">—</option>
            {study.occasions
              .filter((v) => v.instrument === "openmatb")
              .map((v) => (
                <option key={v.key}>{v.key}</option>
              ))}
          </select>
        </label>
      )}
      {o.instrument === "physiology" && (
        <>
          <label>
            {copy("Grupo de recolección simultánea", "Co-acquisition group")}
            <input
              className="native-input block"
              value={o.collection_group ?? ""}
              onChange={(e) =>
                onChange({ ...o, collection_group: e.target.value || null })
              }
            />
          </label>
          <label>
            {copy("Acompaña a", "Accompanies")}
            <select
              className="native-select block"
              value={o.accompanying_key ?? ""}
              onChange={(e) =>
                onChange({ ...o, accompanying_key: e.target.value || null })
              }
            >
              <option value="">
                {copy("Medición independiente", "Standalone measurement")}
              </option>
              {study.occasions
                .filter(
                  (v) =>
                    v.order < o.order &&
                    ["openmatb", "liftoff", "suas"].includes(v.instrument),
                )
                .map((v) => (
                  <option key={v.key}>{v.key}</option>
                ))}
            </select>
          </label>
        </>
      )}
      {["openmatb", "liftoff", "suas"].includes(o.instrument) && (
        <label>
          {copy("Grupo de recolección simultánea", "Co-acquisition group")}
          <input
            className="native-input block"
            value={o.collection_group ?? ""}
            onChange={(e) =>
              onChange({ ...o, collection_group: e.target.value || null })
            }
          />
        </label>
      )}
      <div>
        <p>
          {copy(
            "Prerrequisitos (el intento exacto se selecciona antes de iniciar)",
            "Prerequisites (select the exact attempt before starting)",
          )}
        </p>
        {study.occasions
          .filter(
            (v) => v.visit_ordinal === o.visit_ordinal && v.order < o.order,
          )
          .map((v) => (
            <label className="mr-4" key={v.key}>
              <input
                type="checkbox"
                checked={o.prerequisite_keys.includes(v.key)}
                onChange={(e) =>
                  onChange({
                    ...o,
                    prerequisite_keys: e.target.checked
                      ? [...o.prerequisite_keys, v.key]
                      : o.prerequisite_keys.filter((k) => k !== v.key),
                  })
                }
              />
              {v.key}
            </label>
          ))}
      </div>
      <Button variant="outline" onClick={onRemove}>
        {copy("Quitar ocasión", "Remove occasion")}
      </Button>
    </fieldset>
  );
}
