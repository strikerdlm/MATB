import type { OpenMatbVisualProfileDocument } from "@/types/openmatb";
import { useAppLocale } from "@/lib/i18n";

export function WorkloadPreview({ profile }: { profile: OpenMatbVisualProfileDocument }) {
  const { copy } = useAppLocale();
  const theme = profile.modules.workload;
  return (
    <div className="rounded-md px-4 py-3" style={{ background: theme.panel }} aria-label={copy("Vista previa de carga subjetiva", "Subjective workload appearance preview")}>
      <div className="mb-2 flex justify-between text-[10px]" style={{ color: profile.palette.muted_text }}><span>{copy("Muy baja", "Very low")}</span><span>{copy("Muy alta", "Very high")}</span></div>
      <div className="relative h-8">
        <div className="absolute inset-x-0 top-2 h-px" style={{ background: theme.scale }} />
        {Array.from({ length: 11 }, (_, index) => <span key={index} className="absolute top-0 h-4 w-px" style={{ left: `${index * 10}%`, background: theme.scale }} />)}
        <span className="absolute top-0 grid h-5 w-5 -translate-x-1/2 place-items-center rounded-full text-[9px] font-semibold text-white" style={{ left: "50%", background: theme.marker }}>5</span>
        <div className="absolute inset-x-0 top-5 flex justify-between text-[9px]" style={{ color: profile.palette.text }}>{Array.from({ length: 11 }, (_, index) => <span key={index}>{index}</span>)}</div>
      </div>
    </div>
  );
}
