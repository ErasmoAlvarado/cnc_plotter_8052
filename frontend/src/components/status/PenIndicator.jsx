import { useStatus } from '../../StatusContext.jsx'
import Icon from '../ui/Icon.jsx'
import Tooltip from '../ui/Tooltip.jsx'

// estado de la pluma como icono, no texto suelto. penDown viene derivado
// de Z_POS en el contexto (z_steps >= pen_steps, mismo criterio del
// firmware), sigue siendo correcto mientras la maquina dibuja porque el
// polling se apaga en un job pero el websocket sigue mandando la Z
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
