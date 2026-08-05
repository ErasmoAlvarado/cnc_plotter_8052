import { useTheme } from '../useTheme.js'
import IconButton from '../components/ui/IconButton.jsx'
import Tooltip from '../components/ui/Tooltip.jsx'
import ConnectionPill from '../components/status/ConnectionPill.jsx'
import PositionReadout from '../components/status/PositionReadout.jsx'
import JobProgressBar from '../components/status/JobProgressBar.jsx'

// barra superior. orden de lectura izq a derecha: quien soy -> donde estoy
// conectado -> donde esta la maquina -> que esta haciendo -> como la paro.
// los ajustes van al final, que es donde menos estorban.
//
// es lo unico que siempre esta a la vista, no lleva nada que no sea
// imprescindible -- todo lo que se puede mirar "cuando haga falta" va en
// el rail o en una hoja
export default function TopBar({ onOpenConnection, onOpenAdvanced, onToggleRail, railOpen }) {
  const { isDark, toggle } = useTheme()

  return (
    <header className="topbar">
      <IconButton
        className="topbar__rail-toggle"
        name="sliders"
        onClick={onToggleRail}
        label={railOpen ? 'Ocultar controles' : 'Mostrar controles'}
        aria-expanded={railOpen}
      />

      <div className="topbar__brand">
        {/* logo: el trazo de un plotter con el cabezal al final. va inline
            y no en un archivo aparte porque son 3 lineas nomas */}
        <svg className="topbar__logo" viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="M3 18.5c3.5 0 4-13 7.5-13s4 9 7.5 9"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
            strokeLinecap="round"
          />
          <circle cx="19.4" cy="14.6" r="2.4" fill="currentColor" />
        </svg>
        <span className="topbar__name">Plotter</span>
      </div>

      <span className="topbar__sep" />

      <ConnectionPill onOpen={onOpenConnection} />

      <PositionReadout />

      <JobProgressBar />

      <div className="topbar__tools">
        <Tooltip label={isDark ? 'Modo claro' : 'Modo oscuro'} side="bottom">
          <IconButton
            name={isDark ? 'sun' : 'moon'}
            onClick={toggle}
            label={isDark ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro'}
          />
        </Tooltip>
        <Tooltip label="Ajustes avanzados" side="bottom">
          <IconButton name="sliders" onClick={onOpenAdvanced} label="Ajustes avanzados" />
        </Tooltip>
      </div>
    </header>
  )
}
