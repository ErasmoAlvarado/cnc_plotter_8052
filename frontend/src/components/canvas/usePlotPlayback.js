import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

// Reproduccion "en seco" del dibujo, sin maquina.
//
// Recorre los mismos trazos que pinta el lienzo a una velocidad plausible y
// emite las mismas senales que el seguimiento en vivo (cuantos trazos van y
// donde esta el cabezal). Sirve para dos cosas reales:
//   - ver el orden de trazado antes de gastar tinta y papel,
//   - probar la interfaz sin nada conectado.
export default function usePlotPlayback(paths, { speedMmPerSec = 45 } = {}) {
  const [playing, setPlaying] = useState(false)
  const [state, setState] = useState({ index: 0, head: null })
  const rafRef = useRef(0)

  // Los trazos se aplanan a segmentos rectos con su longitud: recorrer por
  // distancia (y no por numero de puntos) hace que la velocidad sea constante
  // en mm/s, como en la maquina real, en vez de acelerarse en los arcos —
  // que traen decenas de puntos muy juntos.
  const segments = useMemo(() => {
    const segs = []
    for (let i = 0; i < paths.length; i += 1) {
      const p = paths[i]
      const pts = p.points ?? []
      for (let j = 1; j < pts.length; j += 1) {
        const [x0, y0] = pts[j - 1]
        const [x1, y1] = pts[j]
        const len = Math.hypot(x1 - x0, y1 - y0)
        if (len > 0) segs.push({ pathIndex: i, x0, y0, x1, y1, len, draw: p.type !== 'rapid' })
      }
    }
    return segs
  }, [paths])

  const stop = useCallback(() => {
    cancelAnimationFrame(rafRef.current)
    setPlaying(false)
    setState({ index: 0, head: null })
  }, [])

  const start = useCallback(() => {
    if (segments.length === 0) return
    cancelAnimationFrame(rafRef.current)
    setPlaying(true)

    let travelled = 0
    let last = performance.now()
    // Cursor que solo avanza. Un fichero grande puede tener decenas de miles de
    // segmentos: buscarlos desde el principio en cada frame costaria mas que
    // dibujar.
    let cursor = 0
    let accBefore = 0

    const step = (now) => {
      travelled += ((now - last) / 1000) * speedMmPerSec
      last = now

      while (cursor < segments.length && travelled > accBefore + segments[cursor].len) {
        accBefore += segments[cursor].len
        cursor += 1
      }

      const seg = segments[cursor] ?? null
      const local = travelled - accBefore

      if (!seg) {
        const end = segments[segments.length - 1]
        setState({
          index: paths.length,
          head: { x: end.x1, y: end.y1, penDown: false },
        })
        setPlaying(false)
        return
      }

      const t = seg.len === 0 ? 0 : local / seg.len
      setState({
        index: seg.pathIndex,
        head: {
          x: seg.x0 + (seg.x1 - seg.x0) * t,
          y: seg.y0 + (seg.y1 - seg.y0) * t,
          penDown: seg.draw,
        },
      })
      rafRef.current = requestAnimationFrame(step)
    }

    rafRef.current = requestAnimationFrame(step)
  }, [segments, speedMmPerSec, paths.length])

  // Un G-code nuevo invalida la reproduccion del anterior.
  useEffect(() => stop, [stop])
  useEffect(() => {
    stop()
  }, [segments, stop])

  return { playing, index: state.index, head: state.head, start, stop }
}
