import { useEffect } from 'react'
import { AnimatePresence, motion, useSpring, useTransform } from 'motion/react'
import { api } from '../../api'
import { useStatus } from '../../StatusContext.jsx'
import { readoutSpring, spring, useMotionPrefs } from '../../motion.js'
import Button from '../ui/Button.jsx'

function formatElapsed(seconds) {
  if (!Number.isFinite(seconds)) return null
  const s = Math.floor(seconds % 60)
  const m = Math.floor(seconds / 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

// Barra + Detener. El boton esta SIEMPRE montado (deshabilitado si no hay
// trabajo) en vez de aparecer y desaparecer: quien necesita pararlo de urgencia
// no deberia tener que buscar donde salio el boton esta vez.
//
// La barra si se suaviza con un resorte, al reves que la lectura de posicion:
// el progreso llega en saltos de 0.3% cada 200 ms y sin interpolar avanza a
// tirones. Aca no hay riesgo de enganar a nadie — el numero exacto esta escrito
// al lado.
export default function JobProgressBar() {
  const { status, jobActive, runAction } = useStatus()
  const { t, reduce } = useMotionPrefs()

  const job = status?.job
  const percent = Math.round((job?.progress ?? 0) * 100)
  const elapsed = formatElapsed(job?.elapsed)

  const value = useSpring(0, readoutSpring)
  const width = useTransform(value, (v) => `${v}%`)
  // El numero sale del MISMO MotionValue que el relleno. Tenerlos en dos
  // fuentes distintas —la barra interpolada y el porcentaje en texto plano—
  // hacia que se contradijeran a la vista: la barra iba por el 40% mientras el
  // numero de al lado ya decia 43%.
  const label = useTransform(value, (v) => Math.round(v))

  useEffect(() => {
    if (reduce) value.jump(percent)
    else value.set(percent)
  }, [percent, reduce, value])

  return (
    <div className="job">
      <AnimatePresence mode="wait" initial={false}>
        {jobActive ? (
          <motion.div
            key="running"
            className="job__running"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={t(spring.smooth)}
          >
            <div
              className="job__bar"
              role="progressbar"
              aria-valuenow={percent}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Progreso del trabajo"
            >
              <motion.div className="job__fill" style={{ width }} />
            </div>
            <span className="job__label tnum">
              <motion.span>{label}</motion.span>% · {job?.lines_processed ?? 0}/
              {job?.total_lines ?? 0}
              {elapsed ? ` · ${elapsed}` : ''}
            </span>
          </motion.div>
        ) : (
          <motion.span
            key="idle"
            className="job__idle"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={t(spring.smooth)}
          >
            En reposo
          </motion.span>
        )}
      </AnimatePresence>

      <Button
        variant={jobActive ? 'danger' : 'secondary'}
        size="sm"
        icon="stop-circle"
        disabled={!jobActive}
        onClick={() => runAction(api.stop).catch(() => {})}
      >
        Detener
      </Button>
    </div>
  )
}
