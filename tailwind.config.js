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
          DEFAULT: '#1F7A4D',
          hover: '#18633E',
          light: '#26965E',
          dark: '#145233',
        },
        surface: {
          DEFAULT: '#FAFAF7',
          card: '#FFFFFF',
          sage: '#EEF5EE',
          muted: '#F4F7F4',
        },
        agriText: {
          main: '#1F2923',
          muted: '#526056',
          subtle: '#7A8C7E',
        },
        badge: {
          registry: '#1F7A4D',
          registryDoc: '#166534',
          doc: '#1D4ED8',
          fpo: '#D97706',
          pending: '#DC2626',
        },
        forest: {
          50: '#EEF5EE',
          100: '#DDECDD',
          200: '#C2DEC3',
          300: '#94C897',
          400: '#54A85A',
          500: '#1F7A4D', // Primary Action Green
          600: '#1A6841',
          700: '#155435',
          800: '#104028',
          900: '#0C2D1D',
        },
        earth: {
          light: '#81C784',
          DEFAULT: '#1F7A4D',
          dark: '#155435',
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
          50: '#FAFAF7',
          100: '#F4F6F4',
          200: '#E2E7E3',
          300: '#C2CCC4',
          400: '#94A397',
          500: '#647568',
          600: '#47544A',
          700: '#323C34',
          800: '#232B25',
          900: '#1F2923',
        },
        warm: {
          white: '#FAFAF7',
          cream: '#F4F4EB',
        },
        profit: '#1F7A4D',
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
        premium: '0 4px 20px -2px rgba(31, 122, 77, 0.08), 0 2px 8px -1px rgba(0, 0, 0, 0.04)',
        card: '0 4px 20px rgba(0, 0, 0, 0.04)',
      }
    },
  },
  plugins: [],
}
