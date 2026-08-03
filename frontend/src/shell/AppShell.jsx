import { useCallback, useEffect, useState } from 'react'
import { motion } from 'motion/react'
import { useMotionPrefs } from '../motion.js'
import { TooltipProvider } from '../components/ui/Tooltip.jsx'
import ConnectionSheet from '../components/connection/ConnectionSheet.jsx'
import RecoveryDialog from '../components/connection/RecoveryDialog.jsx'
import CalibrationWizard from '../components/calibration/CalibrationWizard.jsx'
import AdvancedSheet from '../components/advanced/AdvancedSheet.jsx'
import PenTunerSheet from '../components/pen/PenTunerSheet.jsx'
import TopBar from './TopBar.jsx'
import Rail from './Rail.jsx'
import Stage from './Stage.jsx'
import StatusBar from './StatusBar.jsx'
import useDrawing from './useDrawing.js'

// Armazon de la aplicacion.
//
// Es una rejilla de tres filas (barra / cuerpo / pie) y dos columnas
// (rail / escenario) que ocupa exactamente la ventana. La pagina no scrollea
// nunca: lo que scrollea es el rail, por su cuenta. Eso es lo que permite que
// el lienzo se quede con todo el espacio que sobre, en vez de dejar margenes
// vacios a los lados como hacia el dashboard centrado de 1180 px.
//
// Todo lo que no es "mirar el dibujo" o "mover la maquina" vive en hojas
// modales, igual que antes.
export default function AppShell() {
  const [sheet, setSheet] = useState(null)
  const [recovery, setRecovery] = useState(null)
  // El aviso de "Z sin energizar" y el paso 3 del asistente son el mismo tema:
  // desde el aviso se entra directamente al paso que lo resuelve.
  const [wizardStep, setWizardStep] = useState(0)
  // Solo se usa por debajo de 1024 px, donde el rail pasa a ser un cajon.
  const [railOpen, setRailOpen] = useState(false)
  const { reduce } = useMotionPrefs()

  const drawing = useDrawing()

  const openWizard = useCallback((step = 0) => {
    setWizardStep(step)
    setSheet('calibration')
  }, [])

  const closeRail = useCallback(() => setRailOpen(false), [])

  useEffect(() => {
    if (!railOpen) return
    const onKey = (e) => e.key === 'Escape' && setRailOpen(false)
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [railOpen])

  return (
    <TooltipProvider>
      {/* Fundido corto al arrancar. Las fuentes y el primer /api/status llegan
          un instante despues del primer pintado, y sin esto lo que se ve es la
          rejilla desnuda dando un tiron. Es opacidad y nada mas: mover el
          armazon entero seria justo el gesto llamativo que v3 no quiere. */}
      <motion.div
        className={`shell ${railOpen ? 'shell--rail-open' : ''}`.trim()}
        initial={reduce ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.15, ease: [0.22, 1, 0.36, 1] }}
      >
        <TopBar
          onOpenConnection={() => setSheet('connection')}
          onOpenAdvanced={() => setSheet('advanced')}
          onToggleRail={() => setRailOpen((v) => !v)}
          railOpen={railOpen}
        />

        <Rail
          drawing={drawing}
          onOpenConnection={() => setSheet('connection')}
          onOpenCalibration={() => openWizard(0)}
          onOpenPenTuner={() => setSheet('pen')}
          onNavigate={closeRail}
        />

        {/* Cortina del cajon: solo existe en pantallas angostas. */}
        <button
          type="button"
          className="rail-scrim"
          aria-label="Cerrar el panel de controles"
          onClick={closeRail}
          tabIndex={railOpen ? 0 : -1}
        />

        <Stage drawing={drawing} />

        <StatusBar onFixZ={() => openWizard(2)} />
      </motion.div>

      <ConnectionSheet
        open={sheet === 'connection'}
        onClose={() => setSheet(null)}
        onRecovery={setRecovery}
      />

      <CalibrationWizard
        open={sheet === 'calibration'}
        initialStep={wizardStep}
        onClose={() => setSheet(null)}
      />

      <AdvancedSheet open={sheet === 'advanced'} onClose={() => setSheet(null)} />

      <PenTunerSheet open={sheet === 'pen'} onClose={() => setSheet(null)} />

      {/* Montado siempre, igual que las otras tres hojas: es lo que le permite
          animar su cierre — ver el comentario en RecoveryDialog. */}
      <RecoveryDialog recovery={recovery} onClose={() => setRecovery(null)} />
    </TooltipProvider>
  )
}
