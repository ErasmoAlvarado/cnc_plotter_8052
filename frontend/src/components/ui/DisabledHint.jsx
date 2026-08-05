import Icon from './Icon.jsx'

// envuelve un grupo de controles que no se pueden usar ahora. la idea es
// que un estado invalido no deberia poder pedirse -- en vez de dejar
// apretar y recibir un 400 del backend, se atenua el bloque y se explica
// el motivo en una linea. los hijos igual reciben su prop disabled, esto
// es la capa visual nomas, no la de seguridad
export default function DisabledHint({ reason, children, className = '' }) {
  return (
    <div className={`disabled-wrap ${reason ? 'disabled-wrap--off' : ''} ${className}`.trim()}>
      {/* inert (React 19) saca el bloque del orden de tabulacion ademas de
          apagarlo visualmente, sin esto el teclado seguia entrando a botones
          que con el mouse ya no se podian tocar */}
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
