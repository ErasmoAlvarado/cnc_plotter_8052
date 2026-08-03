import { useCallback, useEffect, useState } from 'react'

const KEY = 'cnc.theme'

// Tema: 'system' (lo que diga el SO) | 'light' | 'dark'.
//
// El atributo data-theme del <html> solo fija 'color-scheme'; la paleta entera
// la resuelve light-dark() en tokens.css. Sin atributo manda el SO.
export function useTheme() {
  const [theme, setThemeState] = useState(() => localStorage.getItem(KEY) ?? 'system')

  useEffect(() => {
    const root = document.documentElement
    if (theme === 'system') root.removeAttribute('data-theme')
    else root.setAttribute('data-theme', theme)
    localStorage.setItem(KEY, theme)
  }, [theme])

  // El ciclo del boton es de dos posiciones (claro/oscuro) partiendo de lo que
  // el sistema este mostrando ahora: nadie espera un tercer clic para volver a
  // "automatico", y quien quiera eso puede cambiar el tema del SO.
  const toggle = useCallback(() => {
    setThemeState((prev) => {
      if (prev === 'system') {
        const dark = window.matchMedia('(prefers-color-scheme: dark)').matches
        return dark ? 'light' : 'dark'
      }
      return prev === 'dark' ? 'light' : 'dark'
    })
  }, [])

  // En modo 'system' hay que ESCUCHAR el cambio del SO, no solo leerlo una vez:
  // sin esto, cambiar el tema del sistema repinta la app (via la media query de
  // CSS) pero deja el icono del boton mostrando el tema anterior.
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
