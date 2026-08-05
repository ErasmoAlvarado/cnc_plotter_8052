import { useRef } from 'react'

// convierte la estela a un solo atributo `d`, evita miles de nodos DOM y
// evita rehacer toda la conversion 5 veces por segundo
//
// si el array se achica o se reinicia se reconstruye todo, pasa pocas veces
export default function useTrailPath(trail, penSteps, project) {
  const cache = useRef({ d: '', count: 0, pluma: false, key: null })

  // si cambia el area o los ejes, lo ya convertido ya no sirve
  const key = `${project.key}|${penSteps}`
  const c = cache.current

  if (c.key !== key || trail.length < c.count) {
    cache.current = { d: '', count: 0, pluma: false, key }
  }

  const estado = cache.current
  if (trail.length > estado.count) {
    let d = estado.d
    let dibujando = estado.pluma

    for (let i = estado.count; i < trail.length; i += 1) {
      const [x, y, z] = trail[i]
      const abajo = z >= penSteps        // mismo criterio que usa el firmware
      if (!abajo) {
        dibujando = false
        continue
      }
      // un salto con la pluma arriba corta el trazo
      d += `${dibujando ? 'L' : 'M'}${project.x(x).toFixed(3)},${project.y(y).toFixed(3)}`
      dibujando = true
    }

    cache.current = { d, count: trail.length, pluma: dibujando, key }
  }

  return cache.current.d
}
