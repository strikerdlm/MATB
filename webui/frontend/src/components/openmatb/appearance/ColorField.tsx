const HEX_COLOR = /^#[0-9A-F]{6}$/i;

export function ColorField({
  id,
  label,
  value,
  disabled = false,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  const valid = HEX_COLOR.test(value);
  return (
    <div className="fac-color-field">
      <label htmlFor={`${id}-text`}>{label}</label>
      <span className="fac-color-control">
        <input
          aria-label={`${label} color picker`}
          className="fac-color-swatch"
          disabled={disabled}
          id={`${id}-picker`}
          type="color"
          value={valid ? value : "#000000"}
          onChange={(event) => onChange(event.target.value.toUpperCase())}
        />
        <input
          aria-invalid={!valid}
          className="fac-hex-input"
          disabled={disabled}
          id={`${id}-text`}
          maxLength={7}
          pattern="#[0-9A-Fa-f]{6}"
          spellCheck={false}
          value={value}
          onChange={(event) => onChange(event.target.value.toUpperCase())}
        />
      </span>
    </div>
  );
}

export const isHexColor = (value: string) => HEX_COLOR.test(value);
