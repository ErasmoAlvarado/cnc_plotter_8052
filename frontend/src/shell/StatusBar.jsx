import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { useStatus } from '../StatusContext.jsx'
import { spring, useMotionPrefs } from '../motion.js'
import Icon from '../components/ui/Icon.jsx'
import Banner from '../components/ui/Banner.jsx'
import Button from '../components/ui/Button.jsx'

// Franja de pie: los parametros con los que la maquina esta trabajando ahora
// mismo, y los avisos.
//
// Antes los avisos eran tarjetas flotantes colgando de la cabecera, que empujaban
// el contenido hacia abajo cada vez que aparecia uno. Aca ocupan una linea fija
// que no mueve nada, y se despliegan al pulsarlas. El unico que no se puede
// ignorar — el eje Z sin energizar, con la pluma cayendose por gravedad — abre
// el panel por su cuenta.
export default function StatusBar({ onFixZ }) {
  const { status, banner, setBanner, commLost, connected, zEnergized } = useStatus()
  const { t } = useMotionPrefs()
  const [manuallyOpen, setManuallyOpen] = useState(false)

  const warnings = status?.warnings ?? []
  const zLoose = connected && !zEnergized

  const notices = commLost || zLoose || warnings.length > 0 || !!banner
  const severity = commLost || banner?.type === 'error' ? 'error' : zLoose || warnings.length ? 'warn' : 'info'

  // El aviso de Z manda: mientras esta, el panel se queda abierto sin que nadie
  // lo pida.
  const open = notices && (manuallyOpen || zLoose || commLost)

  const summary = commLost
    ? 'Sin respuesta del microcontrolador'
    : zLoose
      ? 'El eje Z está sin energizar'
      : warnings.length
        ? warnings[0]
        : banner?.text

  const spm = status?.steps_per_mm
  const backlash = status?.backlash

  return (
    <>
      <AnimatePresence>
        {open && (
          // No usa `fadeUp`: los avisos salen del pie y vuelven a el, asi que
          // entran y salen por abajo. La asimetria de fadeUp (entra desde
          // abajo, sale hacia arriba) los haria escapar por encima de la franja
          // que los contiene.
          <motion.div
            className="notices"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={t(spring.smooth)}
          >
            {commLost && (
              <Banner tone="error" title="Sin respuesta del microcontrolador">
                Los comandos ya no llegan a la máquina. Revisá el cable USB y volvé a conectar.
              </Banner>
            )}

            {zLoose && (
              <Banner
                tone="warn"
                title="El eje Z está sin energizar"
                action={
                  <Button variant="secondary" size="sm" onClick={onFixZ}>
                    Fijar cero
                  </Button>
                }
              >
                La pluma puede bajar sola por su propio peso. Volvé a fijar el cero antes de
                dibujar.
              </Banner>
            )}

            {warnings.length > 0 && <Banner tone="warn">{warnings.join(' · ')}</Banner>}

            {banner && (
              <Banner
                tone={banner.type === 'info' ? 'info' : banner.type}
                onDismiss={() => setBanner(null)}
              >
                {banner.text}
              </Banner>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <footer className="statusbar">
        <span className="statusbar__item tnum">
          Área {status?.max_x_mm ?? '—'} × {status?.max_y_mm ?? '—'} mm
        </span>
        <span className="statusbar__dot" />
        <span className="statusbar__item tnum">
          {spm ? `${spm.x} · ${spm.y} pasos/mm` : 'pasos/mm —'}
        </span>
        <span className="statusbar__dot" />
        <span className="statusbar__item tnum">
          {backlash ? `juego ${backlash.x} · ${backlash.y}` : 'juego —'}
        </span>

        {notices ? (
          <button
            type="button"
            className={`statusbar__notice statusbar__notice--${severity}`}
            onClick={() => setManuallyOpen((v) => !v)}
            aria-expanded={open}
          >
            <Icon name={severity === 'info' ? 'info-circle' : 'warning'} size={13} />
            <span className="statusbar__notice-text">{summary}</span>
            <Icon name={open ? 'chevron-down' : 'chevron-up'} size={13} />
          </button>
        ) : (
          <span className="statusbar__ok">Todo en orden</span>
        )}

        <span className={`statusbar__mode ${status?.simulating ? 'statusbar__mode--sim' : ''}`.trim()}>
          {!connected ? 'SIN CONEXIÓN' : status?.simulating ? 'SIMULACIÓN' : 'MÁQUINA REAL'}
        </span>
      </footer>
    </>
  )
}
