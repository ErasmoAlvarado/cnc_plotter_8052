import { useCallback, useMemo, useState } from 'react'
import { api } from '../api'
import { useStatus } from '../StatusContext.jsx'
import usePlotPlayback from '../components/canvas/usePlotPlayback.js'

// cuantos trazos del preview ya estan dibujados, segun la linea de gcode que
// manda el websocket. vienen ordenados por 'line' asi que alcanza con
// busqueda binaria aunque haya 5000
//
// si el backend es viejo y no manda 'line' esto da 0 y el canvas queda en
// modo "solo estela" nomas, se ve por donde va la maquina pero sin colorear
// el trazado planeado
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

// estado del dibujo, compartido entre el rail (resumen del archivo) y el
// stage (canvas y botones). antes vivia todo junto en GcodeCard, ahora que
// la vista esta partida en dos subimos esto un escalon y baja por props.
// es el mismo codigo de antes nomas movido, sin cambiar logica
export default function useDrawing() {
  const { gcode, setGcode, live, resetLive, status, runAction } = useStatus()
  const [uploading, setUploading] = useState(false)
  const penSteps = status?.pen_steps ?? 100

  // espejo en Y y "ajustar al area" son del archivo, no de la maquina --
  // el espejo depende de con que se exporto el gcode y el ajuste de si cabe
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
        // archivo nuevo = transformacion nueva, el backend tambien la resetea
        setFlipY(false)
        setFitted(false)
      } catch {
        // el banner ya lo puso runAction
      } finally {
        setUploading(false)
      }
    },
    [runAction, resetLive, setGcode],
  )

  // el seguimiento en vivo manda sobre la reproduccion en seco: si la
  // maquina esta dibujando de verdad, eso es lo que importa mostrar.
  //
  // se mantiene tambien cuando el job ya termino (live.line > 0 con active
  // false), asi el dibujo queda pintado en vez de volver a gris de golpe.
  // un job nuevo limpia live y arranca de cero otra vez
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

  // aplica espejo Y o "ajustar al area" al archivo ya cargado. el backend
  // devuelve el preview nuevo asi el canvas ya pinta el resultado antes de
  // que el usuario confirme nada
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
        // el banner ya lo puso runAction
      }
    },
    [flipY, fitted, runAction, resetLive, setGcode],
  )

  // memoizado porque AppShell pasa esto por props a Rail y Stage, una
  // referencia nueva en cada render re-renderiza a los dos sin necesidad
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
