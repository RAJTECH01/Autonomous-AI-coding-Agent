// ESLint 9 flat configuration.
//
// The previous `lint` script called `eslint . --ext ts,tsx` but eslint was never
// in devDependencies, so the script always failed. `--ext` was also removed in
// ESLint 9; file selection now comes from the `files` globs below.
//
// Rule levels are deliberately split:
//   error  - things that break at runtime or hide bugs
//   warn   - style and hygiene, visible locally without blocking a merge
// CI runs with --max-warnings 0 on changed files only, matching the backend's
// changed-files formatting gate.

import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import unusedImports from 'eslint-plugin-unused-imports';
import prettierConfig from 'eslint-config-prettier';

export default tseslint.config(
  {
    // Never lint build output, dependencies or coverage reports.
    ignores: ['dist/**', 'node_modules/**', 'coverage/**', '*.config.js'],
  },

  js.configs.recommended,
  ...tseslint.configs.recommended,

  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        // Browser globals used by the app. Declared explicitly rather than
        // pulling in the `globals` package for four names.
        window: 'readonly',
        document: 'readonly',
        localStorage: 'readonly',
        setInterval: 'readonly',
        clearInterval: 'readonly',
        setTimeout: 'readonly',
        clearTimeout: 'readonly',
        console: 'readonly',
        fetch: 'readonly',
      },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
      'unused-imports': unusedImports,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,

      // Fast-refresh correctness: a module exporting both a component and
      // non-component values breaks HMR.
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

      // --- Errors: real defects -------------------------------------------
      // Unused imports and variables mean dead or half-finished code. The
      // unused-imports plugin is used instead of the base rule because its
      // version is auto-fixable: `npm run lint -- --fix` deletes the dead import
      // rather than just reporting it. Underscore prefix is the escape hatch.
      '@typescript-eslint/no-unused-vars': 'off',
      'unused-imports/no-unused-imports': 'error',
      'unused-imports/no-unused-vars': [
        'error',
        {
          vars: 'all',
          varsIgnorePattern: '^_',
          args: 'after-used',
          argsIgnorePattern: '^_',
          caughtErrorsIgnorePattern: '^_',
        },
      ],
      // `==` between different types is a common source of subtle bugs.
      eqeqeq: ['error', 'always', { null: 'ignore' }],
      'no-var': 'error',
      'no-throw-literal': 'error',

      // --- Warnings: hygiene, surfaced but not blocking --------------------
      // `any` is pervasive in the current code (axios responses, execution
      // summaries). Warned rather than errored so the gate is adoptable; each
      // one removed is a real improvement.
      '@typescript-eslint/no-explicit-any': 'warn',
      // console.* is fine while developing, noise in production.
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      'prefer-const': 'warn',
    },
  },

  {
    // Test files may use `any` freely and assert on internals.
    files: ['**/*.test.{ts,tsx}', '**/*.spec.{ts,tsx}', 'src/test/**'],
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      'no-console': 'off',
    },
  },

  // Must stay last: switches off every stylistic rule that would fight
  // prettier, so formatting has exactly one owner.
  prettierConfig,
);
