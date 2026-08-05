import { useStatus } from '../../StatusContext.jsx'
import Icon from '../ui/Icon.jsx'

// led + estado + puerto. al apretarlo abre la hoja de conexion, el
// indicador y el control son el mismo objeto, asi no hay que buscar
// "donde me conecto" en otra pantalla.
//
// el verde de esta app existe solo aca. si lo usaramos tambien en toggles
// y botones dejaria de significar "la maquina responde", que es lo unico
// que tiene que decir
export default function ConnectionPill({ onOpen }) {
  const { status, connected, commLost } = useStatus()

  const tone = !connected ? 'off' : commLost ? 'bad' : status?.simulating ? 'sim' : 'ok'
  const state = !connected ? 'Desconectado' : commLost ? 'Sin respuesta' : 'Conectado'
  const meta = !connected
    ? 'conectar'
    : `${status?.simulating ? 'SIM' : 'REAL'}${status?.port ? ` · ${status.port}` : ''}`

  return (
    <button type="button" className="conn" onClick={onOpen}>
      <span className={`conn__led conn__led--${tone}`} />
      <span className="conn__text">
        <span className="conn__state">{state}</span>
        <span className="conn__meta tnum">{meta}</span>
      </span>
      {commLost && <Icon name="wifi-slash" size={14} className="conn__alarm" />}
    </button>
  )
}
