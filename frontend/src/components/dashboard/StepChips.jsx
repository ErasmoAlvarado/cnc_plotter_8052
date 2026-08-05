import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { collapse, spring, useMotionPrefs } from '../../motion.js'
import SegmentedControl from '../ui/SegmentedControl.jsx'

const PRESETS = [0.1, 1, 5, 10]

// chips de paso en vez de un campo numerico, el 95% de las veces el
// usuario quiere uno de estos 4 valores y escribirlos a mano es friccion
// de mas. el campo libre sigue ahi para el caso raro, atras de "otro"
export default function StepChips({ value, onChange }) {
  const [custom, setCustom] = useState(false)
  const { t } = useMotionPrefs()

  const options = [
    ...PRESETS.map((p) => ({ value: String(p), label: `${p}` })),
    { value: 'custom', label: 'otro' },
  ]

  const selected = custom ? 'custom' : String(value)

  function handleChange(next) {
    if (next === 'custom') {
      setCustom(true)
      return
    }
    setCustom(false)
    onChange(Number(next))
  }

  return (
    <div className="stack">
      <SegmentedControl
        label="Paso de movimiento en milímetros"
        options={options}
        value={selected}
        onChange={handleChange}
      />
      <AnimatePresence initial={false}>
        {custom && (
          <motion.div {...collapse} transition={t(spring.smooth)} style={{ overflow: 'hidden' }}>
            <input
              className="field__input"
              type="number"
              min={0.01}
              max={500}
              step={0.1}
              autoFocus
              value={value}
              aria-label="Paso a medida en milímetros"
              onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
