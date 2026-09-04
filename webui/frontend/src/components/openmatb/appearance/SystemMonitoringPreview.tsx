import type { OpenMatbVisualProfileDocument } from "@/types/openmatb";

export function SystemMonitoringPreview({ profile }: { profile: OpenMatbVisualProfileDocument }) {
  const theme = profile.modules.system_monitoring;
  const lamps = [theme.lamp_1, theme.lamp_2, theme.lamp_3, theme.lamp_4];
  return (
    <svg viewBox="0 0 440 105" role="img" aria-label="SYSMON appearance preview" className="fac-preview-svg">
      <rect width="440" height="105" rx="5" fill={theme.panel} />
      {lamps.map((color, index) => (
        <g key={index} transform={`translate(${48 + index * 76} 25)`}>
          {theme.lamp_shape === "circle" ? (
            <circle cx="0" cy="0" r="12" fill={color} stroke={theme.lamp_border} />
          ) : (
            <rect x="-17" y="-10" width="34" height="20" fill={color} stroke={theme.lamp_border} />
          )}
          <text x="0" y="28" textAnchor="middle" fill={profile.palette.text} fontSize="10">L{index + 1}</text>
        </g>
      ))}
      {[0, 1, 2, 3].map((index) => (
        <g key={index} transform={`translate(${54 + index * 77} 69)`} stroke={theme.scale}>
          <line x1="-22" y1="0" x2="22" y2="0" />
          {[-18, -9, 0, 9, 18].map((x) => <line key={x} x1={x} y1="-4" x2={x} y2="4" />)}
          <path d="M 2 -3 L 10 -11 L 12 -1 Z" fill={theme.pointer} stroke="none" />
        </g>
      ))}
    </svg>
  );
}
