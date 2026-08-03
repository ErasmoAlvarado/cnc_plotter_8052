import { useEffect, useState } from 'react'
import { api } from '../../api'
import { useStatus } from '../../StatusContext.jsx'
import Button from '../ui/Button.jsx'
import Field from '../ui/Field.jsx'
import Stepper from '../ui/Stepper.jsx'
import DisabledHint from '../ui/DisabledHint.jsx'

// Velocidades en milisegundos entre medios pasos: numero mas bajo = mas rapido.
//
// El eje Z tiene la suya propia y con un minimo mas alto (4 ms) porque es el
// unico que trabaja contra la gravedad cargando el peso de la pluma: por debajo
// de eso el 28BYJ-48 pierde par y se traba a mitad de recorrido.
export default function SpeedSection() {
  const { status, canOperate, runAction, reason } = useStatus()
  const [form, setForm] = useState(null)

  // El formulario se inicializa una vez y despues es local: si se refrescara en
  // cada polling, el valor se sobrescribiria mientras el usuario lo escribe.
  useEffect(() => {
    if (!form && status) {
      setForm({
        draw: String(status.speed_draw ?? 5),
        rapid: String(status.speed_rapid ?? 6),
        z: String(status.speed_z ?? 8),
      })
    }
  }, [status, form])

  if (!form) return null

  const set = (key) => (value) => setForm((prev) => ({ ...prev, [key]: value }))
  const valid =
    Number(form.draw) >= 2 && Number(form.rapid) >= 2 && Number(form.z) >= 4

  return (
    <DisabledHint reason={reason('config')}>
      <Field label="Dibujando (X/Y)" hint="Más lento da trazos más limpios">
        {(id) => (
          <Stepper id={id} value={form.draw} onChange={set('draw')} min={2} max={255} suffix="ms" />
        )}
      </Field>

      <Field label="Movimiento rápido (X/Y)" hint="Con la pluma arriba, entre trazo y trazo">
        {(id) => (
          <Stepper id={id} value={form.rapid} onChange={set('rapid')} min={2} max={255} suffix="ms" />
        )}
      </Field>

      <Field
        label="Eje Z (pluma)"
        hint="Nunca por debajo de 4 ms: el motor pelea contra la gravedad y pierde pasos"
      >
        {(id) => <Stepper id={id} value={form.z} onChange={set('z')} min={4} max={255} suffix="ms" />}
      </Field>

      <div className="row">
        <Button
          variant="filled"
          disabled={!canOperate || !valid}
          onClick={() =>
            runAction(() =>
              api.speed({ draw: Number(form.draw), rapid: Number(form.rapid), z: Number(form.z) }),
            ).catch(() => {})
          }
        >
          Guardar velocidades
        </Button>
        <Button
          variant="gray"
          onClick={() =>
            setForm({
              draw: String(status.speed_draw),
              rapid: String(status.speed_rapid),
              z: String(status.speed_z),
            })
          }
        >
          Descartar cambios
        </Button>
      </div>
    </DisabledHint>
  )
}
