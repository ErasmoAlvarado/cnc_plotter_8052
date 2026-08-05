import { AnimatePresence, motion } from 'motion/react'
import { api } from '../api'
import { useStatus } from '../StatusContext.jsx'
import { fadeScale, spring, useMotionPrefs } from '../motion.js'
import { viewport } from '../coords.js'
import PlotCanvas from '../components/canvas/PlotCanvas.jsx'
import Button from '../components/ui/Button.jsx'

// el stage: el canvas ocupando todo el espacio que no usa el rail.
//
// sin archivo cargado no mostramos un hueco vacio con un icono, mostramos
// el area de trabajo real con el cabezal en su posicion real -- sirve para
// entender de un vistazo donde esta el (0,0) y para donde crecen los ejes
// incluso sin tener nada cargado
export default function Stage({ drawing }) {
  const { status, jobActive, penDown, startJob, reason } = useStatus()
  const { gcode, paths, playback, donePathCount, head, trail, penSteps } = drawing
  const { t } = useMotionPrefs()

  const runReason = reason('run')

  // con dibujo cargado usa el area de trabajo del gcode, sin dibujo la de la maquina
  const workArea = gcode?.work_area ?? {
    max_x_mm: status?.max_x_mm ?? 100,
    max_y_mm: status?.max_y_mm ?? 100,
  }

  const liveHead = head ?? {
    x: status?.position?.x_mm ?? 0,
    y: status?.position?.y_mm ?? 0,
    penDown,
  }

  // el marco toma la proporcion del area de trabajo para que el recuadro le
  // quede justo al dibujo. el aire de cada lado sale de coords.viewport(),
  // el mismo que usa PlotCanvas en su viewBox (antes estaba a mano en los dos lados)
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

        {/* leyenda y pista ocupan el mismo hueco, por eso el cruce con
            mode="wait" -- solapadas se verian como texto encimado */}
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
              // igual que la barra de abajo: .stage__hint se centra con
              // translateX(-50%) en css. aca solo animamos opacity asi que
              // motion ni toca el transform, pero lo declaro igual para que
              // si el dia de manana alguien agrega un `y` no se descentre
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

        {/* la barra flota apoyada en el borde inferior asi que entra desde
            abajo, viene de donde esta */}
        <AnimatePresence>
          {gcode && (
            <motion.div
              className="stage__toolbar"
              // x: '-50%' es el centrado (antes translateX en css), no un
              // gesto -- motion compone un solo transform asi que hay que
              // pasarselo completo en los 3 estados o se pierde
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
