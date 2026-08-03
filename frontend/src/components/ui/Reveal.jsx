import { useRef } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { fadeUp, spring, useMotionPrefs } from '../../motion.js'

// Aparicion de un resultado: la caja que sale despues de dibujar la linea de
// calibracion, las estadisticas del enlace, el aviso de un ping.
//
// Todos son lo mismo — un dato que no existia y ahora si — y todos se escribian
// igual: `{dato && <div className="result-box">…</div>}`. Envueltos aca, ademas
// de dejar de repetir el AnimatePresence, ganan la salida: antes desaparecian
// de golpe porque React ya habia desmontado el nodo.
//
// El hijo es una funcion y no un nodo por una razon concreta: JSX evalua a sus
// hijos ANTES de pasarlos, asi que `<Reveal when={r}>{r.total}</Reveal>` reventaria
// con `r` a null. Recibiendo el dato por parametro, el contenido solo se
// construye cuando hay algo que construir. Field.jsx hace lo mismo con el id.
//
// `last` guarda el ultimo valor no vacio para que la caja siga teniendo que
// dibujar mientras se va: durante la salida `when` ya es null.
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
