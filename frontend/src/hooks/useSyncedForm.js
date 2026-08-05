import { useCallback, useEffect, useRef, useState } from 'react'

// formularios sembrados UNA vez con el estado de la maquina, despues los maneja el usuario
//
// la siembra es unica, si no el polling de 1.5s te borraria lo que escribis

// un campo sembrado desde el estado de la maquina
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

  // para "Recargar valores" sin tener que remontar el componente
  const resync = useCallback(() => {
    if (disponible) setValue(String(external))
  }, [external, disponible])

  return [value, setValue, resync]
}

// formulario sembrado desde una fuente, normalmente status
// mapper se lee por ref, si va en las dependencias el efecto se dispara sin parar
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

  // vuelve a sembrar desde la maquina en el proximo render
  const reload = useCallback(() => setForm(null), [])

  return { form, set, setForm, reload }
}

export default useSyncedForm
