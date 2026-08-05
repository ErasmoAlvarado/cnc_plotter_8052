import { memo } from 'react'
import useSmoothedPoint from './useSmoothedPoint.js'

// separado y memoizado porque interpola a 60fps, sino repintaba todo el svg
function PlotHead({ x, y, penDown, project, radius, pulsing }) {
  // numeros sueltos y no {x,y}, un objeto nuevo reiniciaria el efecto cada frame
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
