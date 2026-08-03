import { useCallback, useMemo, useState } from 'react'
import { api } from '../api'
import { useStatus } from '../StatusContext.jsx'
import usePlotPlayback from '../components/canvas/usePlotPlayback.js'

// Cuantos trazos del preview ya se dibujaron, a partir de la linea de G-code
// que reporta el WebSocket. Los trazos vienen ordenados por 'line' ascendente,
// asi que una busqueda binaria basta y no cuesta nada aunque haya 5000.
//
// Si el backend es anterior al campo 'line', esto devuelve 0 y el lienzo se
// queda en modo "solo estela": se sigue viendo por donde va la maquina, solo
// que sin colorear el trazado planificado.
function completedPaths(paths, currentLine) {
  if (!paths.length || paths[0].line === undefined || !currentLine) return 0
  let lo = 0
  let hi = paths.length
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (paths[mid].line < currentLine) lo = mid + 1
    else hi = mid
  }
  return lo
}

// Estado del dibujo, compartido entre el rail (resumen del archivo) y el
// escenario (lienzo y botones). Antes vivia dentro de GcodeCard, que era un
// unico componente; ahora que la vista esta partida en dos, vive un escalon mas
// arriba y baja por props.
//
// Lo que se movio aca es exactamente lo que habia, sin cambios de logica: subir
// el archivo, el corte pendiente/dibujado y la posicion del cabezal.
export default function useDrawing() {
  const { gcode, setGcode, live, resetLive, status, runAction } = useStatus()
  const [uploading, setUploading] = useState(false)
  const penSteps = status?.pen_steps ?? 100

  // Espejo en Y y "Ajustar al area" son por fichero, no de la maquina: el
  // espejo depende de con que se exporto el G-code y el ajuste, de si cabe.
  const [flipY, setFlipY] = useState(false)
  const [fitted, setFitted] = useState(false)

  const paths = useMemo(() => gcode?.preview_paths ?? [], [gcode])
  const playback = usePlotPlayback(paths)

  const upload = useCallback(
    async (file) => {
      if (!file) return
      setUploading(true)
      try {
        const result = await runAction(() => api.uploadGcode(file))
        resetLive()
        setGcode(result)
        // Fichero nuevo, transformacion nueva: el backend tambien la reinicia.
        setFlipY(false)
        setFitted(false)
      } catch {
        // runAction ya puso el banner
      } finally {
        setUploading(false)
      }
    },
    [runAction, resetLive, setGcode],
  )

  // El seguimiento en vivo manda sobre la reproduccion en seco: si la maquina
  // esta dibujando de verdad, eso es lo que hay que mirar.
  //
  // Se mantiene tambien cuando el trabajo YA termino (live.line > 0 con
  // active en false): al acabar, el dibujo se queda pintado en vez de volver a
  // gris de golpe, que es lo que uno espera ver despues de dibujarlo. Un
  // trabajo nuevo limpia live y vuelve a empezar de cero.
  const tracking = !playback.playing && (live.active || live.line > 0)

  const donePathCount = tracking
    ? completedPaths(paths, live.line)
    : playback.playing
      ? playback.index
      : 0

  const head = useMemo(() => {
    if (tracking && live.x !== null) {
      return { x: live.x, y: live.y, penDown: (live.zSteps ?? 0) >= penSteps }
    }
    return playback.head
  }, [tracking, live.x, live.y, live.zSteps, penSteps, playback.head])

  // Aplicar espejo en Y o "Ajustar al area" al fichero ya cargado. El backend
  // devuelve el preview nuevo, asi que el lienzo pinta el resultado antes de
  // que el usuario confirme nada.
  const applyTransform = useCallback(
    async (next) => {
      const flip = next.flipY ?? flipY
      const fit = next.fit ?? fitted
      try {
        const result = await runAction(() => api.gcodeTransform(flip, fit))
        resetLive()
        setGcode((prev) => ({ ...prev, ...result }))
        setFlipY(flip)
        setFitted(fit)
      } catch {
        // runAction ya puso el banner
      }
    },
    [flipY, fitted, runAction, resetLive, setGcode],
  )

  // El objeto se memoiza porque AppShell lo pasa por props a Rail y a Stage:
  // una referencia nueva en cada render los re-renderiza a los dos aunque no
  // haya cambiado el dibujo.
  return useMemo(
    () => ({
      gcode,
      paths,
      playback,
      upload,
      uploading,
      tracking,
      donePathCount,
      head,
      penSteps,
      trail: tracking ? live.trail : [],
      flipY,
      fitted,
      applyTransform,
    }),
    [gcode, paths, playback, upload, uploading, tracking, donePathCount, head,
     penSteps, live.trail, flipY, fitted, applyTransform],
  )
}
