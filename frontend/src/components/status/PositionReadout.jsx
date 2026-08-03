import { useStatus } from '../../StatusContext.jsx'
import PenIndicator from './PenIndicator.jsx'

function Axis({ name, value, unit }) {
  return (
    <div className="axis">
      <span className="axis__name">{name}</span>
      <span className="axis__value tnum">{value}</span>
      {unit && <span className="axis__unit">{unit}</span>}
    </div>
  )
}

// Telemetria de la maquina. Es el dato que el usuario compara mentalmente
// contra lo que ve en la mesa, y el que mas veces por segundo cambia (el
// WebSocket emite cada ~200 ms).
//
// Deliberadamente SIN suavizado: el cabezal del lienzo se interpola porque ahi
// lo que importa es que el movimiento se lea continuo, pero un numero que
// muestra una posicion tiene que decir la ultima posicion reportada y no una
// intermedia inventada. La lectura se estabiliza con cifras tabulares (.tnum),
// no retrasando el valor.
export default function PositionReadout() {
  const { status } = useStatus()
  const pos = status?.position

  return (
    <div className="readout">
      <Axis name="X" value={Number(pos?.x_mm ?? 0).toFixed(2)} />
      <Axis name="Y" value={Number(pos?.y_mm ?? 0).toFixed(2)} unit="mm" />
      <PenIndicator />
    </div>
  )
}
