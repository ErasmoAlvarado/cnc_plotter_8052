import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { api } from '../../api'
import { useStatus } from '../../StatusContext.jsx'
import { collapse, fadeUp, spring, useMotionPrefs } from '../../motion.js'
import { blockedJogs, jogVector } from '../../coords.js'
import Button from '../../components/ui/Button.jsx'
import DisabledHint from '../../components/ui/DisabledHint.jsx'
import JogPad from '../../components/dashboard/JogPad.jsx'
import ZControl from '../../components/dashboard/ZControl.jsx'
import StepChips from '../../components/dashboard/StepChips.jsx'
import SecondaryActions from '../../components/dashboard/SecondaryActions.jsx'

// mover los ejes, va en el rail y no atras de un menu
//
// cuando no se puede operar el bloque se atenua y explica por que, el
// motivo lo da reason del contexto para que ninguna vista olvide comm_lost
export default function MotionPanel({ onConnect }) {
  const { canOperate, connected, runAction, reason, status, busy } = useStatus()
  const [step, setStep] = useState(1)
  const { t } = useMotionPrefs()

  const blockReason = reason('move')
  const stepValid = Number(step) > 0 && Number(step) <= 500
  const disabled = !canOperate || !stepValid || busy

  const invert = useMemo(
    () => ({ invertX: !!status?.invert_x, invertY: !!status?.invert_y }),
    [status?.invert_x, status?.invert_y],
  )

  // que flechas sacarian el cabezal del area, con la posicion real del backend
  const blocked = useMemo(
    () =>
      blockedJogs({
        position: status?.position,
        stepMm: Number(step),
        area: { max_x_mm: status?.max_x_mm, max_y_mm: status?.max_y_mm },
        invert,
        enforce: status?.enforce_soft_limits !== false,
      }),
    [status?.position, status?.max_x_mm, status?.max_y_mm,
     status?.enforce_soft_limits, step, invert],
  )

  // coords.jogVector traduce la direccion que ve el usuario a eje y sentido
  function handleJog(direction) {
    const v = jogVector(direction, invert)
    if (!v) return
    runAction(() => api.jog(v.axis, v.direction, Number(step))).catch(() => {})
  }

  // Z va en pasos por su propio endpoint, no en mm como el dpad
  function handleZ(steps) {
    runAction(() => api.penJog(steps)).catch(() => {})
  }

  return (
    <>
      <DisabledHint reason={blockReason}>
        <StepChips value={step} onChange={setStep} />
        <AnimatePresence>
          {!stepValid && (
            <motion.p className="hint field__error" {...fadeUp} transition={t(spring.smooth)}>
              El paso tiene que ser mayor que 0 y como mucho 500 mm.
            </motion.p>
          )}
        </AnimatePresence>

        <div className="jog-row">
          <JogPad onJog={handleJog} disabled={disabled} step={step} blocked={blocked} />
          <ZControl onJog={handleZ} disabled={disabled} />
        </div>

        <AnimatePresence>
          {blocked.size > 0 && stepValid && (
            <motion.p className="hint field__warn" {...fadeUp} transition={t(spring.smooth)}>
              Las flechas apagadas se saldrían del área de {status?.max_x_mm ?? '—'} ×{' '}
              {status?.max_y_mm ?? '—'} mm. Probá con un paso más corto.
            </motion.p>
          )}
        </AnimatePresence>

        <SecondaryActions disabled={!canOperate || busy} />
      </DisabledHint>

      {/* se recoge en vez de desaparecer de golpe, sin animar la altura pega un salto */}
      <AnimatePresence initial={false}>
        {!connected && (
          <motion.div {...collapse} transition={t(spring.smooth)} style={{ overflow: 'hidden' }}>
            <Button variant="primary" size="md" block icon="plug" onClick={onConnect}>
              Conectar la máquina
            </Button>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
