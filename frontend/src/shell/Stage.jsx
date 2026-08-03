import { AnimatePresence, motion } from 'motion/react'
import { api } from '../api'
import { useStatus } from '../StatusContext.jsx'
import { fadeScale, spring, useMotionPrefs } from '../motion.js'
import { viewport } from '../coords.js'
import PlotCanvas from '../components/canvas/PlotCanvas.jsx'
import Button from '../components/ui/Button.jsx'

// El escenario: el lienzo ocupando todo el espacio que no usa el rail.
//
// Sin archivo cargado NO se muestra un hueco vacio con un icono. Se muestra el
// area de trabajo de la maquina con el cabezal en su posicion real — que es
// informacion util incluso antes de tener un dibujo, y ademas es la unica forma
// de que el usuario entienda de un vistazo donde esta el (0,0) y hacia donde
// crecen los ejes.
export default function Stage({ drawing }) {
  const { status, jobActive, penDown, startJob, reason } = useStatus()
  const { gcode, paths, playback, donePathCount, head, trail, penSteps } = drawing
  const { t } = useMotionPrefs()

  const runReason = reason('run')

  // Con dibujo cargado manda su area de trabajo; sin dibujo, la de la maquina.
  const workArea = gcode?.work_area ?? {
    max_x_mm: status?.max_x_mm ?? 100,
    max_y_mm: status?.max_y_mm ?? 100,
  }

  const liveHead = head ?? {
    x: status?.position?.x_mm ?? 0,
    y: status?.position?.y_mm ?? 0,
    penDown,
  }

  // El marco toma la proporcion del area de trabajo para que el recuadro abrace
  // el dibujo. El aire de cada lado sale de coords.viewport(), el mismo que usa
  // PlotCanvas en su viewBox: antes estaba escrito a mano en los dos sitios.
  const { ratio } = viewport({ maxX: workArea.max_x_mm, maxY: workArea.max_y_mm })

  return (
    <main className="stage">
      <div className="stage__frame" style={{ '--ratio': ratio }}>
        <PlotCanvas
          paths={paths}
          workArea={workArea}
          bounds={gcode?.bounds}
          donePathCount={donePathCount}
          head={liveHead}
          trail={trail}
          penSteps={penSteps}
          fits={gcode ? gcode.fits_in_area : true}
          pulsing={jobActive}
          invertX={!!status?.invert_x}
          invertY={!!status?.invert_y}
          className="stage__canvas"
        />

        <AnimatePresence>
          {jobActive && (
            <motion.span className="stage__badge" {...fadeScale} transition={t(spring.snappy)}>
              <span className="stage__badge-dot" />
              Dibujando
            </motion.span>
          )}
        </AnimatePresence>

        {/* La leyenda y la pista ocupan el mismo hueco, asi que se cruzan con
            `mode="wait"`: solapadas se leerian como dos textos encimados. */}
        <AnimatePresence mode="wait" initial={false}>
          {gcode ? (
            <motion.div
              key="legend"
              className="stage__legend"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={t(spring.gentle)}
            >
              <span className="legend__item">
                <span className="legend__swatch legend__swatch--done" /> dibujado
              </span>
              <span className="legend__item">
                <span className="legend__swatch" /> pendiente
              </span>
              <span className="legend__item">
                <span className="legend__swatch legend__swatch--rapid" /> sin dibujar
              </span>
            </motion.div>
          ) : (
            <motion.div
              key="hint"
              className="stage__hint"
              // Igual que la barra: .stage__hint se centra con translateX(-50%)
              // en CSS. Aca solo se anima la opacidad, asi que motion no llegaria
              // a tocar el transform — pero se declara igual para que anadir
              // manana un `y` no descentre el bloque sin avisar.
              initial={{ opacity: 0, x: '-50%' }}
              animate={{ opacity: 1, x: '-50%' }}
              exit={{ opacity: 0, x: '-50%' }}
              transition={t(spring.gentle)}
            >
              <p className="stage__hint-title">Área de trabajo vacía</p>
              <p className="hint">
                Cargá un G-code desde el panel de la izquierda, o dibujá un patrón de prueba.
              </p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* La barra flota sobre el lienzo apoyada en el borde inferior, asi que
            entra desde abajo: viene de donde esta, no de la nada. */}
        <AnimatePresence>
          {gcode && (
            <motion.div
              className="stage__toolbar"
              // El x: '-50%' es el centrado (antes translateX en CSS), no un
              // gesto: motion compone un solo transform y hay que darselo todo
              // aca o se pierde. Va en los tres estados a proposito.
              initial={{ opacity: 0, x: '-50%', y: 8 }}
              animate={{ opacity: 1, x: '-50%', y: 0 }}
              exit={{ opacity: 0, x: '-50%', y: 8 }}
              transition={t(spring.smooth)}
            >
              <Button
                variant="primary"
                size="lg"
                icon="play"
                disabled={!!runReason}
                title={runReason ?? undefined}
                onClick={() => startJob(api.run).catch(() => {})}
              >
                Ejecutar
              </Button>
              <Button
                variant="secondary"
                size="lg"
                icon={playback.playing ? 'stop-circle' : 'wand'}
                disabled={jobActive}
                onClick={playback.playing ? playback.stop : playback.start}
              >
                {playback.playing ? 'Parar' : 'Simular'}
              </Button>
              {runReason && <span className="stage__toolbar-reason">{runReason}</span>}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </main>
  )
}
