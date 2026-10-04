/**
 * CarbonX Design Tokens — Single Source of Truth
 * All colors, spacing, typography, shadows, radii, transitions
 * Import: import { colors, spacing, radius, ... } from '@/design-system/tokens'
 */

// ============================================
// COLOR SYSTEM — Semantic + Brand
// ============================================

export const colors = {
  // Brand (your forest palette — keep as identity)
  brand: {
    50: '#EEF5EE',
    100: '#DDECDD',
    200: '#C2DEC3',
    300: '#94C897',
    400: '#54A85A',
    500: '#1F7A4D',  // Primary action
    600: '#1A6841',
    700: '#155435',
    800: '#104028',
    900: '#0C2D1D',
    950: '#061810',
  },

  // Semantic — used in components, NOT brand directly
  semantic: {
    // Backgrounds
    bg: {
      primary: '#FAFAF7',      // Page background
      secondary: '#F4F4EB',    // Card background
      tertiary: '#EEF5EE',     // Accent background (brand-50)
      inverse: '#1F2923',      // Dark surfaces
    },
    // Text
    text: {
      primary: '#1F2923',      // Headings, important content
      secondary: '#526056',    // Body text
      muted: '#7A8C7E',        // Helper, placeholder, meta
      inverse: '#FAFAF7',      // On dark backgrounds
      link: '#1F7A4D',         // Links, interactive text
    },
    // Borders
    border: {
      light: '#E2E7E3',        // Default borders
      medium: '#C2CCC4',       // Emphasized borders
      dark: '#94A397',         // Focus rings, active borders
      focus: '#1F7A4D',        // Focus ring color
    },
    // Status — ONLY use these for status communication
    status: {
      success: {
        bg: '#EEF5EE',
        text: '#104028',
        border: '#C2DEC3',
        icon: '#1F7A4D',
      },
      warning: {
        bg: '#FEF3C7',
        text: '#78350F',
        border: '#FCD34D',
        icon: '#D97706',
      },
      error: {
        bg: '#FEF2F2',
        text: '#7F1D1D',
        border: '#FECACA',
        icon: '#DC2626',
      },
      info: {
        bg: '#EFF6FF',
        text: '#1E3A5F',
        border: '#BFDBFE',
        icon: '#3B82F6',
      },
    },
    // Badge tiers — your verification system
    badge: {
      registry: { bg: '#EEF5EE', text: '#104028', border: '#C2DEC3' },
      registryDoc: { bg: '#DDECDD', text: '#0C2D1D', border: '#94C897' },
      document: { bg: '#EFF6FF', text: '#1E3A5F', border: '#BFDBFE' },
      fpo: { bg: '#FEF3C7', text: '#78350F', border: '#FCD34D' },
      pending: { bg: '#FEF2F2', text: '#7F1D1D', border: '#FECACA' },
    },
  },

  // Legacy aliases (for gradual migration) — DEPRECATED
  // TODO: Remove after all pages migrated
  legacy: {
    profit: '#1F7A4D',
    alert: '#D97706',
    error: '#DC2626',
    verifBlue: '#3B82F6',
  },
};

// ============================================
// SPACING — 4px base scale
// ============================================
export const spacing = {
  0: '0',
  1: '4px',    // xs
  2: '8px',    // sm
  3: '12px',   // md
  4: '16px',   // lg
  5: '20px',   // xl
  6: '24px',   // 2xl
  8: '32px',   // 3xl
  10: '40px',  // 4xl
  12: '48px',  // 5xl
  16: '64px',  // 6xl
  20: '80px',  // 7xl
};

// Semantic spacing for components
export const space = {
  none: spacing[0],
  xs: spacing[1],
  sm: spacing[2],
  md: spacing[3],
  lg: spacing[4],
  xl: spacing[5],
  '2xl': spacing[6],
  '3xl': spacing[8],
  '4xl': spacing[10],
  '5xl': spacing[12],
};

// ============================================
// TYPOGRAPHY
// ============================================
export const fontFamily = {
  sans: 'Inter, system-ui, sans-serif',      // Body, UI
  display: 'Manrope, system-ui, sans-serif', // Headings, numbers
  mono: 'JetBrains Mono, monospace',         // Code, hashes, amounts
  // Legacy
  inter: 'Inter, system-ui, sans-serif',
  manrope: 'Manrope, system-ui, sans-serif',
  poppins: 'Poppins, system-ui, sans-serif',
};

