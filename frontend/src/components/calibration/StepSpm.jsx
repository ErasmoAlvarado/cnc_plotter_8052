import { useState } from 'react'
import { api } from '../../api'
import { useStatus } from '../../StatusContext.jsx'
import Button from '../ui/Button.jsx'
import Field from '../ui/Field.jsx'
import Banner from '../ui/Banner.jsx'
import Reveal from '../ui/Reveal.jsx'
import SegmentedControl from '../ui/SegmentedControl.jsx'

// Paso 1: pasos por milimetro.
//
// Es el ajuste del que dependen todos los demas: si esta mal, el dibujo sale
// con el tamano equivocado por mucho que el resto este perfecto. Por eso es el
// primero del wizard y el que bloquea a los siguientes.
//
// X e Y se miden por SEPARADO. Antes se trazaba solo en X y el resultado se
// escribia en los dos ejes: en una maquina de cremallera y pinon, con dos
// mecanismos distintos, eso dejaba Y sistematicamente mal calibrado y el error
// no se veia hasta dibujar un circulo y encontrarse un ovalo.
const EJES = [
  { value: 'x', label: 'Eje X' },
  { value: 'y', label: 'Eje Y' },
]

export default function StepSpm({ onDone, done }) {
  const { canOperate, busy, runAction, refreshConfig, refreshStatus } = useStatus()
  const [eje, setEje] = useState('x')
  const [drawResult, setDrawResult] = useState(null)
  const [measured, setMeasured] = useState('')
  const [applied, setApplied] = useState({})

  const measuredNum = Number(measured)
  const measuredValid = measuredNum > 0 && measuredNum <= 1000
  const bloqueado = !canOperate || busy
  // El trazo vale para el eje con el que se hizo: cambiar de pestana no puede
  // dejar arrastrar una medida de X a la correccion de Y.
  const trazoDelEje = drawResult?.axis === eje ? drawResult : null

  async function drawLine() {
    try {
      setDrawResult(await runAction(() => api.calibrateDrawLine(eje)))
      setMeasured('')
    } catch {
      /* banner */
    }
  }

  async function apply() {
    try {
      const result = await runAction(() => api.calibrateApplySteps(measuredNum, eje))
      setApplied((prev) => ({ ...prev, [eje]: result }))
      setDrawResult(null)
      setMeasured('')
      await refreshConfig()
      await refreshStatus()
      // El paso se da por hecho cuando los DOS ejes estan medidos.
      if (eje === 'x' ? applied.y : applied.x) onDone()
    } catch {
      /* banner */
    }
  }

  const otro = eje === 'x' ? 'y' : 'x'

  return (
    <div className="wizard-body">
      <p className="hint">
        La máquina traza una línea recta de 30 mm. La medís con una regla y le decís cuánto midió de
        verdad: con eso se corrige la escala de ese eje.
      </p>

      <SegmentedControl label="Eje a calibrar" options={EJES} value={eje} onChange={setEje} />

      <ol className="steps-list">
        <li className="steps-list__item">
          <div className="steps-list__body">
            <span>
              Poné papel y bajá la pluma hasta que apoye. Después dibujá la línea en{' '}
              {eje.toUpperCase()}.
            </span>
            <div>
              <Button
                variant="tinted"
                icon="ruler"
                disabled={bloqueado}
                loading={busy}
                onClick={drawLine}
              >
                Dibujar línea de 30 mm en {eje.toUpperCase()}
              </Button>
            </div>
            <Reveal when={trazoDelEje} className="result-box">
              {(r) => (
                <>
                  <div className="result-box__row">
                    <span className="result-box__label">Objetivo</span>
                    <span>{r.target_mm} mm</span>
                  </div>
                  <div className="result-box__row">
                    <span className="result-box__label">Pasos enviados</span>
                    <span>{r.steps_sent}</span>
                  </div>
                  <div className="result-box__row">
                    <span className="result-box__label">Pasos/mm actuales</span>
                    <span>{Number(r.current_spm).toFixed(2)}</span>
                  </div>
                </>
              )}
            </Reveal>
          </div>
        </li>

        <li className="steps-list__item">
          <div className="steps-list__body">
            <span>Medí la línea con una regla y escribí el resultado.</span>
            <Field
              label="Medida real"
              hint="Con un decimal alcanza. Si mide 29,4 mm escribí 29.4"
              error={measured !== '' && !measuredValid ? 'Tiene que estar entre 0 y 1000 mm' : null}
            >
              {(id) => (
                <input
                  id={id}
                  className="field__input"
                  type="number"
                  inputMode="decimal"
                  min={0.1}
                  max={1000}
                  step={0.1}
                  value={measured}
                  placeholder="30.0"
                  onChange={(e) => setMeasured(e.target.value)}
                />
              )}
            </Field>
            <div>
              <Button
                variant="filled"
                disabled={bloqueado || !measuredValid || !trazoDelEje}
                onClick={apply}
              >
                Aplicar corrección a {eje.toUpperCase()}
              </Button>
            </div>
            {!trazoDelEje && (
              <p className="hint">
                Primero hay que dibujar la línea de referencia en {eje.toUpperCase()}.
              </p>
            )}
          </div>
        </li>
      </ol>

      {applied[eje] && (
        <Banner
          tone={Math.abs(applied[eje].error_pct) > 5 ? 'warn' : 'success'}
          title={`Escala de ${eje.toUpperCase()} corregida`}
        >
          Pasos/mm: {applied[eje].old_spm} → {applied[eje].new_spm}. Error medido:{' '}
          {applied[eje].error_mm} mm ({applied[eje].error_pct} %). La máquina volvió al origen.
        </Banner>
      )}

      {applied[eje] && !applied[otro] && (
        <Banner tone="info">
          Falta el eje {otro.toUpperCase()}. Cambiá de pestaña y repetí la medición: los dos
          mecanismos son distintos y casi nunca dan el mismo número.
        </Banner>
      )}

      {done && !applied.x && !applied.y && (
        <Banner tone="success">Este paso ya está hecho en esta sesión.</Banner>
      )}
    </div>
  )
}
