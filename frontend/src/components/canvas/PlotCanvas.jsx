import { memo, useMemo } from 'react'
import { projection, viewport } from '../../coords.js'
import PlotHead from './PlotHead.jsx'
import useTrailPath from './useTrailPath.js'

// canvas del dibujo, no sabe nada del backend ni del websocket
//
// la geometria la resuelve coords.js, no aca
//
// presupuesto de rendimiento: hasta 5000 trazos, mensajes 5 veces por segundo
function PlotCanvas({
  paths = [],
  workArea,
  bounds,
  donePathCount = 0,
  head = null,
  trail = [],
  penSteps = 100,
  fits = true,
  pulsing = false,
  showGrid = true,
  invertX = false,
  invertY = false,
  className = '',
}) {
  const maxX = workArea?.max_x_mm ?? bounds?.max_x ?? 100
  const maxY = workArea?.max_y_mm ?? bounds?.max_y ?? 100

  const project = useMemo(
    () => projection({ maxX, maxY, invertX, invertY }),
    [maxX, maxY, invertX, invertY],
  )
  const { maxDim, viewBox } = useMemo(() => viewport({ maxX, maxY }), [maxX, maxY])

  // paso 1: el `d` de cada trazo, una sola vez, no depende del progreso
  const parts = useMemo(
    () =>
      paths.map((p) => {
        if (!p.points?.length) return null
        let d = ''
        for (let j = 0; j < p.points.length; j += 1) {
          const [x, y] = p.points[j]
          d += `${j === 0 ? 'M' : 'L'}${project.x(x).toFixed(3)},${project.y(y).toFixed(3)}`
        }
        return { d, rapid: p.type === 'rapid' }
      }),
    [paths, project],
  )

  // paso 2: repartir en 4 capas, cambia cada mensaje pero solo concatena
  const { pendingDraw, pendingRapid, doneDraw, doneRapid } = useMemo(() => {
    const acc = { pendingDraw: '', pendingRapid: '', doneDraw: '', doneRapid: '' }
    for (let i = 0; i < parts.length; i += 1) {
      const part = parts[i]
      if (!part) continue
      const done = i < donePathCount
      acc[done ? (part.rapid ? 'doneRapid' : 'doneDraw')
               : (part.rapid ? 'pendingRapid' : 'pendingDraw')] += part.d
    }
    return acc
  }, [parts, donePathCount])

  const trailPath = useTrailPath(trail, penSteps, project)

  const gridLines = useMemo(() => {
    if (!showGrid) return []
    const step = maxDim > 120 ? 25 : 10
    const lines = []
    for (let x = step; x < maxX; x += step) lines.push(['v', x])
    for (let y = step; y < maxY; y += step) lines.push(['h', y])
    return lines
  }, [showGrid, maxX, maxY, maxDim])

  // proporcional a maxDim, el cabezal se ve igual de grande en cualquier area
  const headR = maxDim * 0.011

  return (
    <svg
      className={`plot-canvas ${className}`.trim()}
      viewBox={viewBox}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Vista del dibujo y posición de la máquina"
    >
      {/* el papel, area util de la maquina. va debajo de todo */}
      <rect className="plot-canvas__paper" x={0} y={0} width={maxX} height={maxY} />

      {gridLines.map(([dir, v]) =>
        dir === 'v' ? (
          <line key={`v${v}`} className="plot-canvas__grid" x1={project.x(v)} y1={0} x2={project.x(v)} y2={maxY} />
        ) : (
          <line key={`h${v}`} className="plot-canvas__grid" x1={0} y1={project.y(v)} x2={maxX} y2={project.y(v)} />
        ),
      )}

      {/* que esquina es el origen lo decide coords.js segun invert_x/invert_y */}
      <circle
        className="plot-canvas__origin"
        cx={project.origin.cx}
        cy={project.origin.cy}
        r={maxDim * 0.008}
      />

      {pendingRapid && <path className="plot-canvas__pending plot-canvas__pending--rapid" d={pendingRapid} />}
      {pendingDraw && <path className="plot-canvas__pending" d={pendingDraw} />}
      {doneRapid && <path className="plot-canvas__done plot-canvas__done--rapid" d={doneRapid} />}
      {doneDraw && <path className="plot-canvas__done" d={doneDraw} />}

      {trailPath && <path className="plot-canvas__trail" d={trailPath} />}

      {head && (
        <PlotHead
          x={head.x}
          y={head.y}
          penDown={head.penDown}
          project={project}
          radius={headR}
          pulsing={pulsing}
        />
      )}

      {/* marca el borde en rojo, el texto del aviso va en el panel del rail */}
      {!fits && (
        <rect className="plot-canvas__overflow" x={0} y={0} width={maxX} height={maxY} />
      )}
    </svg>
  )
}

export default memo(PlotCanvas)
