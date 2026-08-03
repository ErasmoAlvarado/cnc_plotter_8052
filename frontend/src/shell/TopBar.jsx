import { useTheme } from '../useTheme.js'
import IconButton from '../components/ui/IconButton.jsx'
import Tooltip from '../components/ui/Tooltip.jsx'
import ConnectionPill from '../components/status/ConnectionPill.jsx'
import PositionReadout from '../components/status/PositionReadout.jsx'
import JobProgressBar from '../components/status/JobProgressBar.jsx'

// Barra superior. Orden de lectura de izquierda a derecha: quien soy -> donde
// estoy conectado -> donde esta la maquina -> que esta haciendo -> como la
// paro. Los ajustes van al final, que es donde menos estorban.
//
// Es la unica pieza que esta siempre a la vista, asi que no contiene nada que
// no sea imprescindible: cualquier cosa que se pueda mirar "cuando haga falta"
// vive en el rail o en una hoja.
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
        {/* Marca: el trazo de un plotter y el cabezal al final. Dibujado aca y
            no en un archivo aparte porque es una sola forma de 3 lineas. */}
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
