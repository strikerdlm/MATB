import type { OpenMatbVisualProfileDocument } from "@/types/openmatb";

function Tank({
  x,
  y,
  color,
  fluid,
  border,
  text,
  label,
}: {
  x: number;
  y: number;
  color: string;
  fluid: string;
  border: string;
  text: string;
  label: string;
}) {
  return <g>
    <rect x={x} y={y} width="40" height="74" rx="2" fill={color} stroke={border} />
    <rect x={x + 2} y={y + 35} width="36" height="37" fill={fluid} opacity="0.9" />
    <text x={x + 20} y={y - 5} textAnchor="middle" fontSize="9" fill={text}>{label}</text>
  </g>;
}

export function ResourceManagementPreview({ profile }: { profile: OpenMatbVisualProfileDocument }) {
  const theme = profile.modules.resource_management;
  return (
    <svg viewBox="0 0 560 285" role="img" aria-label="RESMAN appearance preview" className="fac-preview-svg">
      <rect width="560" height="285" rx="5" fill={theme.panel} />
      <g fill="none" stroke={theme.pipe_off} strokeWidth={profile.metrics.line_width + 1} strokeLinejoin="round">
        <path d="M 67 90 V 132 H 202 V 90" />
        <path d="M 357 90 V 132 H 492 V 90" />
        <path d="M 87 204 H 202 V 164 H 280" />
        <path d="M 473 204 H 357 V 164 H 280" />
        <path d="M 202 90 V 50 H 357 V 90" />
      </g>
      <g fill={theme.pump_on} stroke={theme.pipe_on}>
        {[[134, 132], [280, 50], [425, 132], [280, 164]].map(([x, y], index) => (
          <circle key={index} cx={x} cy={y} r="11" fill={index === 1 ? theme.pump_failure : theme.pump_on} />
        ))}
      </g>
      <Tank x={47} y={15} color={theme.tank_1} fluid={theme.fluid} border={profile.palette.border} text={profile.palette.text} label="Tank 1" />
      <Tank x={473} y={15} color={theme.tank_2} fluid={theme.fluid} border={profile.palette.border} text={profile.palette.text} label="Tank 2" />
      <Tank x={67} y={184} color={theme.tank_3} fluid={theme.fluid} border={profile.palette.border} text={profile.palette.text} label="Tank 3" />
      <Tank x={453} y={184} color={theme.tank_4} fluid={theme.fluid} border={profile.palette.border} text={profile.palette.text} label="Tank 4" />
      <Tank x={182} y={184} color={theme.tank_5} fluid={theme.fluid} border={profile.palette.border} text={profile.palette.text} label="Tank 5" />
      <Tank x={338} y={184} color={theme.tank_6} fluid={theme.fluid} border={profile.palette.border} text={profile.palette.text} label="Tank 6" />
      <g transform="translate(244 91)">
        <rect width="72" height="87" rx="3" fill={profile.palette.instrument_background} stroke={profile.palette.border} />
        <text x="36" y="17" textAnchor="middle" fontSize="10" fontWeight="600" fill={profile.palette.text}>FLOW RATES</text>
        {["1   9500", "2   8600", "3   7200", "4   6800"].map((value, index) => <text key={value} x="13" y={35 + index * 12} fontSize="9" fill={profile.palette.text}>{value}</text>)}
      </g>
    </svg>
  );
}
