import { useId } from 'react'
import { motion } from 'motion/react'
import { spring, useMotionPrefs } from '../../motion.js'
import Icon from './Icon.jsx'

// el fondo de la opcion activa VIAJA con layoutId, no es un parpadeo en 2 lugares
//
// el layoutId tiene que ser unico por instancia, si no el fondo salta entre controles
//
// options: value, label, icon opcional, disabled opcional
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
            {/* va detras del contenido, asi el texto no hereda la animacion y no se estira */}
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
