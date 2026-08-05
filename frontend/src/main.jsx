import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

// las fuentes van empaquetadas y no pedidas al sistema. antes el diseno
// pedia SF Pro y en windows caia a Segoe UI, la tipografia terminaba
// siendo una que nadie eligio
import '@fontsource-variable/inter'
import '@fontsource-variable/jetbrains-mono'

// el orden importa: primero los tokens (variables), despues la base que
// los usa, y recien ahi las hojas de cada area. todo css global, el
// aislamiento es por nombre de clase y no con css modules
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
