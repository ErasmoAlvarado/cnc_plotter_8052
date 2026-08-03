import { useRef } from 'react'

// La estela real convertida a UN solo atributo `d`.
//
// Dos problemas que resuelve, los dos medidos durante un trabajo real:
//
//   1. Un <polyline> por tramo con la pluma abajo llegaba a miles de nodos
//      del DOM. Ahora es un unico <path> con varios subtrazados (M...L...M).
//
//   2. La conversion se rehacia ENTERA en cada mensaje del WebSocket (cinco
//      por segundo), formateando otra vez los miles de puntos anteriores.
//      Como StatusContext solo anade al final, aqui se guarda lo ya
//      convertido y se concatena unicamente lo nuevo.
//
// Si el array encoge o se reinicia (trabajo nuevo, o el tope circular
// descartando puntos viejos) se reconstruye entero, que es lo correcto y
// ademas pasa muy de vez en cuando.
export default function useTrailPath(trail, penSteps, project) {
  const cache = useRef({ d: '', count: 0, pluma: false, key: null })

  // La proyeccion cambia si cambia el area o el sentido de los ejes: lo ya
  // convertido deja de valer.
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
      const abajo = z >= penSteps        // el mismo criterio que el firmware
      if (!abajo) {
        dibujando = false
        continue
      }
      // Un salto con la pluma arriba corta el trazo: la estela es la prueba
      // de por donde paso la maquina DIBUJANDO, no de por donde viajo.
      d += `${dibujando ? 'L' : 'M'}${project.x(x).toFixed(3)},${project.y(y).toFixed(3)}`
      dibujando = true
    }

    cache.current = { d, count: trail.length, pluma: dibujando, key }
  }

  return cache.current.d
}
