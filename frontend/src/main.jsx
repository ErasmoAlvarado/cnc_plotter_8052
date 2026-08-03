import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

// Las fuentes van empaquetadas, no pedidas al sistema. Antes el diseno pedia
// SF Pro y en Windows caia en Segoe UI, asi que la tipografia con la que se
// veia la app no era la que nadie habia elegido.
import '@fontsource-variable/inter'
import '@fontsource-variable/jetbrains-mono'

// El orden importa: primero los tokens (variables), luego la base que los usa,
// y despues las hojas de cada area. Todas son CSS global — el aislamiento se
// consigue con nombres de clase por componente, no con CSS Modules.
import './theme/tokens.css'
import './theme/base.css'
import './shell/shell.css'
import './components/ui/ui.css'
import './components/status/status.css'
import './components/canvas/canvas.css'
import './components/dashboard/controls.css'
import './components/calibration/calibration.css'
import './components/pen/pen.css'

import AppShell from './shell/AppShell.jsx'
import { StatusProvider } from './StatusContext.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <StatusProvider>
      <AppShell />
    </StatusProvider>
  </StrictMode>,
)
