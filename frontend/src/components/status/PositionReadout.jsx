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

// telemetria de la maquina. es el dato que el usuario compara mentalmente
// contra lo que ve en la mesa, y el que mas cambia por segundo (el
// websocket manda cada ~200ms).
//
// a proposito sin suavizado: el cabezal del canvas se interpola porque ahi
// importa que se vea continuo, pero un numero de posicion tiene que
// mostrar la ultima posicion real, no una intermedia inventada. se
// estabiliza con cifras tabulares (.tnum), no retrasando el valor
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
