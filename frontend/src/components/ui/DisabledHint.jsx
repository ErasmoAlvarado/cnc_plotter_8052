import Icon from './Icon.jsx'

// Envuelve un grupo de controles que no se pueden usar ahora mismo.
//
// La regla de diseno es "un estado invalido no deberia poder pedirse": en vez
// de dejar que el usuario pulse y reciba un 400 del backend, el bloque se
// atenua y se explica el motivo en una linea. Los hijos igual reciben su
// prop `disabled` — esto es la capa visual, no la de seguridad.
export default function DisabledHint({ reason, children, className = '' }) {
  return (
    <div className={`disabled-wrap ${reason ? 'disabled-wrap--off' : ''} ${className}`.trim()}>
      {/* inert (React 19) saca el bloque del orden de tabulacion ademas de
          apagarlo visualmente: sin esto el teclado seguia entrando en botones
          que el raton ya no podia pulsar. */}
      <div className="disabled-wrap__body" aria-disabled={reason ? 'true' : undefined} inert={!!reason}>
        {children}
      </div>
      {reason && (
        <p className="disabled-wrap__reason">
          <Icon name="info-circle" size={16} />
          {reason}
        </p>
      )}
    </div>
  )
}
