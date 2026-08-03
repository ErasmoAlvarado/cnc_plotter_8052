import { useId } from 'react'
import { motion } from 'motion/react'
import { spring, useMotionPrefs } from '../../motion.js'
import Icon from './Icon.jsx'

// Control segmentado. Se usa para los chips de paso del jog, el selector de
// patron y las secciones de la hoja avanzada.
//
// El fondo de la opcion activa no se pinta con `[aria-selected='true']`: es un
// elemento propio que VIAJA de una opcion a otra con `layoutId`. Cambiar de
// seccion deja de ser un parpadeo en dos sitios a la vez —uno que se apaga y
// otro que se enciende— y pasa a ser una sola cosa que se mueve, que es lo que
// el usuario cree que esta haciendo cuando pulsa.
//
// El layoutId tiene que ser unico por instancia: hay varios de estos en
// pantalla al mismo tiempo (los pasos del jog y las secciones de la hoja) y si
// compartieran identificador el fondo saltaria de un control al otro.
//
// options: [{ value, label, icon?, disabled? }]
export default function SegmentedControl({
  options,
  value,
  onChange,
  size = 'md',
  label,
  className = '',
}) {
  const layoutId = useId()
  const { t } = useMotionPrefs()

  return (
    <div
      className={`segmented ${size === 'lg' ? 'segmented--lg' : ''} ${className}`.trim()}
      role="tablist"
      aria-label={label}
    >
      {options.map((opt) => {
        const selected = opt.value === value
        return (
          <button
            key={opt.value}
            type="button"
            role="tab"
            aria-selected={selected}
            disabled={opt.disabled}
            className="segmented__option"
            onClick={() => onChange(opt.value)}
          >
            {/* Detras del contenido, no envolviendolo: asi el texto no hereda
                la animacion de layout y no se estira mientras el fondo viaja. */}
            {selected && (
              <motion.span
                layoutId={layoutId}
                className="segmented__thumb"
                transition={t(spring.snappy)}
              />
            )}
            <span className="segmented__content">
              {opt.icon && <Icon name={opt.icon} size={16} />}
              {opt.label}
            </span>
          </button>
        )
      })}
    </div>
  )
}
