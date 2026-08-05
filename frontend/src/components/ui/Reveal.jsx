import { useRef } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { fadeUp, spring, useMotionPrefs } from '../../motion.js'

// junta el patron repetido `{dato && <div>...}` y de paso gana animacion de salida
//
// children es funcion, no nodo: JSX evalua children antes de pasarlos, explota si son null
//
// `last` guarda el ultimo valor no vacio para que la caja tenga algo que pintar al salir
export default function Reveal({ when, className, children }) {
  const { t } = useMotionPrefs()
  const last = useRef(null)

  if (when) last.current = when
  const data = when || last.current

  return (
    <AnimatePresence initial={false}>
      {when && data && (
        <motion.div className={className} {...fadeUp} transition={t(spring.smooth)}>
          {typeof children === 'function' ? children(data) : children}
        </motion.div>
      )}
    </AnimatePresence>
  )
}
