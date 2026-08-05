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

// todo sale de lucide, misma grilla y mismo trazo en toda la app
//
// el grosor se define solo aca, ningun icono tiene su propia linea
const STROKE = 1.75

// los unicos 2 iconos propios: pluma arriba y abajo, no existen en ninguna libreria
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

// cambiar de libreria de iconos no deberia obligar a tocar 20 archivos
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
