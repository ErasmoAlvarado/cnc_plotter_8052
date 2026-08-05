import IconButton from './IconButton.jsx'

// numero con -/+ a los lados. se usa en vez de un input number pelado para
// todo lo que se ajusta "a tanteo" (profundidad de pluma, backlash,
// velocidades), asi el usuario no tiene que escribir, solo empujar.
//
// el input sigue aceptando escritura directa porque para calibrar hace
// falta poder teclear una medida exacta
export default function Stepper({
  value,
  onChange,
  min = 0,
  max = 255,
  step = 1,
  suffix,
  disabled,
  id,
  'aria-label': ariaLabel,
}) {
  const num = Number(value)
  const valid = Number.isFinite(num)

  const clamp = (n) => Math.min(max, Math.max(min, n))
  // redondeamos a 4 decimales para que 0.1 + 0.2 no termine escribiendo
  // 0.30000000000000004 justo en el campo que el usuario esta mirando
  const round = (n) => Math.round(n * 10000) / 10000
  const bump = (delta) => onChange(String(round(clamp((valid ? num : min) + delta))))

  return (
    <div className="stepper">
      <IconButton
        baseClass="stepper__btn"
        name="minus"
        size={20}
        label="Disminuir"
        disabled={disabled || (valid && num <= min)}
        onClick={() => bump(-step)}
      />
      <input
        id={id}
        className="stepper__input"
        type="number"
        inputMode="decimal"
        value={value}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        aria-label={ariaLabel}
        onChange={(e) => onChange(e.target.value)}
      />
      <IconButton
        baseClass="stepper__btn"
        name="plus"
        size={20}
        label="Aumentar"
        disabled={disabled || (valid && num >= max)}
        onClick={() => bump(step)}
      />
      {suffix && <span className="stepper__suffix">{suffix}</span>}
    </div>
  )
}
