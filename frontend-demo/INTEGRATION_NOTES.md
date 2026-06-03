# Notas de integracion futura con PLNC

El demo sigue siendo autonomo. La integracion futura debe mantener el contrato descrito en:

- `C:\Proyectos\plnc-poc\src\features\guided-assistant\README.md`
- `C:\Proyectos\plnc-poc\src\features\guided-assistant\INTEGRATION_GUIDE.md`

## Contrato que debemos emitir

Cuando el asistente se inserte en `plnc-poc`, el componente debera llamar a `onComplete(findings)` con:

```ts
interface AssistantFinding {
  targetSection: string;
  code: string;
  description: string;
  value: string;
}
```

En este demo, `app/lib/api.js` expone `suggestionToAssistantFindings()` para transformar una sugerencia aceptada al formato esperado.

## Estilo de referencia

Tomamos de `plnc-poc`:

- UI de trabajo densa, no landing page.
- Fondo claro `#f8fafc`, tarjetas blancas, bordes `#e2e8f0`.
- Primario teal/verde: `#0f766e`.
- Radio de borde entre `8px` y `12px`.
- Botones compactos con icono y texto.
- Drawer/panel del asistente a la derecha, con cabecera y toolbar compactos.
