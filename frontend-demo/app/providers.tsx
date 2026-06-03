"use client";

import type { ReactNode } from "react";
import { ThemeProvider } from "@mui/material/styles";
import theme from "./theme";

// El theme MUI contiene funciones (breakpoints.up, etc.). En Next 16 los props
// Server->Client deben ser serializables, asi que el ThemeProvider y el theme
// viven en un Client Component; el theme nunca cruza el limite como prop.
export default function Providers({ children }: { children: ReactNode }) {
  return <ThemeProvider theme={theme}>{children}</ThemeProvider>;
}
