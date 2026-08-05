import * as Dialog from '@radix-ui/react-dialog'
import IconButton from './IconButton.jsx'

// dialogo modal, todas las hojas de la app pasan por aca
//
// usa Radix por debajo, antes esto implementaba a mano el focus trap y el escape
//
// entrada y salida se animan con css sobre data-state, no hace falta AnimatePresence
export default function Sheet({ open, onClose, title, description, children, footer, size = 'md' }) {
  return (
    <Dialog.Root open={open} onOpenChange={(next) => !next && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="scrim" />
        <Dialog.Content className={`sheet sheet--${size}`}>
          <header className="sheet__head">
            <Dialog.Title className="sheet__title">{title}</Dialog.Title>
            <Dialog.Close asChild>
              <IconButton name="xmark" size={15} label="Cerrar" />
            </Dialog.Close>
          </header>

          {description ? (
            <Dialog.Description className="sheet__description">{description}</Dialog.Description>
          ) : (
            /* radix tira warning si el dialog no tiene descripcion */
            <Dialog.Description className="visually-hidden">{title}</Dialog.Description>
          )}

          <div className="sheet__body">{children}</div>
          {footer && <footer className="sheet__footer">{footer}</footer>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
