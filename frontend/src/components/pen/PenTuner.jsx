import { useState } from 'react'
import { api } from '../../api'
import { useStatus } from '../../StatusContext.jsx'
import { useSyncedValue } from '../../hooks/useSyncedForm.js'
import Button from '../ui/Button.jsx'
import Banner from '../ui/Banner.jsx'
import Field from '../ui/Field.jsx'
import Reveal from '../ui/Reveal.jsx'

// Ajuste fino de la pluma.
//
// El porta-pluma es la pieza mas delicada de la maquina: unos pocos pasos de
// mas rompen la hoja o hacen perder pasos al eje Z, y unos pocos de menos y no
// escribe. Hasta ahora esa presion se ajustaba con un Stepper de cinco en
// cinco, escondido en el paso 3 del asistente y sin forma de ver el resultado
// sin montar un dibujo entero.
//
// Las tres piezas que faltaban:
//   - resolucion de UN paso, con el deslizador para buscar a ojo y las teclas
//     para afinar,
//   - probar sin guardar (bajar, subir, y sobre todo TRAZAR: el ciclo de
//     prueba dice si el eje pierde pasos, no si el trazo sale marcado),
//   - guardar cuando ya esta bien.
//
// La unidad es el PASO, no el grado: el eje Z lo mueve un 28BYJ-48 contra la
// palanca del porta-pluma, y pen_steps es exactamente lo que el firmware
// guarda en PEN_N.
const FINOS = [-5, -1, 1, 5]

export default function PenTuner({ embedded = false }) {
  const { status, canOperate, busy, runAction, refreshConfig, penDown } = useStatus()
  // Sembrado UNA vez desde la maquina: con useState(status?.pen_steps) a secas,
  // montar antes del primer /api/status dejaba el campo clavado en el valor por
  // defecto y "Guardar" escribia ese, no el de la maquina.
  const [pasos, setPasos, resyncPasos] = useSyncedValue(status?.pen_steps, 100)
  const [linea, setLinea] = useState(null)
  const [guardado, setGuardado] = useState(false)

  const valor = Number(pasos)
  const valido = Number.isFinite(valor) && valor >= 1 && valor <= 255
  const bloqueado = !canOperate || busy
  const sinGuardar = valido && valor !== status?.pen_steps

  const ajustar = (delta) =>
    setPasos(String(Math.max(1, Math.min(255, (valido ? valor : 100) + delta))))

  async function guardar() {
    if (!valido) return
    try {
      await runAction(() => api.penConfig(valor))
      await refreshConfig()
      setGuardado(true)
    } catch {
      /* banner */
    }
  }

  async function probar(accion) {
    setGuardado(false)
    await runAction(() => api.pen(accion)).catch(() => {})
  }

  async function trazar() {
    try {
      setLinea(await runAction(() => api.penTestLine(20)))
    } catch {
      /* banner */
    }
  }

  async function fijarCero() {
    try {
      await runAction(api.zSetZero)
    } catch {
      /* banner */
    }
  }

  return (
    <div className="pen-tuner">
      {!embedded && (
        <p className="hint">
          Poné papel debajo y buscá la presión con la que el trazo sale marcado sin hundir la punta.
          Probar no guarda nada: el valor se aplica a la máquina cuando pulsás Guardar.
        </p>
      )}

      <Field
        label="Presión sobre el papel"
        hint="Cuántos pasos baja la pluma desde la altura de tránsito. Más pasos, más presión."
      >
        {(id) => (
          <div className="pen-tuner__slider">
            <input
              id={id}
              className="slider"
              type="range"
              min={1}
              max={255}
              step={1}
              value={valido ? valor : 100}
              onChange={(e) => setPasos(e.target.value)}
              aria-describedby={`${id}-valor`}
            />
            <output id={`${id}-valor`} className="pen-tuner__value tnum">
              {pasos}
              <span className="pen-tuner__unit">pasos</span>
            </output>
          </div>
        )}
      </Field>

      <div className="pen-tuner__fine">
        {FINOS.map((d) => (
          <Button key={d} variant="secondary" size="sm" onClick={() => ajustar(d)}>
            {d > 0 ? `+${d}` : d}
          </Button>
        ))}
        <Button
          variant={sinGuardar ? 'filled' : 'gray'}
          size="sm"
          disabled={bloqueado || !valido || !sinGuardar}
          onClick={guardar}
        >
          {sinGuardar ? 'Guardar presión' : 'Guardada'}
        </Button>
      </div>

      {sinGuardar && (
        <p className="hint field__warn">
          La máquina sigue con {status?.pen_steps ?? '—'} pasos. Guardá para probar con {valor}.
        </p>
      )}

      <div className="pen-tuner__tests">
        <Button
          variant="secondary"
          icon="pen-down"
          className={penDown ? 'btn--active' : ''}
          disabled={bloqueado}
          onClick={() => probar('down')}
        >
          Probar abajo
        </Button>
        <Button
          variant="secondary"
          icon="pen-up"
          className={penDown ? '' : 'btn--active'}
          disabled={bloqueado}
          onClick={() => probar('up')}
        >
          Probar arriba
        </Button>
        <Button variant="tinted" icon="ruler" disabled={bloqueado} onClick={trazar}>
          Dibujar línea de test
        </Button>
      </div>

      <Reveal when={linea} className="result-box">
        {(r) => (
          <div className="result-box__row">
            <span className="result-box__label">Línea trazada</span>
            <span>
              {r.length_mm?.toFixed?.(1) ?? r.length_mm} mm con {r.pen_steps} pasos de presión
            </span>
          </div>
        )}
      </Reveal>

      {guardado && (
        <Banner tone="success">
          Presión guardada: {status?.pen_steps} pasos. Ya podés dibujar.
        </Banner>
      )}

      <hr className="divider" />

      <h3 className="section-title">Altura de tránsito</h3>
      <p className="hint">
        Es el cero: la altura a la que la pluma viaja sin tocar el papel. Subila o bajala hasta que
        quede justo despegada y fijala.
      </p>
      <div className="pen-tuner__tests">
        <Button variant="secondary" size="sm" disabled={bloqueado} onClick={() => runAction(() => api.penJog(5)).catch(() => {})}>
          Subir 5
        </Button>
        <Button variant="secondary" size="sm" disabled={bloqueado} onClick={() => runAction(() => api.penJog(1)).catch(() => {})}>
          Subir 1
        </Button>
        <Button variant="secondary" size="sm" disabled={bloqueado} onClick={() => runAction(() => api.penJog(-1)).catch(() => {})}>
          Bajar 1
        </Button>
        <Button variant="secondary" size="sm" disabled={bloqueado} onClick={() => runAction(() => api.penJog(-5)).catch(() => {})}>
          Bajar 5
        </Button>
        <Button variant="tinted" icon="scope" disabled={bloqueado} onClick={fijarCero}>
          Fijar como cero
        </Button>
      </div>

      <Button variant="ghost" size="sm" onClick={resyncPasos}>
        Volver al valor de la máquina
      </Button>
    </div>
  )
}
