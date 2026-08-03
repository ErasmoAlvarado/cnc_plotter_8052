import { useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { useStatus } from '../../StatusContext.jsx'
import { fadeUp, spring, useMotionPrefs } from '../../motion.js'
import Icon from '../../components/ui/Icon.jsx'
import Button from '../../components/ui/Button.jsx'
import Banner from '../../components/ui/Banner.jsx'
import Toggle from '../../components/ui/Toggle.jsx'

// Mitad "rail" de la vista del dibujo: cargar el archivo y leer lo que trae.
// La otra mitad —el lienzo y los botones de ejecucion— vive en el escenario,
// porque es lo que se mira, no lo que se toca.
//
// El estado lo pone useDrawing (shell/useDrawing.js), que es comun a las dos
// mitades.
export default function DrawingPanel({ drawing }) {
  const { status, busy } = useStatus()
  const { gcode, upload, uploading, flipY, fitted, applyTransform } = drawing
  const [over, setOver] = useState(false)
  const inputRef = useRef(null)
  const { t } = useMotionPrefs()

  function onDrop(e) {
    e.preventDefault()
    setOver(false)
    upload(e.dataTransfer.files?.[0])
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept=".gcode,.nc,.txt"
        style={{ display: 'none' }}
        onChange={(e) => upload(e.target.files?.[0])}
      />

      {/* Cargar un archivo sustituye la zona de soltado por su ficha. Es el
          cambio mas grande que hace el panel, y de golpe se lee como si algo se
          hubiera roto y redibujado. */}
      <AnimatePresence mode="wait" initial={false}>
        {!gcode ? (
          <motion.div
            key="dropzone"
            className={`dropzone ${over ? 'dropzone--over' : ''}`.trim()}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault()
              setOver(true)
            }}
            onDragLeave={() => setOver(false)}
            onDrop={onDrop}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === 'Enter' && inputRef.current?.click()}
            {...fadeUp}
            // Al arrastrar un archivo encima crece lo justo para acusar recibo.
            // El borde ya cambia de color (shell.css); esto es para el rabillo
            // del ojo, que es donde esta la atencion mientras se arrastra.
            animate={{ opacity: 1, y: 0, scale: over ? 1.015 : 1 }}
            transition={t(spring.smooth)}
          >
            <Icon name="upload" size={20} />
            <p className="dropzone__title">
              {uploading ? 'Leyendo el archivo…' : 'Soltá tu G-code acá'}
            </p>
            <p className="hint">.gcode · .nc · .txt</p>
          </motion.div>
        ) : (
          <motion.div key="file" className="stack" {...fadeUp} transition={t(spring.smooth)}>
            <div className="file">
              <Icon name="doc" size={15} />
              <div className="file__text">
                <p className="file__name">{gcode.filename}</p>
                <p className="file__meta tnum">
                  {gcode.total_lines} líneas · {gcode.bounds?.max_x?.toFixed(1)} ×{' '}
                  {gcode.bounds?.max_y?.toFixed(1)} mm
                </p>
              </div>
              <span className={`tag ${gcode.fits_in_area ? 'tag--ok' : 'tag--bad'}`}>
                {gcode.fits_in_area ? 'cabe' : 'no cabe'}
              </span>
            </div>

            {/* Voltear Y es por archivo y no un ajuste de la maquina: depende
                de con que se exporto el G-code. El estandar asume Y hacia
                arriba y esta maquina tiene el origen arriba, asi que un
                fichero de CAM normal sale del reves. El lienzo repinta el
                resultado en cuanto se marca, antes de dibujar nada. */}
            <Toggle
              id="gcode-flip-y"
              checked={flipY}
              disabled={busy}
              onChange={(v) => applyTransform({ flipY: v })}
              label="Voltear en Y"
            />
            <p className="hint">
              Marcalo si el dibujo aparece espejado de arriba abajo respecto a como lo diseñaste.
            </p>

            {!gcode.fits_in_area && (
              <Banner tone="error" title="El dibujo se sale del área">
                Parte del trazado queda fuera de los {status?.max_x_mm ?? '—'} ×{' '}
                {status?.max_y_mm ?? '—'} mm de la máquina. No se puede ejecutar así: la máquina no
                tiene finales de carrera y llegaría al tope perdiendo pasos.
                <div className="stack stack--tight">
                  <Button
                    variant="filled"
                    size="sm"
                    icon="wand"
                    disabled={busy}
                    loading={busy}
                    onClick={() => applyTransform({ fit: true })}
                  >
                    Ajustar al área
                  </Button>
                </div>
              </Banner>
            )}

            {fitted && gcode.fits_in_area && (
              <Banner tone="info">
                Dibujo escalado al {Math.round((gcode.transform?.scale ?? 1) * 100)} % para que
                entre en el área.{' '}
                <button
                  type="button"
                  className="linkish"
                  disabled={busy}
                  onClick={() => applyTransform({ fit: false })}
                >
                  Volver al tamaño original
                </button>
              </Banner>
            )}

            {gcode.preview_truncated && (
              <p className="hint">
                La vista previa se recortó porque el archivo es muy grande. El dibujo se ejecuta
                completo igual.
              </p>
            )}

            <Button
              variant="ghost"
              size="sm"
              icon="upload"
              block
              onClick={() => inputRef.current?.click()}
            >
              Cambiar archivo
            </Button>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}
