import Icon from './Icon.jsx'
import IconButton from './IconButton.jsx'

const ICONS = {
  info: 'info-circle',
  success: 'check-circle',
  warn: 'warning',
  error: 'warning',
}

// Aviso en linea. Se usa para lo que tiene que quedarse a la vista (Z sin
// energizar, comunicacion perdida, firmware antiguo), no para confirmaciones
// —esas van en ConfirmDialog, que interrumpe a proposito.
export default function Banner({ tone = 'info', title, children, action, onDismiss }) {
  return (
    <div className={`banner banner--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <Icon name={ICONS[tone] ?? 'info-circle'} size={20} />
      <div className="banner__text">
        {title && <p className="banner__title">{title}</p>}
        {children}
      </div>
      {action}
      {onDismiss && (
        <IconButton
          baseClass="banner__close"
          name="xmark"
          size={16}
          label="Descartar"
          onClick={onDismiss}
        />
      )}
    </div>
  )
}
