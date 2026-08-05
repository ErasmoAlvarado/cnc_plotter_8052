import { motion } from 'motion/react'
import { spring, useMotionPrefs } from '../../motion.js'
import Icon from './Icon.jsx'

// boton de solo icono sin caja, transparente hasta que lo tocas
//
// label es obligatorio en la practica, sin texto necesita nombre accesible
//
// baseClass existe porque el stepper y los avisos ya tenian su propia piel en css
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
