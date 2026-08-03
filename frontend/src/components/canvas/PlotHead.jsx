import { memo } from 'react'
import useSmoothedPoint from './useSmoothedPoint.js'

// El cabezal, en su propio componente y memoizado.
//
// No es una separacion cosmetica: useSmoothedPoint llama a setState en CADA
// frame para interpolar entre las muestras del WebSocket. Mientras vivio
// dentro de PlotCanvas, eso re-renderizaba el SVG entero a 60 fps —incluidos
// los cuatro <path> de hasta 5000 trazos, que React tiene que volver a
// comparar cadena a cadena—. De ahi que la interfaz se atascara justo
// mientras la maquina dibujaba, que es cuando mas se mira.
//
// Aqui el bucle de animacion solo puede repintar estos dos circulos.
function PlotHead({ x, y, penDown, project, radius, pulsing }) {
  // Numeros sueltos y no un objeto {x,y}: con un objeto, cada render del
  // padre crea una referencia nueva y el efecto se reiniciaria en cada frame.
  const smooth = useSmoothedPoint(x, y)
  if (!smooth) return null

  const cx = project.x(smooth.x)
  const cy = project.y(smooth.y)

  return (
    <>
      <circle
        className={`plot-canvas__head-halo ${pulsing ? 'plot-canvas__head-halo--pulsing' : ''}`.trim()}
        cx={cx}
        cy={cy}
        r={radius * 1.8}
      />
      <circle
        className={`plot-canvas__head ${penDown ? 'plot-canvas__head--down' : ''}`.trim()}
        cx={cx}
        cy={cy}
        r={radius}
      />
    </>
  )
}

export default memo(PlotHead)
