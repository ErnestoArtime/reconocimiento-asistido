import { createTheme } from "@mui/material/styles";

// Tokens alineados con plnc-poc (teal primary, slate text, verde answered).
const theme = createTheme({
  palette: {
    primary: { main: "#0f766e", dark: "#0b5e57", light: "#5eada6" },
    success: { main: "#22c55e", dark: "#16a34a" },
    warning: { main: "#f59e0b" },
    error: { main: "#ef4444" },
    info: { main: "#0ea5e9" },
    background: { default: "#f8fafc", paper: "#ffffff" },
    text: { primary: "#1e293b", secondary: "#64748b" },
    divider: "#e2e8f0",
  },
  shape: { borderRadius: 8 },
  typography: {
    fontFamily:
      'system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: { textTransform: "none", fontWeight: 700, boxShadow: "none" },
      },
    },
  },
});

export default theme;
