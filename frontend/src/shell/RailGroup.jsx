import { useCallback, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { collapse, spring, stagger, useMotionPrefs } from '../motion.js'
import Icon from '../components/ui/Icon.jsx'

// Grupo colapsable del rail.
//
// Sustituye a las tarjetas del dashboard. Un grupo no es una superficie propia
// flotando sobre otra: es una seccion del rail separada por una linea. Cuatro
// tarjetas de cristal apiladas eran cuatro bordes, cuatro sombras y cuatro
// halos para decir algo que dice mejor una linea de 1px.
//
// Que este colapsado o no se recuerda entre sesiones: quien no usa los patrones
// de prueba no tiene por que verlos cada vez que abre la app.
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
    // Las variantes las orquesta Rail: aca solo se declara como se ve cada
    // estado. El `transition` del grupo no toca al del cuerpo colapsable de
    // abajo, que trae el suyo propio y por eso no hereda nada.
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
