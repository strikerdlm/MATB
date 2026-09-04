import type { ReactNode } from "react";
import { useAppLocale } from "@/lib/i18n";
import { cvdFilterValues, type CvdType } from "./cvd";

export function CvdPreview({
  type,
  severity,
  onTypeChange,
  onSeverityChange,
  children,
}: {
  type: CvdType;
  severity: number;
  onTypeChange: (type: CvdType) => void;
  onSeverityChange: (severity: number) => void;
  children: ReactNode;
}) {
  const { copy } = useAppLocale();
  const filterId = "fac-cvd-preview-filter";
  return (
    <>
      <div className="fac-cvd-controls" aria-label={copy("Vista previa de deficiencia de visión cromática solo en el navegador", "Browser-only color vision deficiency preview")}>
        <label>
          <span>{copy("Vista CVD", "CVD preview")}</span>
          <select value={type} onChange={(event) => onTypeChange(event.target.value as CvdType)}>
            <option value="normal">Normal</option>
            <option value="protanomaly">{copy("Protanomalía", "Protanomaly")}</option>
            <option value="deuteranomaly">{copy("Deuteranomalía", "Deuteranomaly")}</option>
            <option value="tritanomaly">{copy("Tritanomalía", "Tritanomaly")}</option>
          </select>
        </label>
        <label className="fac-range-control">
          <span>{copy("Severidad", "Severity")} <output>{severity}%</output></span>
          <input
            aria-label={copy("Severidad de vista CVD", "CVD preview severity")}
            disabled={type === "normal"}
            max="100"
            min="0"
            step="10"
            type="range"
            value={severity}
            onChange={(event) => onSeverityChange(Number(event.target.value))}
          />
        </label>
        <p>{copy("Solo vista previa: nunca se escribe en el perfil del participante.", "Preview only — never written to the participant profile.")}</p>
      </div>
      <svg aria-hidden="true" className="fac-filter-definitions">
        <filter id={filterId} colorInterpolationFilters="sRGB">
          <feColorMatrix type="matrix" values={cvdFilterValues(type, severity)} />
        </filter>
      </svg>
      <div className="fac-cvd-stage" style={type === "normal" ? undefined : { filter: `url(#${filterId})` }}>
        {children}
      </div>
    </>
  );
}
