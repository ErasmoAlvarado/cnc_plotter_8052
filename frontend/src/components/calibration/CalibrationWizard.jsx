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

// Variantes dinamicas: reciben la direccion por `custom`. Tienen que ser
// variantes con nombre — motion solo pasa `custom` a las funciones que encuentra
// dentro de `variants`, no a un `initial`/`exit` que sea una funcion suelta.
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

// Flujo guiado de calibracion.
//
// El orden importa y por eso "Siguiente" solo se habilita cuando el paso
// anterior se completo: medir el juego con una escala mal calibrada da un
// numero que no significa nada. Se puede volver atras libremente — lo que no se
// puede es saltar hacia adelante.
export default function CalibrationWizard({ open, onClose, initialStep = 0 }) {
  const { canOperate, connected } = useStatus()
  const [index, setIndex] = useState(initialStep)
  const [completed, setCompleted] = useState({})
  const [mode, setMode] = useState('wizard')
  const { t } = useMotionPrefs()

  // Hacia donde va el paso. Un asistente que siempre entra por el mismo lado no
  // distingue avanzar de volver atras, y "Atras" es justo el boton que necesita
  // decirle al usuario que esta deshaciendo. +1 adelante, -1 atras.
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
      // Tambien se reinicia lo completado. Sin esto, cerrar y volver a abrir
      // mostraba los pasos en verde y dejaba saltar directo a "Terminar": el
      // asistente afirmaba que la maquina estaba calibrada en esta visita
      // cuando lo unico cierto es que se calibro en algun momento de la sesion.
      setCompleted({})
    }
  }, [open, initialStep])

  const Current = STEPS[index].Component
  const isLast = index === STEPS.length - 1
  const canAdvance = !!completed[STEPS[index].id]

  // Se puede volver a cualquier paso anterior, y avanzar solo hasta el primero
  // sin hacer. Antes se miraba unicamente el paso inmediatamente anterior, asi
  // que con "Juego" hecho se podia saltar a "Pluma" sin haber pasado nunca por
  // "Escala" — justo el orden que el asistente existe para imponer, porque
  // medir el juego con una escala mal calibrada da un numero sin significado.
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
      {/* El asistente sirve para estrenar la maquina; los ajustes rapidos, para
          el dia a dia. Obligar a recorrer los tres pasos —moviendo los ejes y
          gastando papel— solo para subir dos pasos la pluma era la queja
          principal de la calibracion. */}
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
