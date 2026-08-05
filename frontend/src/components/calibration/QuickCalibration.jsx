import { useState } from 'react'
import { api } from '../../api'
import { useStatus } from '../../StatusContext.jsx'
import { useSyncedForm } from '../../hooks/useSyncedForm.js'
import { originLabel } from '../../coords.js'
import Button from '../ui/Button.jsx'
import Field from '../ui/Field.jsx'
import Toggle from '../ui/Toggle.jsx'
import Banner from '../ui/Banner.jsx'
import Reveal from '../ui/Reveal.jsx'
import Stepper from '../ui/Stepper.jsx'

// para el dia a dia, cada parametro se edita y guarda por separado sin el wizard entero
//
// cada bloque guarda lo suyo nomas, guardar la escala no debe pisar el backlash
export default function QuickCalibration() {
  const { status, canOperate, busy, runAction, refreshConfig, refreshStatus } = useStatus()
  const [medida, setMedida] = useState({ x: '', y: '' })
  const [trazado, setTrazado] = useState(null)
  const [aplicado, setAplicado] = useState(null)

  const { form, set, reload } = useSyncedForm(status, (st) => ({
    steps_per_mm_x: String(st.steps_per_mm?.x ?? 170.67),
    steps_per_mm_y: String(st.steps_per_mm?.y ?? 170.67),
    steps_per_mm_z: String(st.steps_per_mm?.z ?? 100),
    backlash_x: String(st.backlash?.x ?? 0),
    backlash_y: String(st.backlash?.y ?? 0),
    max_x_mm: String(st.max_x_mm ?? 40),
    max_y_mm: String(st.max_y_mm ?? 40),
    invert_x: !!st.invert_x,
    invert_y: !!st.invert_y,
  }))

  if (!form) return null

  // /api/settings recibe el bloque entero, los campos sin editar viajan con su valor viejo
  const guardar = async (parciales) => {
    await runAction(() =>
      api.settings({
        steps_per_mm_x: Number(form.steps_per_mm_x),
        steps_per_mm_y: Number(form.steps_per_mm_y),
        steps_per_mm_z: Number(form.steps_per_mm_z),
        backlash_x: Number(form.backlash_x),
        backlash_y: Number(form.backlash_y),
        max_x_mm: Number(form.max_x_mm),
        max_y_mm: Number(form.max_y_mm),
        invert_x: form.invert_x,
        invert_y: form.invert_y,
        ...parciales,
      }),
    ).catch(() => {})
    await refreshConfig()
  }

  async function medir(eje) {
    try {
      setTrazado(await runAction(() => api.calibrateDrawLine(eje)))
    } catch {
      /* banner */
    }
  }

  async function aplicar(eje) {
    const valor = Number(medida[eje])
    if (!(valor > 0)) return
    try {
      const r = await runAction(() => api.calibrateApplySteps(valor, eje))
      setAplicado(r)
      setMedida((prev) => ({ ...prev, [eje]: '' }))
      setTrazado(null)
      await refreshConfig()
      await refreshStatus()
      reload()          // vuelve a leer el valor recien calculado
    } catch {
      /* banner */
    }
  }

  const bloqueado = !canOperate || busy

  const ejeSpm = (eje) => (
    <div className="quick-cal__axis" key={eje}>
      <Field label={`Pasos por mm en ${eje.toUpperCase()}`}>
        {(id) => (
          <input
            id={id}
            className="field__input"
            type="number"
            inputMode="decimal"
            step="0.01"
            min="0.01"
            value={form[`steps_per_mm_${eje}`]}
            onChange={(e) => set(`steps_per_mm_${eje}`)(e.target.value)}
          />
        )}
      </Field>
      <div className="row">
        <Button variant="gray" disabled={bloqueado} loading={busy} onClick={() => guardar({})}>
          Guardar
        </Button>
        <Button variant="tinted" icon="ruler" disabled={bloqueado} onClick={() => medir(eje)}>
          Medir {eje.toUpperCase()}
        </Button>
      </div>
      {trazado?.axis === eje && (
        <div className="row">
          <Field label="¿Cuánto midió?" hint={`Se trazaron ${trazado.target_mm} mm`}>
            {(id) => (
              <input
                id={id}
                className="field__input"
                type="number"
                inputMode="decimal"
                step="0.1"
                placeholder={String(trazado.target_mm)}
                value={medida[eje]}
                onChange={(e) => setMedida((p) => ({ ...p, [eje]: e.target.value }))}
              />
            )}
          </Field>
          <Button
            variant="filled"
            disabled={bloqueado || !(Number(medida[eje]) > 0)}
            onClick={() => aplicar(eje)}
          >
            Corregir
          </Button>
        </div>
      )}
    </div>
  )

  return (
    <div className="quick-cal">
      <p className="hint">
        Cada ajuste se guarda por separado. Para estrenar la máquina o si algo se descalibró del
        todo, usá el asistente.
      </p>

      <section className="quick-cal__block">
        <h3 className="section-title">Escala</h3>
        <p className="hint">
          X e Y se miden por separado: son dos mecanismos distintos y usar la medida de uno para el
          otro deja siempre un eje mal.
        </p>
        <div className="quick-cal__axes">{['x', 'y'].map(ejeSpm)}</div>
        <Reveal when={aplicado} className="result-box">
          {(r) => (
            <div className="result-box__row">
              <span className="result-box__label">Eje {r.axis?.toUpperCase()}</span>
              <span>
                {r.old_spm} → {r.new_spm} pasos/mm ({r.error_pct} % de error)
              </span>
            </div>
          )}
        </Reveal>
      </section>

      <hr className="divider" />

      <section className="quick-cal__block">
        <h3 className="section-title">Juego mecánico</h3>
        <div className="row">
          <Stepper value={form.backlash_x} onChange={set('backlash_x')} min={0} max={255} suffix="X" aria-label="Juego en X" />
          <Stepper value={form.backlash_y} onChange={set('backlash_y')} min={0} max={255} suffix="Y" aria-label="Juego en Y" />
          <Button variant="gray" disabled={bloqueado} onClick={() => guardar({})}>
            Guardar
          </Button>
        </div>
      </section>

      <hr className="divider" />

      <section className="quick-cal__block">
        <h3 className="section-title">Área de trabajo</h3>
        <p className="hint">
          Es lo que decide si un dibujo cabe. Pasarse de acá no da un aviso: la máquina llega al
          tope, pierde pasos y hay que recalibrar.
        </p>
        <div className="row">
          <Stepper value={form.max_x_mm} onChange={set('max_x_mm')} min={1} max={1000} step={5} suffix="mm X" aria-label="Ancho del área" />
          <Stepper value={form.max_y_mm} onChange={set('max_y_mm')} min={1} max={1000} step={5} suffix="mm Y" aria-label="Alto del área" />
          <Button variant="gray" disabled={busy} onClick={() => guardar({})}>
            Guardar
          </Button>
        </div>
      </section>

      <hr className="divider" />

      <section className="quick-cal__block">
        <h3 className="section-title">Perspectiva</h3>
        <p className="hint">
          Dónde ves vos el (0,0) de la máquina. Ajustalo hasta que el punto del lienzo coincida con
          la esquina real y las flechas muevan el cabezal hacia donde apuntan.
        </p>
        <Toggle
          id="quick-invert-y"
          checked={form.invert_y}
          onChange={set('invert_y')}
          label="El origen está arriba (Y crece hacia abajo)"
        />
        <Toggle
          id="quick-invert-x"
          checked={form.invert_x}
          onChange={set('invert_x')}
          label="El origen está a la derecha (X crece hacia la izquierda)"
        />
        <Banner tone="info">
          Origen en la {originLabel({ invertX: form.invert_x, invertY: form.invert_y })}.
        </Banner>
        <div>
          <Button variant="gray" disabled={busy} onClick={() => guardar({})}>
            Guardar perspectiva
          </Button>
        </div>
      </section>
    </div>
  )
}
