import { useStatus } from '../../StatusContext.jsx'
import Icon from '../ui/Icon.jsx'
import Tooltip from '../ui/Tooltip.jsx'

// Estado de la pluma como icono, no como texto suelto. penDown viene derivado
// de Z_POS en el contexto (z_steps >= pen_steps, el mismo criterio que usa el
// firmware), asi que tambien es fiel mientras la maquina dibuja — el polling se
// apaga durante un trabajo, pero el WebSocket sigue trayendo la Z.
export default function PenIndicator() {
  const { penDown, status } = useStatus()
  const z = status?.position?.z_steps

  return (
    <Tooltip label={`Z = ${z ?? '—'} pasos`} side="bottom">
      <div className={`pen-state ${penDown ? 'pen-state--down' : ''}`.trim()}>
        <Icon name={penDown ? 'pen-down' : 'pen-up'} size={15} />
        <span className="pen-state__label">{penDown ? 'ABAJO' : 'ARRIBA'}</span>
      </div>
    </Tooltip>
  )
}
