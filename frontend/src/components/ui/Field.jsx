import { useId } from 'react'

// Campo con etiqueta y texto de ayuda. Los <input>/<select> sueltos de la v1 se
// centralizan aca para que la etiqueta siempre este asociada (htmlFor/id) y el
// mensaje de validacion viva junto al campo, no en el banner global.
export default function Field({ label, hint, error, children, id, className = '' }) {
  const autoId = useId()
  const fieldId = id ?? autoId

  return (
    <div className={`field ${className}`.trim()}>
      {label && (
        <label className="field__label" htmlFor={fieldId}>
          {label}
        </label>
      )}
      {typeof children === 'function' ? children(fieldId) : children}
      {error ? (
        <p className="hint field__error">{error}</p>
      ) : (
        hint && <p className="hint">{hint}</p>
      )}
    </div>
  )
}
