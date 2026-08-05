import { AnimatePresence, motion } from 'motion/react'
import { spring, useMotionPrefs } from '../../motion.js'
import Icon from './Icon.jsx'

// 4 jerarquias nomas: primary, secondary de default, ghost sin caja, danger
//
// los nombres viejos se siguen aceptando para no reescribir ~40 sitios
const ALIASES = {
  filled: 'primary',
  tinted: 'secondary',
  gray: 'secondary',
  plain: 'ghost',
  destructive: 'danger',
  'destructive-tinted': 'danger-soft',
}

// el color va por css, la geometria por spring, un tap interrumpido se
// reanuda desde donde quedo el anterior
export default function Button({
  variant = 'secondary',
  size = 'md',
  icon,
  iconSize,
  iconOnly = false,
  block = false,
  loading = false,
  className = '',
  children,
  type = 'button',
  disabled,
  ...rest
}) {
  const { t, tap } = useMotionPrefs()
  const kind = ALIASES[variant] ?? variant

  const classes = [
    'btn',
    `btn--${kind}`,
    `btn--${size}`,
    block ? 'btn--block' : '',
    iconOnly ? 'btn--icon-only' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  const isDisabled = disabled || loading

  return (
    <motion.button
      type={type}
      className={classes}
      disabled={isDisabled}
      // disabled no deberia responder al gesto ni parecer que acepto el click
      whileTap={isDisabled ? undefined : tap()}
      transition={t(spring.snappy)}
      {...rest}
    >
      {/* el spinner reemplaza al icono en el mismo lugar, el boton no cambia de ancho */}
      <AnimatePresence initial={false} mode="wait">
        {loading ? (
          <motion.span
            key="spinner"
            className="btn__spinner"
            aria-hidden="true"
            initial={{ opacity: 0, scale: 0.6 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.6 }}
            transition={t(spring.snappy)}
          />
        ) : (
          icon && (
            <motion.span
              key="icon"
              className="btn__icon"
              initial={{ opacity: 0, scale: 0.6 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.6 }}
              transition={t(spring.snappy)}
            >
              <Icon name={icon} size={iconSize ?? (size === 'lg' ? 16 : 14)} />
            </motion.span>
          )
        )}
      </AnimatePresence>
      {children}
    </motion.button>
  )
}
