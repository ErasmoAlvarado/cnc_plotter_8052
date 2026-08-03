import { useState } from 'react'
import { api } from '../../api'
import { useStatus } from '../../StatusContext.jsx'
import Button from '../ui/Button.jsx'
import Banner from '../ui/Banner.jsx'
import PenTuner from '../pen/PenTuner.jsx'
import PenHolderSection from '../advanced/PenHolderSection.jsx'

// Paso 3: pluma y eje Z, en el orden que pide el backend
// (invertir si hace falta -> ajustar altura y presion -> ciclo de prueba).
//
// El ajuste en si lo hace PenTuner, que es el mismo control que se abre desde
// el rail: ajustar la pluma es exactamente lo mismo dentro y fuera del
// asistente, y tenerlo dos veces escrito garantizaba que uno de los dos se
// quedara atras.
export default function StepPen({ onDone, done }) {
  const { canOperate, busy, runAction, setZEnergized } = useStatus()
  const [cycle, setCycle] = useState(null)

  async function testCycle() {
    try {
      const result = await runAction(api.penTestCycle)
      setCycle(result)
      // Fijar el cero y mover el eje vuelve a energizarlo: el aviso naranja de
      // "Z sin energizar" deja de tener sentido. Solo en el camino de exito —
      // antes se marcaba tambien cuando la peticion fallaba, y se borraba el
      // aviso mientras el eje seguia suelto de verdad, que es justo lo que el
      // aviso existe para impedir.
      setZEnergized(true)
      onDone()
    } catch {
      /* banner */
    }
  }

  return (
    <div className="wizard-body">
      <p className="hint">
        Aquí se define qué altura es «pluma arriba» y cuánto tiene que bajar para dibujar. Es lo que
        decide si el trazo sale marcado, flojo o directamente rayado.
      </p>

      <ol className="steps-list">
        <li className="steps-list__item">
          <div className="steps-list__body">
            <span>¿«Bajar» levanta la pluma en vez de bajarla? Invertí el porta-pluma primero.</span>
            <PenHolderSection compact />
          </div>
        </li>

        <li className="steps-list__item">
          <div className="steps-list__body">
            <span>Ajustá la altura de tránsito y la presión sobre el papel.</span>
            <PenTuner embedded />
          </div>
        </li>

        <li className="steps-list__item">
          <div className="steps-list__body">
            <span>Comprobalo: la pluma baja, espera un momento y vuelve a subir.</span>
            <div>
              <Button
                variant="filled"
                icon="play"
                disabled={!canOperate || busy}
                loading={busy}
                onClick={testCycle}
              >
                Ciclo de prueba
              </Button>
            </div>
            {cycle && (
              <Banner
                tone={cycle.steps_lost === true ? 'warn' : cycle.steps_lost === false ? 'success' : 'info'}
              >
                {cycle.steps_lost === true
                  ? 'La pluma no volvió exactamente a su sitio: se perdieron pasos. Bajá la velocidad del eje Z o reducí la presión.'
                  : cycle.steps_lost === false
                    ? 'La pluma volvió exactamente a cero. El eje Z está bien.'
                    : 'La máquina no contestó al comprobar la altura.'}
              </Banner>
            )}
          </div>
        </li>
      </ol>

      {done && <Banner tone="success">Pluma calibrada. Ya podés dibujar.</Banner>}
    </div>
  )
}
