import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  CircleCheck,
  CircleStop,
  Crosshair,
  FileText,
  House,
  Info,
  Minus,
  MoveHorizontal,
  Play,
  Plug,
  Plus,
  RefreshCw,
  Ruler,
  SlidersHorizontal,
  Sun,
  Moon,
  TriangleAlert,
  Upload,
  WandSparkles,
  WifiOff,
  X,
  ZapOff,
} from 'lucide-react'

// Iconografia de la app.
//
// El sprite dibujado a mano que habia antes tenia pesos y radios distintos en
// cada simbolo (comparar 'plug' con 'sun'), y eso es lo que hacia que el
// conjunto se viera desparejo por mucho que cada icono suelto estuviera bien.
// Ahora todo viene de Lucide, que es una sola rejilla y un solo trazo.
//
// El peso se fija aca y en ningun sitio mas: un icono de esta app SIEMPRE tiene
// el mismo grosor de linea, mida 12 o mida 28.
const STROKE = 1.75

// Los dos unicos iconos propios: la pluma arriba y abajo. Son del dominio (no
// existen en ninguna libreria) y son el estado que mas se mira de un vistazo,
// asi que se dibujan con la misma rejilla de 24 y el mismo trazo que el resto.
function PenUp(props) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={STROKE}
      strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M9.5 3h5v7l-2.5 3.5L9.5 10z" />
      <path d="M4 20.5h16" />
    </svg>
  )
}

function PenDown(props) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={STROKE}
      strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M9.5 6h5v7l-2.5 3.5L9.5 13z" />
      <path d="M12 16.5v4" />
      <path d="M4 20.5h16" />
    </svg>
  )
}

// Los nombres se conservan tal cual los usan los componentes: cambiar la
// libreria de iconos no deberia obligar a tocar 20 archivos.
const REGISTRY = {
  'chevron-up': ChevronUp,
  'chevron-down': ChevronDown,
  'chevron-left': ChevronLeft,
  'chevron-right': ChevronRight,
  plus: Plus,
  minus: Minus,
  xmark: X,
  'pen-up': PenUp,
  'pen-down': PenDown,
  house: House,
  scope: Crosshair,
  'bolt-slash': ZapOff,
  play: Play,
  'stop-circle': CircleStop,
  upload: Upload,
  doc: FileText,
  wand: WandSparkles,
  ruler: Ruler,
  'arrows-lr': MoveHorizontal,
  sliders: SlidersHorizontal,
  resync: RefreshCw,
  plug: Plug,
  'wifi-slash': WifiOff,
  'check-circle': CircleCheck,
  warning: TriangleAlert,
  'info-circle': Info,
  sun: Sun,
  moon: Moon,
}

export default function Icon({ name, size = 16, className = '', title }) {
  const Glyph = REGISTRY[name]
  if (!Glyph) return null

  return (
    <Glyph
      className={`icon ${className}`.trim()}
      width={size}
      height={size}
      strokeWidth={STROKE}
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : 'true'}
      aria-label={title}
      focusable="false"
    />
  )
}
