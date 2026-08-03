import { useCallback, useEffect, useRef, useState } from 'react'

// Formularios que se siembran con el estado de la maquina UNA vez y a partir de
// ahi los manda el usuario.
//
// ─────────────────────────────────────────────────────────────────────
// EL BUG QUE ESTO ARREGLA
// ─────────────────────────────────────────────────────────────────────
// Varios campos se inicializaban asi:
//
//     const [penSteps, setPenSteps] = useState(String(status?.pen_steps ?? 100))
//
// `status` llega del primer /api/status, que tarda. Si el componente se monta
// antes —y el paso 3 del asistente se monta antes— el campo se quedaba clavado
// en el valor por defecto y NUNCA se sincronizaba. El usuario veia "100",
// pulsaba Guardar convencido de no haber tocado nada, y le escribia 100 a una
// maquina configurada con 70. Con la profundidad de la pluma, eso es clavar la
// punta contra el papel.
//
// El patron correcto ya existia en SettingsSection ("sembrar solo si aun no hay
// formulario"); aqui se extrae para que no haya que acordarse de repetirlo.
//
// La siembra ocurre una sola vez a proposito: si se re-sincronizara con cada
// /api/status, el sondeo de 1,5 s borraria lo que el usuario esta escribiendo.

/** Un solo campo sembrado desde el estado de la maquina. */
export function useSyncedValue(external, fallback = '') {
  const disponible = external !== undefined && external !== null
  const [value, setValue] = useState(() => String(disponible ? external : fallback))
  const sembrado = useRef(disponible)

  useEffect(() => {
    if (!sembrado.current && disponible) {
      sembrado.current = true
      setValue(String(external))
    }
  }, [external, disponible])

  // Permite volver a leer de la maquina ("Recargar valores") sin remontar.
  const resync = useCallback(() => {
    if (disponible) setValue(String(external))
  }, [external, disponible])

  return [value, setValue, resync]
}

/**
 * Formulario completo sembrado desde una fuente (normalmente `status`).
 *
 * `mapper` se lee por referencia y no entra en las dependencias: casi siempre
 * es un literal creado en cada render, y meterlo en el efecto lo dispararia
 * sin parar.
 */
export function useSyncedForm(source, mapper) {
  const [form, setForm] = useState(null)
  const mapperRef = useRef(mapper)
  mapperRef.current = mapper

  useEffect(() => {
    if (form === null && source !== null && source !== undefined) {
      setForm(mapperRef.current(source))
    }
  }, [source, form])

  const set = useCallback(
    (key) => (value) => setForm((prev) => ({ ...prev, [key]: value })),
    [],
  )

  // Vuelve a sembrar desde la maquina en el proximo render.
  const reload = useCallback(() => setForm(null), [])

  return { form, set, setForm, reload }
}

export default useSyncedForm
