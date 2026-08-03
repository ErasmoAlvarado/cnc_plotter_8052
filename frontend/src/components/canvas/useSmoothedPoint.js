import { useEffect, useRef, useState } from 'react'

const REDUCED = '(prefers-reduced-motion: reduce)'

// Interpola el cabezal entre las muestras que llegan por WebSocket.
//
// El backend emite progreso como mucho cada 200 ms (last_ws_update en
// run_gcode_thread), asi que pintar la posicion cruda da un movimiento a cinco
// saltos por segundo. Este hook persigue el objetivo con un lerp por frame: el
// cabezal siempre va hacia la ultima posicion REAL conocida, nunca la adelanta,
// solo suaviza el camino hasta ella.
//
// Recibe numeros sueltos y no un objeto {x,y} a proposito: con un objeto, cada
// render del padre crea una referencia nueva y el efecto se reiniciaria en cada
// frame.
export default function useSmoothedPoint(tx, ty, { factor = 0.22, epsilon = 0.01 } = {}) {
  const hasTarget = Number.isFinite(tx) && Number.isFinite(ty)

  // El primer valor se toma ya en el render inicial, no en el efecto: si no, el
  // cabezal falta durante un frame cada vez que aparece el lienzo.
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

    // Primer punto, o movimiento reducido: aparecer directamente donde toca.
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
