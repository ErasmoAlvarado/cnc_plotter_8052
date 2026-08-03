import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { api } from '../../api'
import { useStatus } from '../../StatusContext.jsx'
import { fadeUp, spring, useMotionPrefs } from '../../motion.js'
import Button from '../../components/ui/Button.jsx'
import DisabledHint from '../../components/ui/DisabledHint.jsx'
import Stepper from '../../components/ui/Stepper.jsx'

// Los cinco patrones que sabe dibujar el backend (PATTERNS en cnc_api.py).
const ETIQUETAS = {
  square: 'Cuadrado',
  triangle: 'Triángulo',
  circle: 'Círculo',
  star: 'Estrella',
  grid: 'Rejilla',
}

// Atajo para comprobar la calibracion sin tener que buscar un G-code: un
// cuadrado de 20 mm que se mide con una regla dice en diez segundos si los
// pasos/mm estan bien.
//
// El tamano maximo lo dice el backend y no se calcula aqui: 'size' no significa
// lo mismo en todos los patrones —es el lado del cuadrado, pero el RADIO del
// circulo y el ESPACIADO de cada celda de la rejilla— asi que un unico "cabe si
// size <= area" era falso para tres de los cinco. Un circulo de 60 en una
// maquina de 80 mm mide 121 mm de ancho, y hasta ahora se dibujaba contra el
// tope.
export default function PatternsPanel() {
  const { startJob, reason, status, busy } = useStatus()
  const [size, setSize] = useState('20')
  const [limites, setLimites] = useState(null)
  const { t } = useMotionPrefs()

  // Los maximos dependen del area, asi que se releen cuando esta cambia.
  useEffect(() => {
    let vivo = true
    api
      .listPatterns()
      .then((r) => vivo && setLimites(Object.fromEntries(
        r.patterns.map((p) => [p.id, p.max_size_mm]),
      )))
      .catch(() => {})
    return () => {
      vivo = false
    }
  }, [status?.max_x_mm, status?.max_y_mm])

  const blockReason = reason('move')
  const sizeNum = Number(size)
  const sizeValid = sizeNum > 0 && sizeNum <= 1000
  const patrones = Object.keys(ETIQUETAS)
  const excedidos = patrones.filter((p) => limites && sizeNum > limites[p])

  return (
    <DisabledHint reason={blockReason}>
      <Stepper
        value={size}
        onChange={setSize}
        min={1}
        max={1000}
        step={5}
        suffix="mm"
        aria-label="Tamaño del patrón en milímetros"
      />

      <div className="pattern-grid">
        {patrones.map((id) => {
          const maximo = limites?.[id]
          const cabe = maximo === undefined || sizeNum <= maximo
          return (
            <Button
              key={id}
              variant="secondary"
              size="sm"
              disabled={!sizeValid || !cabe || busy}
              title={cabe ? undefined : `Máximo ${maximo} mm en esta área`}
              onClick={() => startJob(() => api.testPattern(id, sizeNum)).catch(() => {})}
            >
              {ETIQUETAS[id]}
            </Button>
          )
        })}
      </div>

      <AnimatePresence>
        {excedidos.length > 0 && sizeValid && (
          <motion.p className="hint field__warn" {...fadeUp} transition={t(spring.smooth)}>
            {excedidos.length === patrones.length
              ? `Ningún patrón entra a ${sizeNum} mm en un área de ${status?.max_x_mm ?? '—'} × ${status?.max_y_mm ?? '—'} mm.`
              : `A ${sizeNum} mm no entran: ${excedidos.map((p) => ETIQUETAS[p].toLowerCase()).join(', ')}.`}{' '}
            {limites && `El círculo mide el doble de su radio y la rejilla cuatro celdas de lado.`}
          </motion.p>
        )}
      </AnimatePresence>
    </DisabledHint>
  )
}
