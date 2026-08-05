import { useCallback, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { collapse, spring, stagger, useMotionPrefs } from '../motion.js'
import Icon from '../components/ui/Icon.jsx'

// grupo colapsable, una seccion separada por una linea, no una tarjeta flotante
//
// si esta colapsado se guarda entre sesiones, no todos usan los patrones de prueba
function usePersistedOpen(id, fallback) {
  const key = `cnc.rail.${id}`
  const [open, setOpen] = useState(() => {
    const stored = localStorage.getItem(key)
    return stored === null ? fallback : stored === '1'
  })
  const toggle = useCallback(() => {
    setOpen((prev) => {
      localStorage.setItem(key, prev ? '0' : '1')
      return !prev
    })
  }, [key])
  return [open, toggle]
}

export default function RailGroup({ id, title, aside, defaultOpen = true, children }) {
  const [open, toggle] = usePersistedOpen(id, defaultOpen)
  const { t } = useMotionPrefs()

  return (
    // las variantes las maneja Rail, el cuerpo colapsable trae su propio transition
    <motion.section
      className="rail-group"
      variants={stagger.child}
      transition={t(spring.smooth)}
    >
      <button type="button" className="rail-group__head" onClick={toggle} aria-expanded={open}>
        <Icon
          name="chevron-right"
          size={12}
          className={`rail-group__caret ${open ? 'rail-group__caret--open' : ''}`.trim()}
        />
        <span className="rail-group__title micro">{title}</span>
        {aside && <span className="rail-group__aside">{aside}</span>}
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div className="rail-group__clip" {...collapse} transition={t(spring.smooth)}>
            <div className="rail-group__body">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.section>
  )
}
