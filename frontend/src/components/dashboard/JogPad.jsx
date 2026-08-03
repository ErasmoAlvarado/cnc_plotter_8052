import { motion } from 'motion/react'
import { spring, useMotionPrefs } from '../../motion.js'
import Icon from '../ui/Icon.jsx'

// D-pad de X/Y. Se exporta suelto porque el asistente de calibracion lo
// reutiliza tal cual: mover la maquina se hace en un solo sitio de la app, no
// en tres copias que se van desincronizando.
//
// Los botones se identifican por lo que el usuario VE ('up', 'left'), no por
// el eje y el signo. Antes 'arriba' era literalmente Y+1, y por eso invertir
// la perspectiva de la maquina dejaba el mando funcionando al reves: quien
// traduce direccion -> eje es coords.jogVector(), y lo hace en un solo sitio
// para el D-pad, el lienzo y el G-code.
//
// Sin auto-repeticion al mantener pulsado, y es deliberado: cada jog es una
// llamada serie bloqueante, y encolar repeticiones separa la posicion que
// muestra la pantalla de la real.
const BOTONES = {
  up: { icon: 'chevron-up', label: 'Mover hacia arriba' },
  left: { icon: 'chevron-left', label: 'Mover hacia la izquierda' },
  right: { icon: 'chevron-right', label: 'Mover hacia la derecha' },
  down: { icon: 'chevron-down', label: 'Mover hacia abajo' },
}

export default function JogPad({ onJog, disabled, step, unit = 'mm', blocked }) {
  const { t, tap } = useMotionPrefs()

  // El rebote de la pulsacion va con resorte y no con una duracion fija: si el
  // usuario pulsa dos veces seguidas, la segunda sale desde donde estaba la
  // primera en lugar de cortarla en seco.
  //
  // 0.92 y no el 0.97 del resto de la app: estos son cuadrados grandes sin
  // texto, y el mismo porcentaje sobre mas superficie se ve menos.
  const press = tap(0.92)

  const btn = (dir) => {
    const { icon, label } = BOTONES[dir]
    // Bloqueada = ese movimiento sacaria el cabezal del area util. Se apaga
    // en vez de dejar pulsar y recibir un 400: un estado invalido no deberia
    // poder pedirse. El motivo lo escribe MotionPanel debajo del mando —- un
    // tooltip no serviria, porque un boton deshabilitado no emite eventos de
    // puntero y nunca llegaria a abrirse.
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
