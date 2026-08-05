// switch estilo ios, por debajo sigue siendo un input checkbox real para
// no perder el foco de teclado ni el anuncio del lector de pantalla
export default function Toggle({ checked, onChange, disabled, label, id }) {
  return (
    <label className={`toggle ${disabled ? 'toggle--off' : ''}`.trim()} htmlFor={id}>
      <input
        id={id}
        type="checkbox"
        checked={!!checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="toggle__track">
        <span className="toggle__knob" />
      </span>
      {label && <span>{label}</span>}
    </label>
  )
}
