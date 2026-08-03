import { AnimatePresence, motion } from 'motion/react'
import { spring, useMotionPrefs } from '../../motion.js'
import Icon from './Icon.jsx'

// Cuatro jerarquias, no seis:
//   primary   -> la accion de la vista (Ejecutar, Conectar). Una sola visible.
//   secondary -> la piel por defecto de casi todo (Home, Simular, Guardar)
//   ghost     -> terciaria, sin caja: "ver mas", "cambiar archivo"
//   danger    -> Detener, apagar Z. Rojo, y nunca la unica opcion de un dialogo.
//
// Los nombres viejos siguen aceptandose para no tener que reescribir los ~40
// sitios que los pasan; el mapa deja claro cual era cual.
const ALIASES = {
  filled: 'primary',
  tinted: 'secondary',
  gray: 'secondary',
  plain: 'ghost',
  destructive: 'danger',
  'destructive-tinted': 'danger-soft',
}

// El reparto entre CSS y fisica: el color va por CSS (`transition` en ui.css) y
// la geometria por resorte. Un cambio de color no se interrumpe a mitad —
// termina en el color que toca y ya— pero una pulsacion si: quien pulsa dos
// veces rapido tiene que ver la segunda salir de donde estaba la primera.
//
// Por eso `.btn:active { transform: translateY(1px) }` ya no existe en ui.css:
// motion escribe `transform` en el estilo inline y ganaba siempre.
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
      // Un boton deshabilitado no responde al gesto. Sin esto motion sigue
      // hundiendolo al pulsar y el control miente: parece que acepto el clic.
      whileTap={isDisabled ? undefined : tap()}
      transition={t(spring.snappy)}
      {...rest}
    >
      {/* El spinner sustituye al icono en el sitio, sin corte: el boton no
          cambia de ancho y la accion no parece haberse reiniciado. */}
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
