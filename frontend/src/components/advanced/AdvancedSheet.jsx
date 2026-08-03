import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { spring, useMotionPrefs } from '../../motion.js'
import Sheet from '../ui/Sheet.jsx'
import SegmentedControl from '../ui/SegmentedControl.jsx'
import SpeedSection from './SpeedSection.jsx'
import SettingsSection from './SettingsSection.jsx'
import PenSection from './PenSection.jsx'
import UtilitiesSection from './UtilitiesSection.jsx'

const SECTIONS = [
  { value: 'speed', label: 'Velocidad', Component: SpeedSection },
  { value: 'settings', label: 'Ajustes', Component: SettingsSection },
  { value: 'pen', label: 'Pluma', Component: PenSection },
  { value: 'tools', label: 'Diagnóstico', Component: UtilitiesSection },
]

// Todo lo que un usuario nuevo no necesita tocar. Vive fuera de la pantalla
// principal —a un clic, no a cinco— para que el dashboard pueda dedicarse a lo
// que se usa todos los días.
export default function AdvancedSheet({ open, onClose, initialSection = 'speed' }) {
  const [section, setSection] = useState(initialSection)
  const Current = SECTIONS.find((s) => s.value === section)?.Component ?? SpeedSection
  const { t } = useMotionPrefs()

  return (
    <Sheet open={open} onClose={onClose} title="Ajustes avanzados">
      <SegmentedControl
        label="Secciones de ajustes"
        options={SECTIONS}
        value={section}
        onChange={setSection}
      />
      {/* Cruce con `mode="wait"`: las cuatro secciones tienen alturas muy
          distintas, y solapandolas la hoja daria un tiron mientras las dos
          existen a la vez. Se desvanece una, entra la otra. */}
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={section}
          className="stack"
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={t(spring.gentle)}
        >
          <Current />
        </motion.div>
      </AnimatePresence>
    </Sheet>
  )
}
