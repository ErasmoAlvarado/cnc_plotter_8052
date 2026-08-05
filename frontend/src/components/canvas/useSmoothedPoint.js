import { useEffect, useRef, useState } from 'react'

const REDUCED = '(prefers-reduced-motion: reduce)'

// interpola el cabezal entre muestras del websocket con un lerp por frame,
// nunca se adelanta a la ultima posicion real conocida
//
// numeros sueltos y no {x,y}, un objeto nuevo reiniciaria el efecto cada frame
export default function useSmoothedPoint(tx, ty, { factor = 0.22, epsilon = 0.01 } = {}) {
  const hasTarget = Number.isFinite(tx) && Number.isFinite(ty)

  // el primer valor se toma en el render inicial, si no falta un frame al aparecer
  const [point, setPoint] = useState(() => (hasTarget ? { x: tx, y: ty } : null))
  const targetRef = useRef(null)
  const currentRef = useRef(hasTarget ? { x: tx, y: ty } : null)
  const rafRef = useRef(0)
  targetRef.current = hasTarget ? { x: tx, y: ty } : null

  useEffect(() => {
    if (!hasTarget) {
      currentRef.current = null
      setPoint(null)
      return
    }

    // primer punto o reduced motion, aparece directo donde va sin animar
    if (!currentRef.current || window.matchMedia(REDUCED).matches) {
      currentRef.current = { x: tx, y: ty }
      setPoint(currentRef.current)
      return
    }

    function tick() {
      const t = targetRef.current
      const c = currentRef.current
      if (!t || !c) return

      const dx = t.x - c.x
      const dy = t.y - c.y

      if (Math.abs(dx) < epsilon && Math.abs(dy) < epsilon) {
        currentRef.current = t
        setPoint(t)
        return
      }

      const next = { x: c.x + dx * factor, y: c.y + dy * factor }
      currentRef.current = next
      setPoint(next)
      rafRef.current = requestAnimationFrame(tick)
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [tx, ty, hasTarget, factor, epsilon])

  return point
}
