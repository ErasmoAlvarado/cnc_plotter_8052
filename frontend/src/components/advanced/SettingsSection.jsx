import { api } from '../../api'
import { useStatus } from '../../StatusContext.jsx'
import { useSyncedForm } from '../../hooks/useSyncedForm.js'
import { originLabel } from '../../coords.js'
import Button from '../ui/Button.jsx'
import Field from '../ui/Field.jsx'
import Toggle from '../ui/Toggle.jsx'
import Banner from '../ui/Banner.jsx'
import DisabledHint from '../ui/DisabledHint.jsx'

function NumberInput({ id, value, onChange, ...rest }) {
  return (
    <input
      id={id}
      className="field__input"
      type="number"
      inputMode="decimal"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      {...rest}
    />
  )
}

// Ajustes tecnicos. Casi nadie los toca a mano — la calibracion guiada escribe
// los mismos valores — pero tienen que ser accesibles y editables para quien
// sabe lo que hace o quiere copiar la configuracion de otra maquina.
export default function SettingsSection() {
  const { status, config, busy, runAction, refreshConfig, reason } = useStatus()

  // El formulario se siembra desde la maquina una sola vez y a partir de ahi
  // manda el usuario; el sondeo de 1,5 s no puede pisar lo que se esta
  // escribiendo. "Recargar valores" vuelve a leer de la maquina — que es lo que
  // hace falta despues de calibrar, porque si no la seccion sigue mostrando los
  // pasos/mm viejos.
  const { form, set, reload } = useSyncedForm(status, (st) => ({
    steps_per_mm_x: String(st.steps_per_mm?.x ?? 170.67),
    steps_per_mm_y: String(st.steps_per_mm?.y ?? 170.67),
    steps_per_mm_z: String(st.steps_per_mm?.z ?? config?.steps_per_mm_z ?? 100),
    backlash_x: String(st.backlash?.x ?? 0),
    backlash_y: String(st.backlash?.y ?? 0),
    max_x_mm: String(st.max_x_mm ?? 40),
    max_y_mm: String(st.max_y_mm ?? 40),
    z_pen_down_threshold: String(st.z_pen_down_threshold ?? 0),
    enforce_soft_limits: !!st.enforce_soft_limits,
    invert_x: !!st.invert_x,
    invert_y: !!st.invert_y,
  }))

  if (!form) return null

  async function save() {
    await runAction(() =>
      api.settings({
        steps_per_mm_x: Number(form.steps_per_mm_x),
        steps_per_mm_y: Number(form.steps_per_mm_y),
        steps_per_mm_z: Number(form.steps_per_mm_z),
        backlash_x: Number(form.backlash_x),
        backlash_y: Number(form.backlash_y),
        max_x_mm: Number(form.max_x_mm),
        max_y_mm: Number(form.max_y_mm),
        z_pen_down_threshold: Number(form.z_pen_down_threshold),
        enforce_soft_limits: form.enforce_soft_limits,
        invert_x: form.invert_x,
        invert_y: form.invert_y,
      }),
    ).catch(() => {})
    await refreshConfig()
  }

  return (
    <DisabledHint reason={reason('config')}>
      <Field label="Pasos por mm en X" hint="Lo calcula solo el asistente de calibración">
        {(id) => <NumberInput id={id} value={form.steps_per_mm_x} onChange={set('steps_per_mm_x')} step="0.01" min="0.01" />}
      </Field>
      <Field label="Pasos por mm en Y">
        {(id) => <NumberInput id={id} value={form.steps_per_mm_y} onChange={set('steps_per_mm_y')} step="0.01" min="0.01" />}
      </Field>
      <Field label="Pasos por mm en Z" hint="El mecanismo del eje Z casi nunca tiene la misma escala que X/Y">
        {(id) => <NumberInput id={id} value={form.steps_per_mm_z} onChange={set('steps_per_mm_z')} step="0.01" min="0.01" />}
      </Field>

      <div className="row">
        <Field label="Juego en X (pasos)">
          {(id) => <NumberInput id={id} value={form.backlash_x} onChange={set('backlash_x')} min="0" max="255" />}
        </Field>
        <Field label="Juego en Y (pasos)">
          {(id) => <NumberInput id={id} value={form.backlash_y} onChange={set('backlash_y')} min="0" max="255" />}
        </Field>
      </div>

      <div className="row">
        <Field label="Ancho del área (mm)">
          {(id) => <NumberInput id={id} value={form.max_x_mm} onChange={set('max_x_mm')} min="1" max="1000" step="0.5" />}
        </Field>
        <Field label="Alto del área (mm)">
          {(id) => <NumberInput id={id} value={form.max_y_mm} onChange={set('max_y_mm')} min="1" max="1000" step="0.5" />}
        </Field>
      </div>

      <Field
        label="Umbral de pluma abajo (Z del G-code)"
        hint="Una línea con Z menor o igual que este valor se dibuja con la pluma abajo. Muchos programas exportan Z0 para dibujar."
      >
        {(id) => (
          <NumberInput
            id={id}
            value={form.z_pen_down_threshold}
            onChange={set('z_pen_down_threshold')}
            step="0.1"
          />
        )}
      </Field>

      <Toggle
        id="soft-limits"
        checked={form.enforce_soft_limits}
        onChange={set('enforce_soft_limits')}
        label="Bloquear los trabajos que se salen del área"
      />
      <p className="hint">
        La máquina no tiene finales de carrera: si el carro llega al tope pierde pasos y hay que
        recalibrar. Desactivalo sólo si sabés lo que hacés.
      </p>

      <hr className="divider" />

      {/* Perspectiva. No toca la cinemática: los milímetros siguen viviendo en
          [0, max] y los pasos siguen siendo positivos. Lo único que cambia es
          en qué esquina se pinta el (0,0) y hacia dónde mueve cada flecha. */}
      <h3 className="section-title">Perspectiva de la máquina</h3>
      <Toggle
        id="invert-y"
        checked={form.invert_y}
        onChange={set('invert_y')}
        label="El origen está arriba (Y crece hacia abajo)"
      />
      <Toggle
        id="invert-x"
        checked={form.invert_x}
        onChange={set('invert_x')}
        label="El origen está a la derecha (X crece hacia la izquierda)"
      />
      <Banner tone="info">
        El (0,0) se dibuja en la {originLabel({ invertX: form.invert_x, invertY: form.invert_y })}{' '}
        del lienzo, y las flechas del mando mueven el cabezal hacia donde apuntan.
      </Banner>

      <div className="row">
        <Button variant="filled" disabled={busy} onClick={save}>
          Guardar ajustes
        </Button>
        <Button variant="gray" onClick={reload}>
          Recargar valores
        </Button>
      </div>
    </DisabledHint>
  )
}
