import { motion } from 'motion/react'
import { spring, useMotionPrefs } from '../../motion.js'
import Icon from '../ui/Icon.jsx'

// dpad de X/Y, se exporta suelto porque el wizard de calibracion lo reusa
//
// los botones se identifican por lo que ve el usuario, no por eje y signo
//
// sin auto-repeat al mantener apretado, cada jog es una llamada serie bloqueante
const BOTONES = {
  up: { icon: 'chevron-up', label: 'Mover hacia arriba' },
  left: { icon: 'chevron-left', label: 'Mover hacia la izquierda' },
  right: { icon: 'chevron-right', label: 'Mover hacia la derecha' },
  down: { icon: 'chevron-down', label: 'Mover hacia abajo' },
}

export default function JogPad({ onJog, disabled, step, unit = 'mm', blocked }) {
  const { t, tap } = useMotionPrefs()

  // cuadrados grandes sin texto, el mismo % se nota menos que en el resto de la app
  const press = tap(0.92)

  const btn = (dir) => {
    const { icon, label } = BOTONES[dir]
    // bloqueada = ese movimiento saca el cabezal del area, se apaga en vez de tirar un 400
    const fuera = !disabled && !!blocked?.has(dir)
    return (
      <motion.button
        type="button"
        className={`jog-btn ${fuera ? 'jog-btn--blocked' : ''}`.trim()}
        disabled={disabled || fuera}
        aria-label={fuera ? `${label} (se saldría del área)` : label}
        whileTap={press}
        transition={t(spring.snappy)}
        onClick={() => onJog(dir)}
      >
        <Icon name={icon} size={20} />
      </motion.button>
    )
  }

  return (
    <div className="jog-pad">
      <span />
      {btn('up')}
      <span />

      {btn('left')}
      <div className="jog-center">
        <span className="jog-center__value">{step}</span>
        <span className="jog-center__unit">{unit}</span>
      </div>
      {btn('right')}

      <span />
      {btn('down')}
      <span />
    </div>
  )
}
