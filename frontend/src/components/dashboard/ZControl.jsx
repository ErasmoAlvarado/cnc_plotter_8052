import { motion } from 'motion/react'
import { spring, useMotionPrefs } from '../../motion.js'
import Icon from '../ui/Icon.jsx'

// eje Z en su propia columna, afuera de la cruz X/Y.
//
// habla en pasos y no en mm, por eso no comparte el chip de X/Y. antes si
// lo compartia: con el chip de 10mm y steps_per_mm_z=100 se pedian 1000
// pasos, el backend recortaba en silencio al maximo de 255 y la etiqueta
// seguia diciendo "un paso". el recorrido util de este eje son unas
// decenas de pasos en total, el mm no es la unidad que sirve aca.
//
// el backend limita cada jog a 255 pasos y avisa si Z_POS se sale de 0-255
const PASOS = [
  { steps: 5, icon: 'chevron-up', label: 'Subir la pluma 5 pasos' },
  { steps: 1, icon: 'plus', label: 'Subir la pluma 1 paso' },
  { steps: -1, icon: 'minus', label: 'Bajar la pluma 1 paso' },
  { steps: -5, icon: 'chevron-down', label: 'Bajar la pluma 5 pasos' },
]

export default function ZControl({ onJog, disabled }) {
  const { t, tap } = useMotionPrefs()
  const press = tap(0.92)

  return (
    <div className="jog-z">
      <span className="jog-z__label">Z</span>
      {PASOS.map(({ steps, icon, label }) => (
        <motion.button
          key={steps}
          type="button"
          className="jog-btn jog-btn--sm"
          disabled={disabled}
          aria-label={label}
          title={label}
          whileTap={press}
          transition={t(spring.snappy)}
          onClick={() => onJog(steps)}
        >
          <Icon name={icon} size={15} />
        </motion.button>
      ))}
      <span className="jog-z__unit">pasos</span>
    </div>
  )
}