export const fontSize = {
  xs: ['12px', { lineHeight: '16px', letterSpacing: '0.01em' }],      // 12px
  sm: ['14px', { lineHeight: '20px', letterSpacing: '0.01em' }],      // 14px
  base: ['16px', { lineHeight: '24px', letterSpacing: '0' }],         // 16px
  lg: ['18px', { lineHeight: '28px', letterSpacing: '-0.01em' }],     // 18px
  xl: ['20px', { lineHeight: '28px', letterSpacing: '-0.01em' }],     // 20px
  '2xl': ['24px', { lineHeight: '32px', letterSpacing: '-0.02em' }],  // 24px
  '3xl': ['30px', { lineHeight: '36px', letterSpacing: '-0.02em' }],  // 30px
  '4xl': ['36px', { lineHeight: '40px', letterSpacing: '-0.03em' }],  // 36px
};

export const fontWeight = {
  normal: '400',
  medium: '500',
  semibold: '600',
  bold: '700',
  extrabold: '800',
};

// ============================================
// BORDER RADIUS
// ============================================
export const radius = {
  none: '0',
  xs: '4px',
  sm: '8px',
  md: '12px',
  lg: '16px',
  xl: '24px',
  '2xl': '32px',
  full: '9999px',
};

// ============================================
// SHADOWS — Elevation system
// ============================================
export const shadows = {
  none: 'none',
  xs: '0 1px 2px 0 rgb(0 0 0 / 0.03)',
  sm: '0 1px 3px 0 rgb(0 0 0 / 0.05), 0 1px 2px -1px rgb(0 0 0 / 0.05)',
  md: '0 4px 6px -1px rgb(0 0 0 / 0.05), 0 2px 4px -2px rgb(0 0 0 / 0.03)',
  lg: '0 10px 15px -3px rgb(0 0 0 / 0.05), 0 4px 6px -4px rgb(0 0 0 / 0.03)',
  xl: '0 20px 25px -5px rgb(0 0 0 / 0.05), 0 8px 10px -6px rgb(0 0 0 / 0.03)',
  '2xl': '0 25px 50px -12px rgb(0 0 0 / 0.1)',
  inner: 'inset 0 2px 4px 0 rgb(0 0 0 / 0.05)',
  // Brand-specific
  card: '0 4px 20px rgba(0, 0, 0, 0.04)',
  premium: '0 4px 20px -2px rgba(31, 122, 77, 0.08), 0 2px 8px -1px rgba(0, 0, 0, 0.04)',
  focus: '0 0 0 3px rgb(31 122 77 / 0.3)',
};

// ============================================
// TRANSITIONS
// ============================================
export const transitions = {
  fast: '150ms cubic-bezier(0.4, 0, 0.2, 1)',
  normal: '200ms cubic-bezier(0.4, 0, 0.2, 1)',
  slow: '300ms cubic-bezier(0.4, 0, 0.2, 1)',
  spring: '300ms cubic-bezier(0.34, 1.56, 0.64, 1)',
};

// ============================================
// Z-INDEX LAYERS
// ============================================
export const zIndex = {
  base: 0,
  dropdown: 100,
  sticky: 200,
  fixed: 300,
  modalBackdrop: 400,
  modal: 500,
  popover: 600,
  tooltip: 700,
  toast: 800,
};

// ============================================
// BREAKPOINTS (match Tailwind)
// ============================================
export const breakpoints = {
  sm: '640px',
  md: '768px',
  lg: '1024px',
  xl: '1280px',
  '2xl': '1536px',
};

// ============================================
// COMPONENT DEFAULTS — Used by primitives
// ============================================
export const componentDefaults = {
  button: {
    height: {
      sm: '32px',
      md: '40px',
      lg: '48px',
    },
    padding: {
      sm: '0 12px',
      md: '0 16px',
      lg: '0 24px',
    },
  },
  input: {
    height: '40px',
    padding: '0 12px',
  },
  card: {
    padding: {
      sm: spacing[3],
      md: spacing[4],
      lg: spacing[6],
    },
  },
  modal: {
    maxWidth: {
      sm: '320px',
      md: '400px',
      lg: '560px',
      xl: '720px',
      full: '95vw',
    },
  },
};

// ============================================
// EXPORT ALL AS DEFAULT FOR CONVENIENCE
// ============================================
const tokens = {
  colors,
  spacing,
  space,
  fontFamily,
  fontSize,
  fontWeight,
  radius,
  shadows,
  transitions,
  zIndex,
  breakpoints,
  componentDefaults,
};

export default tokens;