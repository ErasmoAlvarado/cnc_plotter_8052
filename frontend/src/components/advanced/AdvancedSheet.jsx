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

// todo lo que un usuario nuevo no necesita tocar. va fuera de la pantalla
// principal (a un click, no a cinco) para que el dashboard se dedique a
// lo que se usa todos los dias
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
      {/* cruce con mode="wait", las 4 secciones tienen alturas muy
          distintas y solapadas la hoja pegaria un tiron mientras las 2
          existen a la vez. se desvanece una, entra la otra */}
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
