import type { OpenMatbVisualProfileDocument } from "@/types/openmatb";

export function TrackingPreview({ profile }: { profile: OpenMatbVisualProfileDocument }) {
  const theme = profile.modules.tracking;
  return (
    <svg viewBox="0 0 320 300" role="img" aria-label="TRACK appearance preview" className="fac-preview-svg">
      <rect x="8" y="8" width="304" height="284" rx="5" fill={theme.panel} stroke={profile.palette.border} />
      {theme.show_grid && [84, 160, 236].flatMap((position) => [
        <line key={`gx-${position}`} x1={position} y1="16" x2={position} y2="284" stroke={theme.grid} strokeWidth="1" />,
        <line key={`gy-${position}`} x1="16" y1={position} x2="304" y2={position} stroke={theme.grid} strokeWidth="1" />,
      ])}
      <line x1="16" y1="150" x2="304" y2="150" stroke={theme.axis} strokeWidth={profile.metrics.line_width} />
      <line x1="160" y1="16" x2="160" y2="284" stroke={theme.axis} strokeWidth={profile.metrics.line_width} />
      {Array.from({ length: 17 }, (_, index) => 32 + index * 16).map((position, index) => (
        <g key={position} stroke={theme.axis} strokeWidth="1">
          <line x1={position} y1={index % 4 === 0 ? 143 : 146} x2={position} y2={index % 4 === 0 ? 157 : 154} />
          <line x1={index % 4 === 0 ? 153 : 156} y1={position} x2={index % 4 === 0 ? 167 : 164} y2={position} />
        </g>
      ))}
      <circle cx="160" cy="150" r="29" fill={theme.target_fill} stroke={theme.target} strokeWidth={profile.metrics.line_width} />
      <circle cx="181" cy="136" r="8" fill={theme.cursor} stroke={theme.cursor} />
      <line x1="169" y1="136" x2="193" y2="136" stroke={theme.cursor} strokeWidth="2" />
      <line x1="181" y1="124" x2="181" y2="148" stroke={theme.cursor} strokeWidth="2" />
    </svg>
  );
}
