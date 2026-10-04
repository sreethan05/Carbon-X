/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#16A34A',
          hover: '#15803D',
          light: '#22C55E',
          dark: '#14532D',
        },
        surface: {
          DEFAULT: '#F6F5EE',
          card: '#FFFFFF',
          sage: '#E9F2EA',
          muted: '#F1F4EF',
        },
        agriText: {
          main: '#0F172A',
          muted: '#475569',
          subtle: '#64748B',
        },
        badge: {
          registry: '#16A34A',
          registryDoc: '#166534',
          doc: '#1D4ED8',
          fpo: '#D97706',
          pending: '#DC2626',
        },
        forest: {
          50: '#ECFDF5',
          100: '#D1FAE5',
          200: '#A7F3D0',
          300: '#6EE7B7',
          400: '#34D399',
          500: '#10B981', // Primary Action Green
          600: '#059669',
          700: '#047857',
          800: '#065F46',
          900: '#064E3B',
        },
        earth: {
          light: '#4ADE80',
          DEFAULT: '#16A34A',
          dark: '#15803D',
        },
        soil: {
          light: '#A0826C',
          DEFAULT: '#7C6049',
          dark: '#584231',
        },
        sky: {
          50: '#F0F9FF',
          100: '#E0F2FE',
          200: '#BAE6FD',
          300: '#7DD3FC',
          400: '#38BDF8',
          500: '#0EA5E9',
          600: '#0284C7',
          700: '#0369A1',
          800: '#075985',
          900: '#0C4A6E',
          light: '#F0F9FF',
          DEFAULT: '#38BDF8',
          dark: '#0369A1',
        },
        carbon: {
          50: '#F8FAFC',
          100: '#F1F5F9',
          200: '#E2E8F0',
          300: '#CBD5E1',
          400: '#94A3B8',
          500: '#64748B',
          600: '#475569',
          700: '#334155',
          800: '#1E293B',
          900: '#0F172A',
        },
        warm: {
          white: '#FAFAF7',
          cream: '#F4F4EB',
        },
        profit: '#16A34A',
        alert: '#D97706',
        error: '#DC2626',
        verifBlue: '#1D4ED8',
      },
      fontFamily: {
        poppins: ['Poppins', 'sans-serif'],
        inter: ['Inter', 'sans-serif'],
        manrope: ['Manrope', 'sans-serif'],
      },
      boxShadow: {
        premium: '0 4px 20px -2px rgba(4, 120, 87, 0.10), 0 2px 8px -1px rgba(0, 0, 0, 0.04)',
        card: '0 4px 20px rgba(0, 0, 0, 0.04)',
      }
    },
  },
  plugins: [],
}
