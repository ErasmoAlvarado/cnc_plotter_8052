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

// Mover los ejes. Es lo primero que necesita cualquiera que se acerca a la
// maquina, asi que vive en el rail y no detras de un menu.
//
// Cuando no se puede operar, el bloque no desaparece: se atenua y explica por
// que. El motivo lo da reason() del contexto, no este componente — asi ninguna
// vista se olvida de comprobar comm_lost.
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

  // Que flechas sacarian el cabezal del area. Se calcula con la posicion real
  // reportada por el backend, no con la interpolada del lienzo.
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

  // El D-pad habla en direcciones que ve el usuario; coords.jogVector las
  // traduce a eje y sentido segun como este montada la maquina.
  function handleJog(direction) {
    const v = jogVector(direction, invert)
    if (!v) return
    runAction(() => api.jog(v.axis, v.direction, Number(step))).catch(() => {})
  }

  // Z va en PASOS y por su propio endpoint. Antes compartia el valor en mm del
  // D-pad: con el chip de 10 mm y steps_per_mm_z=100 el backend recortaba en
  // silencio a 255 pasos, mientras la etiqueta decia "un paso".
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

      {/* Al conectar, este boton no desaparece de golpe: se recoge. Es el unico
          sitio del rail donde algo se va del todo, y sin la altura animada el
          resto del panel pega un salto hacia arriba. */}
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
