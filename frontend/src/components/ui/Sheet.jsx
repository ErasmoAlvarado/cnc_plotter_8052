import * as Dialog from '@radix-ui/react-dialog'
import IconButton from './IconButton.jsx'

// Dialogo modal. Toda la revelacion progresiva de la app pasa por aca:
// conexion, asistente de calibracion y ajustes avanzados.
//
// Por debajo es Radix. La version anterior implementaba a mano la trampa de
// foco, el bloqueo del scroll, el Escape y la restauracion del foco al cerrar —
// unas 40 lineas que ahora las pone la libreria, y las pone bien (incluye el
// caso que faltaba: devolver el foco al elemento correcto cuando la hoja se
// cierra sola desde codigo, no por un clic).
//
// La entrada y la salida se animan con CSS sobre [data-state]: Radix retrasa el
// desmontaje hasta que la animacion termina, asi que no hace falta envolver el
// portal en AnimatePresence.
//
// La API de props es la misma de antes para no tocar los cinco sitios que la
// usan.
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
            /* Radix avisa por consola si un dialogo no tiene descripcion; cuando
             * no hace falta una, se declara explicitamente que no la hay. */
            <Dialog.Description className="visually-hidden">{title}</Dialog.Description>
          )}

          <div className="sheet__body">{children}</div>
          {footer && <footer className="sheet__footer">{footer}</footer>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
