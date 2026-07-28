/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Tokens are defined as CSS variables in index.css; these are the Tailwind
        // handles for them. Keep the two in sync.
        canvas: 'rgb(var(--bg) / <alpha-value>)',
        surface: 'rgb(var(--surface) / <alpha-value>)',
        primary: 'rgb(var(--text-primary) / <alpha-value>)',
        secondary: 'rgb(var(--text-secondary) / <alpha-value>)',
        tertiary: 'rgb(var(--text-tertiary) / <alpha-value>)',
        accent: {
          DEFAULT: 'rgb(var(--accent) / <alpha-value>)',
          600: '#D97706', // hover state for amber
        },
        positive: {
          DEFAULT: 'rgb(var(--positive) / <alpha-value>)',
          bg: 'rgb(var(--positive-bg) / <alpha-value>)',
        },
        negative: {
          DEFAULT: 'rgb(var(--negative) / <alpha-value>)',
          bg: 'rgb(var(--negative-bg) / <alpha-value>)',
        },

        // --- TRANSITIONAL SHIM ---
        // Pages not yet converted to the light design system still reference the old
        // dark `ink-*` / `up` / `down` tokens. Remapping them to light equivalents keeps
        // the app coherent while the Development Order works through each page.
        // Delete each usage as its page is converted; delete this block when none remain.
        ink: {
          950: '#FAFAF7',
          900: '#FFFFFF',
          850: '#F8FAFC',
          800: '#F1F5F9',
          700: '#E2E8F0',
          600: '#CBD5E1',
        },
        up: 'rgb(var(--positive) / <alpha-value>)',
        down: 'rgb(var(--negative) / <alpha-value>)',
      },
      fontFamily: {
        sans: [
          'Pretendard Variable',
          'Pretendard',
          '-apple-system',
          'BlinkMacSystemFont',
          'Segoe UI',
          'system-ui',
          'sans-serif',
        ],
        mono: ['JetBrains Mono', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      fontSize: {
        // Spec type scale: display 32/700, h1 24/700, h2 20/600, body 14/500, small 12/500
        display: ['32px', { lineHeight: '1.2', fontWeight: '700' }],
        h1: ['24px', { lineHeight: '1.3', fontWeight: '700' }],
        h2: ['20px', { lineHeight: '1.4', fontWeight: '600' }],
        body: ['14px', { lineHeight: '1.6', fontWeight: '500' }],
        small: ['12px', { lineHeight: '1.5', fontWeight: '500' }],
        hero: ['40px', { lineHeight: '1.1', fontWeight: '700' }],
      },
    },
  },
  plugins: [],
}
