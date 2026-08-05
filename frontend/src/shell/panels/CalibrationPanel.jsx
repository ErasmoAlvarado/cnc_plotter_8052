import { useStatus } from '../../StatusContext.jsx'
import Button from '../../components/ui/Button.jsx'

// el backend guarda la fecha como "YYYY-MM-DD HH:MM" en hora local, hace
// falta el guion de ISO para que safari la parsee bien
function parseDate(value) {
  if (!value) return null
  const d = new Date(value.replace(' ', 'T'))
  return Number.isNaN(d.getTime()) ? null : d
}

function relativeTime(date) {
  const minutes = Math.round((Date.now() - date.getTime()) / 60000)
  if (minutes < 2) return 'hace un momento'
  if (minutes < 60) return `hace ${minutes} minutos`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `hace ${hours} hora${hours === 1 ? '' : 's'}`
  const days = Math.round(hours / 24)
  if (days < 30) return `hace ${days} día${days === 1 ? '' : 's'}`
  const months = Math.round(days / 30)
  return `hace ${months} mes${months === 1 ? '' : 'es'}`
}

// atajo al wizard con el estado a la vista. para alguien que estrena la
// maquina "nunca calibrado" es la instruccion de que hacer primero, para
// el resto es solo una fecha que confirma que no hace falta tocar nada.
//
// sin calibrar es un aviso, no una averia, por eso va en ambar sin fondo.
// el rojo se guarda para lo que se rompio recien
export default function CalibrationPanel({ onOpen }) {
  const { config, status } = useStatus()
  const date = parseDate(config?.last_calibration_date)
  const never = !!config && !date

  const spm = status?.steps_per_mm?.x ?? config?.steps_per_mm_x
  const backlash = status?.backlash ?? { x: config?.backlash_x, y: config?.backlash_y }

  return (
    <>
      <div className={`calib ${never ? 'calib--never' : ''}`.trim()}>
        <span className="calib__dot" />
        <div className="calib__text">
          <p className="calib__state">
            {!config ? 'Comprobando…' : never ? 'Nunca calibrado' : `Calibrado ${relativeTime(date)}`}
          </p>
          <p className="calib__detail tnum">
            {never
              ? 'El dibujo va a salir con el tamaño equivocado.'
              : `${Number(spm ?? 0).toFixed(2)} pasos/mm · juego ${backlash?.x ?? 0}/${backlash?.y ?? 0}`}
          </p>
        </div>
      </div>

      <Button variant={never ? 'primary' : 'secondary'} size="md" block icon="wand" onClick={onOpen}>
        {never ? 'Calibrar ahora' : 'Volver a calibrar'}
      </Button>
    </>
  )
}
