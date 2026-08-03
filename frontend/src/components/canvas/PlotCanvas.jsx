import { memo, useMemo } from 'react'
import { projection, viewport } from '../../coords.js'
import PlotHead from './PlotHead.jsx'
import useTrailPath from './useTrailPath.js'

// Lienzo del dibujo. No sabe nada del backend ni del WebSocket: recibe los
// trazos, cuantos van completados y donde esta el cabezal, y pinta.
//
// Geometria: la relacion entre los milimetros de la maquina y el SVG la
// decide coords.js, no este fichero. Es lo que permite que el origen se pinte
// en la esquina que el usuario tiene delante (arriba a la izquierda en esta
// maquina) sin que ningun componente calcule su propio `maxY - y`. El viewBox
// va en milimetros, de forma que un G-code de 40 mm y uno de 200 mm se ven
// igual de grandes en pantalla.
//
// Rendimiento: el backend manda hasta 5000 trazos (MAX_PREVIEW_PATHS) y el
// WebSocket avisa cinco veces por segundo. Por eso:
//   - el `d` de cada trazo se calcula UNA vez y solo se reparte en cuatro
//     capas segun el progreso (concatenar cadenas ya hechas, sin volver a
//     formatear miles de numeros en cada mensaje),
//   - la estela se acumula incrementalmente en un solo <path> (useTrailPath),
//   - el cabezal vive en su propio componente memoizado (PlotHead), porque
//     su interpolacion repinta a 60 fps y arrastraba consigo todo lo demas.
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

  // Paso 1: el `d` de cada trazo, calculado una sola vez. Depende del dibujo
  // y de la proyeccion, NO del progreso.
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

  // Paso 2: repartir en cuatro capas (pendiente/completado x dibujo/rapido).
  // Esto si cambia con cada mensaje de progreso, pero ya solo concatena.
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

  // Radio en unidades del viewBox (o sea, en mm): al ser proporcional a
  // maxDim, el cabezal se ve del mismo tamano en pantalla trabaje la maquina
  // en 40 mm o en 200 mm.
  const headR = maxDim * 0.011

  return (
    <svg
      className={`plot-canvas ${className}`.trim()}
      viewBox={viewBox}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Vista del dibujo y posición de la máquina"
    >
      {/* El papel: el area util de la maquina. Va debajo de todo, porque es la
          superficie sobre la que ocurre el resto. */}
      <rect className="plot-canvas__paper" x={0} y={0} width={maxX} height={maxY} />

      {gridLines.map(([dir, v]) =>
        dir === 'v' ? (
          <line key={`v${v}`} className="plot-canvas__grid" x1={project.x(v)} y1={0} x2={project.x(v)} y2={maxY} />
        ) : (
          <line key={`h${v}`} className="plot-canvas__grid" x1={0} y1={project.y(v)} x2={maxX} y2={project.y(v)} />
        ),
      )}

      {/* Origen (0,0): la esquina desde la que se mide todo. Cual de las
          cuatro sea lo decide coords.js a partir de invert_x/invert_y. */}
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

      {/* El dibujo se sale del area: se remarca el limite en rojo. El aviso
          escrito lo pone el panel del rail; esto dice DONDE se sale. */}
      {!fits && (
        <rect className="plot-canvas__overflow" x={0} y={0} width={maxX} height={maxY} />
      )}
    </svg>
  )
}

export default memo(PlotCanvas)
