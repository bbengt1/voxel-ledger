import js from "@eslint/js";
import globals from "globals";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: ["dist", "coverage", "node_modules"],
  },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
      "jsx-a11y": jsxA11y,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      ...jsxA11y.flatConfigs.recommended.rules,
      // The project uses the "label wraps input" convention; nesting
      // is the WCAG-acceptable form, but the default rule asks for
      // both nesting AND htmlFor. Configure to accept either.
      "jsx-a11y/label-has-associated-control": [
        "error",
        {
          assert: "either",
          depth: 5,
          // Custom components that wrap a real form control. jsx-a11y
          // can't see through them without an explicit allow-list.
          controlComponents: [
            "Input",
            "Textarea",
            "Select",
            "DatePicker",
            "EntityPicker",
            "AccountPicker",
            "BankAccountPicker",
            "CustomerPicker",
            "ExpenseCategoryPicker",
            "TaxProfilePicker",
            "VendorPicker",
            "Combobox",
          ],
        },
      ],
      // autoFocus is fine for primary action targets in modals
      // (Login submit, dialog confirmations); the rule is too strict
      // for our usage.
      "jsx-a11y/no-autofocus": "off",
    },
  },
  {
    files: ["**/*.test.{ts,tsx}"],
    rules: {
      // `role` is a prop name in some of our components and collides
      // with the ARIA role attribute the plugin guards.
      "jsx-a11y/aria-role": "off",
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
      "@typescript-eslint/consistent-type-imports": [
        "error",
        { prefer: "type-imports", fixStyle: "inline-type-imports" },
      ],
    },
  },
);
