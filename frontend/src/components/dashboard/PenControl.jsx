import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { api } from '../../api'
import { useStatus } from '../../StatusContext.jsx'
import { collapse, spring, useMotionPrefs } from '../../motion.js'
import Button from '../ui/Button.jsx'

const FINE_STEPS = [-10, -1, 1, 10]

// Subir/Bajar, mas un ajuste fino que se despliega en el sitio.
//
// Subir y bajar son ABSOLUTOS en el firmware (van a Z_POS=0 y Z_POS=PEN_N), asi
// que repetirlos siempre es seguro: no hace falta protegerlos contra el doble
// clic ni recordar en que estado estaba la pluma.
export default function PenControl({ disabled }) {
  const { penDown, runAction } = useStatus()
  const [fine, setFine] = useState(false)
  const { t } = useMotionPrefs()

  const pen = (action) => runAction(() => api.pen(action)).catch(() => {})

  return (
    <div className="pen-control">
      <div className="pen-control__main">
        {/* El resaltado marca en que estado ESTA la pluma, no cual es la accion
            recomendada — por eso es el tono tenue del acento y no un boton
            primario lleno. */}
        <Button
          variant="secondary"
          className={penDown ? '' : 'btn--active'}
          aria-pressed={!penDown}
          icon="pen-up"
          disabled={disabled}
          onClick={() => pen('up')}
        >
          Subir
        </Button>
        <Button
          variant="secondary"
          className={penDown ? 'btn--active' : ''}
          aria-pressed={penDown}
          icon="pen-down"
          disabled={disabled}
          onClick={() => pen('down')}
        >
          Bajar
        </Button>
      </div>

      <Button
        variant="ghost"
        size="sm"
        icon={fine ? 'chevron-up' : 'chevron-down'}
        onClick={() => setFine((v) => !v)}
      >
        Ajuste fino
      </Button>

      <AnimatePresence initial={false}>
        {fine && (
          <motion.div {...collapse} transition={t(spring.smooth)} style={{ overflow: 'hidden' }}>
            <div className="pen-fine">
              <span className="pen-fine__label">
                Mueve el eje Z en pasos sueltos, sin cambiar el estado de la pluma.
              </span>
              {FINE_STEPS.map((s) => (
                <Button
                  key={s}
                  variant="secondary"
                  size="sm"
                  disabled={disabled}
                  onClick={() => runAction(() => api.penJog(s)).catch(() => {})}
                >
                  {s > 0 ? `+${s}` : s}
                </Button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
