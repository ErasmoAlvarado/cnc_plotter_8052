import { useId } from 'react'

// campo con etiqueta y texto de ayuda. los input/select sueltos de la v1
// quedan centralizados aca para que la etiqueta siempre este asociada
// (htmlFor/id) y el error viva junto al campo, no en el banner global
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
