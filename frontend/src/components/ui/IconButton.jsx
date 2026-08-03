import { motion } from 'motion/react'
import { spring, useMotionPrefs } from '../../motion.js'
import Icon from './Icon.jsx'

// Boton de solo icono sin caja: el tema, los ajustes, el hamburguesa del rail,
// la X de un aviso, el -/+ de un stepper.
//
// No es un `Button` con `iconOnly`. Ese tiene fondo, borde y una de las cuatro
// jerarquias; este es transparente hasta que lo tocas con el raton y no compite
// con nada. La diferencia es la clase `.icon-btn`, que ya existia en ui.css —
// lo que faltaba era el componente, porque escribirlo a mano en cada sitio
// (TopBar, Banner, Stepper) los dejaba a todos sin respuesta a la pulsacion.
//
// `label` es obligatorio en la practica: un boton sin texto necesita nombre
// accesible o el lector de pantalla anuncia "boton" y nada mas.
//
// `baseClass` existe porque el stepper y la X de los avisos ya tenian su propia
// piel en CSS y no hay motivo para reescribirla: lo que comparten con el resto
// no es el aspecto, es la respuesta a la pulsacion.
export default function IconButton({
  name,
  size = 16,
  label,
  baseClass = 'icon-btn',
  className = '',
  type = 'button',
  disabled,
  children,
  ...rest
}) {
  const { t, tap } = useMotionPrefs()

  return (
    <motion.button
      type={type}
      className={`${baseClass} ${className}`.trim()}
      disabled={disabled}
      aria-label={label}
      whileTap={disabled ? undefined : tap()}
      transition={t(spring.snappy)}
      {...rest}
    >
      {name ? <Icon name={name} size={size} /> : children}
    </motion.button>
  )
}
