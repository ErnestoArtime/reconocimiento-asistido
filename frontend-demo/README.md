# Demo Next: reconocimiento asistido

Mini frontend para simular el flujo de reconocimiento asistido dentro del tab
`Historia Clinica`.

## Arranque

```powershell
cd C:\Proyectos\reconocimiento-asistido\frontend-demo
npm install
npm run dev
```

URL:

```text
http://localhost:3010
```

## Flujo simulado

1. Abrir `Reconocimiento Asistido`.
2. Pulsar `Iniciar entrevista`.
3. Pulsar `Procesar texto`.
4. Revisar transcripcion, sugerencias, evidencia y conflictos.
5. Aceptar sugerencias individualmente o con `Aceptar todo`.
6. Cerrar el panel y ver respuestas aplicadas al formulario.

## Casos incluidos

- Habitos:
  - `C5-1` fuma actualmente: `No`
  - `C5-121` fumado anteriormente: `Si`
  - `C5-2` alcohol: `No`
- Alergias:
  - conflicto sobre `C6-1`, cambia de `No` a `Si`
  - `C6-141` antibioticos: `Derivados penicilina`

