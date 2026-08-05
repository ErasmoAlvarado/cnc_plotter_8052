import { useCallback, useEffect, useState } from 'react'

const KEY = 'cnc.theme'

// tema: 'system' (lo que diga el so) | 'light' | 'dark'.
//
// el atributo data-theme del <html> solo fija color-scheme, la paleta
// entera la resuelve light-dark() en tokens.css. sin atributo manda el so
export function useTheme() {
  const [theme, setThemeState] = useState(() => localStorage.getItem(KEY) ?? 'system')

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', theme)
    localStorage.setItem(KEY, theme)
  }, [theme])

  // el boton cicla entre 2 posiciones (claro/oscuro) partiendo de lo que
  // muestra el sistema ahora, nadie espera un tercer click para volver a
  // "automatico" -- el que quiera eso cambia el tema del so directamente
  const toggle = useCallback(() => {
    setThemeState((prev) => {
      if (prev === 'system') {
        const dark = window.matchMedia('(prefers-color-scheme: dark)').matches
        return dark ? 'light' : 'dark'
      }
      return prev === 'dark' ? 'light' : 'dark'
    })
  }, [])

  // en modo 'system' hay que escuchar el cambio del so, no solo leerlo una
  // vez -- si no, cambiar el tema del sistema repinta la app (via la media
  // query css) pero el icono del boton queda mostrando el tema viejo
  const [systemDark, setSystemDark] = useState(
    () => window.matchMedia('(prefers-color-scheme: dark)').matches,
  )

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = (e) => setSystemDark(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  const isDark = theme === 'dark' || (theme === 'system' && systemDark)

  return { theme, isDark, setTheme: setThemeState, toggle }
}
