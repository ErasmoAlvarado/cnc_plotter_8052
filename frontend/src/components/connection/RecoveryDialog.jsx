import { useRef } from 'react'
import { api } from '../../api'
import { useStatus } from '../../StatusContext.jsx'
import Sheet from '../ui/Sheet.jsx'
import Button from '../ui/Button.jsx'
import PlotCanvas from '../canvas/PlotCanvas.jsx'

// el backend puede ofrecer la ultima posicion guardada en disco, el minimapa
// muestra donde quedo la pluma para elegir sin adivinar
//
// queda montado siempre y se cierra con `open`, si lo desmontas radix no
// llega a animar la salida
//
// por eso guarda los ultimos datos, durante el cierre `recovery` ya es null
export default function RecoveryDialog({ recovery, onClose }) {
  const { status, runAction, refreshStatus } = useStatus()
  const last = useRef(null)

  if (recovery) last.current = recovery
  const data = recovery ?? last.current

  if (!data) return null

  const spmX = status?.steps_per_mm?.x || 1
  const spmY = status?.steps_per_mm?.y || 1
  const xMm = data.pos_x / spmX
  const yMm = data.pos_y / spmY

  async function decide(action) {
    await runAction(() => api.recoverPosition(action)).catch(() => {})
    await refreshStatus()
    onClose()
  }

  return (
    <Sheet
      open={!!recovery}
      onClose={onClose}
      title="Se encontró una posición anterior"
      footer={
        <>
          <Button variant="gray" size="lg" block onClick={() => decide('reset')}>
            Empezar de cero
          </Button>
          <Button variant="filled" size="lg" block onClick={() => decide('accept')}>
            Continuar desde ahí
          </Button>
        </>
      }
    >
      <p className="hint">
        La sesión anterior terminó con la pluma en este punto, hace {data.age_human}. Si no
        moviste la máquina a mano desde entonces, podés seguir desde ahí; si la moviste, conviene
        empezar de cero y volver a fijar el origen.
      </p>

      <div className="recovery-map">
        <PlotCanvas
          workArea={{ max_x_mm: status?.max_x_mm ?? 40, max_y_mm: status?.max_y_mm ?? 40 }}
          invertX={!!status?.invert_x}
          invertY={!!status?.invert_y}
          head={{ x: xMm, y: yMm, penDown: data.pen_down }}
          penSteps={status?.pen_steps ?? 100}
          pulsing
          className="recovery-map__canvas"
        />
      </div>

      <div className="recovery-facts">
        <div className="fact">
          <p className="fact__label">Posición X</p>
          <p className="fact__value">{xMm.toFixed(2)} mm</p>
        </div>
        <div className="fact">
          <p className="fact__label">Posición Y</p>
          <p className="fact__value">{yMm.toFixed(2)} mm</p>
        </div>
        <div className="fact">
          <p className="fact__label">Pluma</p>
          <p className="fact__value">{data.pen_down ? 'Abajo' : 'Arriba'}</p>
        </div>
      </div>

      {/* Z nunca sale del archivo, se relee del microcontrolador al conectar */}
      <p className="hint">
        La altura de la pluma no se recupera del archivo — se vuelve a leer de la máquina al
        conectar, así que siempre es la real.
      </p>
    </Sheet>
  )
}
