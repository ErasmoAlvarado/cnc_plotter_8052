import { useStatus } from '../../StatusContext.jsx'
import Icon from '../ui/Icon.jsx'

// LED + estado + puerto. Pulsarlo abre la hoja de conexion: el indicador y su
// control son el mismo objeto, asi no hay que buscar "donde se conecta" en otra
// pantalla.
//
// El verde de esta app existe solo aca. Si tine tambien toggles y botones deja
// de querer decir "la maquina responde", que es justo lo unico que tiene que
// decir.
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
