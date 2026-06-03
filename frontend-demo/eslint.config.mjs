import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import tsEslint from "typescript-eslint";
import prettier from "eslint-plugin-prettier";

// Alineado con plnc-poc (next core-web-vitals + typescript-eslint + prettier).
// Pragmatico: prettier como `warn` y no-explicit-any off para no bloquear el
// codigo JS legacy (page.jsx / api.js) durante la migracion gradual a TS.
const eslintConfig = defineConfig([
  ...nextVitals,
  ...tsEslint.configs.recommended,
  {
    plugins: { prettier },
    rules: {
      "prettier/prettier": "warn",
      "prefer-const": "error",
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_" },
      ],
      "react/react-in-jsx-scope": "off",
    },
  },
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "node_modules/",
  ]),
]);

export default eslintConfig;
