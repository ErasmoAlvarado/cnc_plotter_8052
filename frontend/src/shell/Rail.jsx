import { motion } from 'motion/react'
import { useStatus } from '../StatusContext.jsx'
import { stagger, useMotionPrefs } from '../motion.js'
import RailGroup from './RailGroup.jsx'
import DrawingPanel from './panels/DrawingPanel.jsx'
import MotionPanel from './panels/MotionPanel.jsx'
import CalibrationPanel from './panels/CalibrationPanel.jsx'
import PatternsPanel from './panels/PatternsPanel.jsx'
import PenControl from '../components/dashboard/PenControl.jsx'
import Button from '../components/ui/Button.jsx'

// columna de control. ancho fijo, scroll propio, y el orden del trabajo
// real: cargar el dibujo -> colocar la maquina -> ajustar la pluma ->
// (calibrar, probar patrones, cosas de vez en cuando que van al final)
export default function Rail({ drawing, onOpenConnection, onOpenCalibration, onOpenPenTuner }) {
  const { canOperate, config } = useStatus()
  const { gcode } = drawing
  const { reduce } = useMotionPrefs()

  const calibrated = !!config?.last_calibration_date

  return (
    // el stagger corre una sola vez al montar. colapsar un grupo no lo
    // vuelve a disparar, RailGroup anima su propia altura y su
    // AnimatePresence lleva initial={false} justo para eso
    <motion.nav
      className="rail"
      aria-label="Controles de la máquina"
      initial={reduce ? false : 'hidden'}
      animate="shown"
      variants={stagger.parent}
    >
      <RailGroup id="drawing" title="Dibujo" aside={gcode ? 'cargado' : null}>
        <DrawingPanel drawing={drawing} />
      </RailGroup>

      <RailGroup id="motion" title="Posición">
        <MotionPanel onConnect={onOpenConnection} />
      </RailGroup>

      <RailGroup id="pen" title="Pluma">
        <PenControl disabled={!canOperate} />
        {/* el ajuste fino abre su propia hoja y no vive aca adentro, buscar
            la presion es un rato de prueba y error con el papel puesto, no
            una accion del rail */}
        <Button variant="ghost" size="sm" block icon="scope" onClick={onOpenPenTuner}>
          Ajuste fino de presión
        </Button>
      </RailGroup>

      <RailGroup
        id="calibration"
        title="Calibración"
        aside={config && !calibrated ? 'pendiente' : null}
      >
        <CalibrationPanel onOpen={onOpenCalibration} />
      </RailGroup>

      <RailGroup id="patterns" title="Patrones de prueba" defaultOpen={false}>
        <PatternsPanel />
      </RailGroup>
    </motion.nav>
  )
}
