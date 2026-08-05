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

// armazon de la app, grid de 3 filas y 2 columnas que ocupa toda la ventana
//
// la pagina nunca scrollea, solo el rail, asi el canvas usa todo el espacio
//
// todo lo que no es ver el dibujo o mover la maquina va en hojas modales
export default function AppShell() {
  const [sheet, setSheet] = useState(null)
  const [recovery, setRecovery] = useState(null)
  // el aviso de Z sin energizar entra directo al paso del wizard que lo arregla
  const [wizardStep, setWizardStep] = useState(0)
  // solo se usa debajo de 1024px, donde el rail pasa a ser un cajon
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
      {/* fade corto al arrancar, sin esto se ve la grilla pelada tironeando */}
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

        {/* cortina del cajon, solo existe en pantallas angostas */}
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

      {/* montado siempre, es lo que permite animar el cierre */}
      <RecoveryDialog recovery={recovery} onClose={() => setRecovery(null)} />
    </TooltipProvider>
  )
}
