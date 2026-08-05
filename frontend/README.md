# Frontend — CNC Plotter

Interfaz de control del plotter, en React 19 + Vite. Sin dependencias de UI: el sistema de
diseño es propio (`src/theme/`) y los iconos son un sprite SVG (`public/icons.svg`).

## Levantarlo

Hacen falta los dos procesos. Desde la raíz del repo, `dev.bat` abre ambos; a mano:

```
python python/cnc_api.py      # backend en http://127.0.0.1:8000
cd frontend && npm run dev    # interfaz en http://localhost:5173
```

El puerto 5173 es fijo (`strictPort`): el backend solo acepta CORS desde ahí, así que arrancar
en otro puerto rompería las llamadas con un "Failed to fetch" sin explicación.

Sin la máquina conectada se puede usar todo activando **Modo simulación** al conectar, y el
botón **Simular** de la tarjeta de dibujo recorre el G-code en pantalla sin mover nada.

## Cómo está organizado

```
src/
  api.js            único punto de contacto con el backend (fetch + WebSocket)
  StatusContext.jsx estado compartido: polling, WebSocket, seguimiento en vivo, motivos de bloqueo
  theme/            tokens de diseño (claro/oscuro) y estilos base
  components/
    ui/             primitivas sin lógica de CNC (Button, Card, Sheet, …)
    status/         franja superior
    dashboard/      pantalla principal
    canvas/         lienzo del dibujo y seguimiento en vivo
    calibration/    asistente de calibración
    connection/     hoja de conexión y recuperación de posición
    advanced/       ajustes avanzados
```

Ningún componente llama a `fetch` directamente: todo pasa por `src/api.js`.

`DISENO_UI.md` explica las decisiones de diseño y por qué cada cosa está donde está.

## Comandos

```
npm run dev      servidor de desarrollo
npm run build    build de producción en dist/
npm run lint     oxlint
```
