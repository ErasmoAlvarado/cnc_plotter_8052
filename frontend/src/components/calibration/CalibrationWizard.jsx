import { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { useStatus } from '../../StatusContext.jsx'
import { spring, useMotionPrefs } from '../../motion.js'
import Sheet from '../ui/Sheet.jsx'
import Button from '../ui/Button.jsx'
import Banner from '../ui/Banner.jsx'
import Icon from '../ui/Icon.jsx'
import SegmentedControl from '../ui/SegmentedControl.jsx'
import StepSpm from './StepSpm.jsx'
import StepBacklash from './StepBacklash.jsx'
import StepPen from './StepPen.jsx'
import QuickCalibration from './QuickCalibration.jsx'

// motion solo pasa `custom` a funciones dentro de `variants`
const SLIDE = {
  enter: (d) => ({ opacity: 0, x: 12 * d }),
  center: { opacity: 1, x: 0 },
  exit: (d) => ({ opacity: 0, x: -12 * d }),
}

const STEPS = [
  { id: 'spm', label: 'Escala', title: 'Pasos por milímetro', Component: StepSpm },
  { id: 'backlash', label: 'Juego', title: 'Juego mecánico', Component: StepBacklash },
  { id: 'pen', label: 'Pluma', title: 'Altura de la pluma', Component: StepPen },
]

const MODES = [
  { value: 'wizard', label: 'Asistente' },
  { value: 'quick', label: 'Ajustes rápidos' },
]

// el orden importa: medir el juego con la escala mal calibrada no sirve
export default function CalibrationWizard({ open, onClose, initialStep = 0 }) {
  const { canOperate, connected } = useStatus()
  const [index, setIndex] = useState(initialStep)
  const [completed, setCompleted] = useState({})
  const [mode, setMode] = useState('wizard')
  const { t } = useMotionPrefs()

  // hacia donde va el paso, adelante o atras
  const dir = useRef(1)
  const goTo = useCallback((next) => {
    setIndex((prev) => {
      dir.current = next >= prev ? 1 : -1
      return next
    })
  }, [])

  useEffect(() => {
    if (open) {
      dir.current = 1
      setIndex(initialStep)
      // reinicia lo completado tambien, si no cerrar y abrir de nuevo
      // mostraba todo en verde y dejaba saltar directo a Terminar como si
      // ya estuviera calibrado en esta visita
      setCompleted({})
    }
  }, [open, initialStep])

  const Current = STEPS[index].Component
  const isLast = index === STEPS.length - 1
  const canAdvance = !!completed[STEPS[index].id]

  // se puede volver a cualquier paso anterior, avanzar solo hasta el
  // primero sin hacer. antes miraba nomas el paso inmediato anterior y con
  // "juego" hecho se podia saltar a "pluma" sin pasar por "escala", que es
  // justo el orden que el wizard tiene que forzar
  const reachable = (i) =>
    i <= index || STEPS.slice(0, i).every((s) => completed[s.id])

  const guiado = mode === 'wizard'

  return (
    <Sheet
      open={open}
      onClose={onClose}
      title={guiado ? `Calibración · ${STEPS[index].title}` : 'Calibración · Ajustes rápidos'}
      footer={
        guiado ? (
          <>
            <Button
              variant="gray"
              size="lg"
              disabled={index === 0}
              icon="chevron-left"
              onClick={() => goTo(Math.max(0, index - 1))}
            >
              Atrás
            </Button>
            {isLast ? (
              <Button variant="filled" size="lg" block onClick={onClose}>
                Terminar
              </Button>
            ) : (
              <Button
                variant="filled"
                size="lg"
                block
                disabled={!canAdvance}
                onClick={() => goTo(index + 1)}
              >
                {canAdvance ? 'Siguiente paso' : 'Completá este paso'}
              </Button>
            )}
          </>
        ) : (
          <Button variant="filled" size="lg" block onClick={onClose}>
            Cerrar
          </Button>
        )
      }
    >
      {/* el wizard es para la primera vez, los ajustes rapidos para el dia
          a dia. obligar a pasar los 3 pasos (moviendo ejes y gastando
          papel) solo para subir 2 pasos la pluma era la queja mas comun */}
      <SegmentedControl
        label="Modo de calibración"
        options={MODES}
        value={mode}
        onChange={setMode}
      />

      {!connected && (
        <Banner tone="warn" title="La máquina no está conectada">
          Calibrar requiere mover los ejes de verdad. Conectá la máquina para continuar.
        </Banner>
      )}
      {connected && !canOperate && (
        <Banner tone="warn">
          Esperá a que termine el trabajo en curso antes de calibrar.
        </Banner>
      )}

      {!guiado ? (
        <QuickCalibration />
      ) : (
        <>
          <nav className="wizard-steps" aria-label="Pasos de la calibración">
            {STEPS.map((s, i) => {
              const state = completed[s.id] ? 'done' : i === index ? 'current' : ''
              return (
                <button
                  key={s.id}
                  type="button"
                  className={`wizard-step ${state ? `wizard-step--${state}` : ''}`.trim()}
                  disabled={!reachable(i)}
                  onClick={() => goTo(i)}
                  aria-current={i === index ? 'step' : undefined}
                >
                  <span className="wizard-step__dot">
                    {completed[s.id] ? <Icon name="check-circle" size={18} /> : i + 1}
                  </span>
                  <span className="wizard-step__label">{s.label}</span>
                </button>
              )
            })}
          </nav>

          <AnimatePresence mode="wait" initial={false} custom={dir.current}>
            <motion.div
              key={STEPS[index].id}
              custom={dir.current}
              variants={SLIDE}
              initial="enter"
              animate="center"
              exit="exit"
              transition={t(spring.gentle)}
            >
              <Current
                done={!!completed[STEPS[index].id]}
                onDone={() => setCompleted((prev) => ({ ...prev, [STEPS[index].id]: true }))}
              />
            </motion.div>
          </AnimatePresence>
        </>
      )}
    </Sheet>
  )
}
