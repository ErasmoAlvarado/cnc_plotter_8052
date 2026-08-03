import { useMemo, useState } from 'react'
import { api } from '../../api'
import { useStatus } from '../../StatusContext.jsx'
import { useSyncedValue } from '../../hooks/useSyncedForm.js'
import { jogVector } from '../../coords.js'
import Button from '../ui/Button.jsx'
import Stepper from '../ui/Stepper.jsx'
import Banner from '../ui/Banner.jsx'
import Reveal from '../ui/Reveal.jsx'
import JogPad from '../dashboard/JogPad.jsx'

// Paso 2: juego mecanico (backlash).
//
// Reutiliza el D-pad del dashboard, pero cableado a /api/calibrate/backlash/move
// y NO a /api/jog. La diferencia es el punto entero del paso: el jog normal ya
// aplica compensacion de backlash, asi que medir con el daria siempre cero.
// Este endpoint manda los pasos crudos, sin compensar.
export default function StepBacklash({ onDone, done }) {
  const { canOperate, busy, runAction, refreshConfig, refreshStatus, status } = useStatus()
  const [rawSteps, setRawSteps] = useState('200')
  const [moveResult, setMoveResult] = useState(null)
  // Sembrados desde la maquina en cuanto llega el estado. Antes se leian una
  // sola vez en el montaje: si el componente se montaba antes del primer
  // /api/status —que es lo normal— los campos se quedaban en 0 y "Guardar"
  // borraba la compensacion que ya estaba medida.
  const [blX, setBlX] = useSyncedValue(status?.backlash?.x, 0)
  const [blY, setBlY] = useSyncedValue(status?.backlash?.y, 0)

  const stepsNum = Number(rawSteps)
  const stepsValid = stepsNum > 0 && stepsNum <= 10000
  const valuesValid =
    Number(blX) >= 0 && Number(blX) <= 255 && Number(blY) >= 0 && Number(blY) <= 255

  const invert = useMemo(
    () => ({ invertX: !!status?.invert_x, invertY: !!status?.invert_y }),
    [status?.invert_x, status?.invert_y],
  )

  // El D-pad habla en direcciones que ve el usuario. Aqui se traducen igual
  // que en el panel de movimiento —misma funcion— pero el destino es otro:
  // /api/calibrate/backlash/move manda PASOS CRUDOS, sin compensacion. Es el
  // punto entero de este paso: el jog normal ya compensa el juego, asi que
  // medir con el daria siempre cero.
  async function move(direction) {
    const v = jogVector(direction, invert)
    if (!v || v.axis === 'z') return
    try {
      setMoveResult(
        await runAction(() => api.calibrateBacklashMove(v.axis, v.direction * stepsNum)),
      )
    } catch {
      /* banner */
    }
  }

  async function apply() {
    try {
      await runAction(() => api.calibrateBacklashApply(Number(blX), Number(blY)))
      await refreshConfig()
      await refreshStatus()
      onDone()
    } catch {
      /* banner */
    }
  }

  return (
    <div className="wizard-body">
      <p className="hint">
        El juego es lo que la correa o el husillo tardan en «agarrar» al cambiar de sentido: el
        motor gira pero el carro todavía no se mueve. Se mide yendo y volviendo, y se compensa.
      </p>

      <ol className="steps-list">
        <li className="steps-list__item">
          <div className="steps-list__body">
            <span>
              Marcá con lápiz dónde está el carro. Movelo en un sentido y después la misma cantidad
              en el contrario, con estos botones (mueven pasos crudos, sin compensación).
            </span>
            <Stepper
              value={rawSteps}
              onChange={setRawSteps}
              min={10}
              max={10000}
              step={50}
              suffix="pasos"
              aria-label="Pasos crudos por pulsación"
            />
            <JogPad
              onJog={move}
              disabled={!canOperate || !stepsValid || busy}
              step={rawSteps}
              unit="pasos"
            />
            <Reveal when={moveResult} className="result-box">
              {(r) => (
                <>
                  <div className="result-box__row">
                    <span className="result-box__label">Movido</span>
                    <span>{r.moved} pasos</span>
                  </div>
                  <div className="result-box__row">
                    <span className="result-box__label">Posición</span>
                    <span>
                      X {r.pos_x} · Y {r.pos_y}
                    </span>
                  </div>
                </>
              )}
            </Reveal>
          </div>
        </li>

        <li className="steps-list__item">
          <div className="steps-list__body">
            <span>
              Medí cuántos pasos se pierden en el cambio de sentido y anotalos para cada eje. Si no
              notás juego, dejá 0.
            </span>
            <div className="row">
              <Stepper value={blX} onChange={setBlX} min={0} max={255} aria-label="Juego en X" suffix="X" />
              <Stepper value={blY} onChange={setBlY} min={0} max={255} aria-label="Juego en Y" suffix="Y" />
            </div>
            <div>
              <Button variant="filled" disabled={!canOperate || !valuesValid || busy} onClick={apply}>
                Guardar compensación
              </Button>
            </div>
          </div>
        </li>
      </ol>

      {done && <Banner tone="success">Compensación guardada. La máquina volvió al origen.</Banner>}
    </div>
  )
}
