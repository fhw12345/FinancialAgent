module.exports = {
  root: true,
  env: { browser: true, es2021: true, node: true },
  extends: [
    "eslint:recommended",
    "plugin:react/recommended",
    "plugin:react-hooks/recommended",
    "plugin:jsx-a11y/recommended",
    "plugin:@typescript-eslint/recommended",
  ],
  ignorePatterns: ["dist", ".eslintrc.cjs"],
  parser: "@typescript-eslint/parser",
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "module",
    ecmaFeatures: {
      jsx: true,
    },
    project: ["./tsconfig.json", "./tsconfig.node.json"],
    tsconfigRootDir: __dirname,
  },
  plugins: [
    "react",
    "react-hooks",
    "jsx-a11y",
    "react-refresh",
    "@typescript-eslint",
    "security",
    "eslint-plugin-perf-standard",
  ],
  settings: {
    react: {
      version: "detect", // Automatically detect React version
    },
  },
  rules: {
    // React rules
    "react/react-in-jsx-scope": "off", // Not needed in React 18+
    "react/prop-types": "off", // Using TypeScript for prop validation
    "react/jsx-key": "error", // Enforce keys in lists

    // React Hooks rules
    "react-hooks/rules-of-hooks": "error", // Enforce Rules of Hooks
    "react-hooks/exhaustive-deps": "warn", // Warn about missing dependencies

    // React Refresh
    "react-refresh/only-export-components": [
      "warn",
      { allowConstantExport: true },
    ],

    // TypeScript rules
    "@typescript-eslint/no-non-null-assertion": "warn",
    "@typescript-eslint/no-unused-vars": "error",
    "@typescript-eslint/no-explicit-any": "warn",
    "@typescript-eslint/no-unsafe-assignment": "warn",
    "@typescript-eslint/no-unsafe-member-access": "warn",
    "@typescript-eslint/no-unsafe-call": "warn",
    "@typescript-eslint/no-unsafe-return": "warn",

    // Security rules
    "security/detect-object-injection": "warn",
    "security/detect-non-literal-regexp": "warn",
    "security/detect-unsafe-regex": "warn",
    "security/detect-buffer-noassert": "error",
    "security/detect-eval-with-expression": "error",
    "security/detect-no-csrf-before-method-override": "error",
    "security/detect-possible-timing-attacks": "warn",

    // Performance rules
    "perf-standard/no-instanceof-guard": "warn",
    "perf-standard/no-self-in-constructor": "warn",

    // Accessibility rules remain visible without blocking local iteration.
    "jsx-a11y/label-has-associated-control": "warn",
    "jsx-a11y/no-noninteractive-element-interactions": "warn",
    "jsx-a11y/no-static-element-interactions": "warn",
    "jsx-a11y/no-autofocus": "warn",
    "no-constant-condition": "warn",
    "react/display-name": "warn",
    "react/no-unescaped-entities": "warn",
  },
};
