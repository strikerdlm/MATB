import type { OpenMatbVisualProfileDocument } from "@/types/openmatb";

export function CommunicationsPreview({ profile }: { profile: OpenMatbVisualProfileDocument }) {
  const theme = profile.modules.communications;
  return (
    <div className="grid grid-cols-[1fr_7rem] gap-3 rounded-md p-3 text-xs" style={{ background: theme.panel }} aria-label="COMM appearance preview">
      <div className="grid grid-cols-2 gap-x-4 gap-y-2">
        {["COM 1", "COM 2", "NAV 1", "NAV 2"].map((label, index) => (
          <div key={label} className="flex items-center gap-2" style={{ color: profile.palette.text }}>
            <span className="h-3 w-3 rounded-full border-2" style={{ borderColor: index === 0 ? theme.active : theme.inactive, background: index === 0 ? theme.active : theme.panel }} />
            {label}
          </div>
        ))}
      </div>
      <div className="rounded border px-2 py-2 text-center font-mono" style={{ background: theme.display_background, borderColor: theme.display_border, color: profile.palette.text }}>
        0.500
      </div>
    </div>
  );
}
