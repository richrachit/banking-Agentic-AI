export const colors = {
  ink: '#102A43',
  muted: '#627D98',
  canvas: '#F4F7FB',
  surface: '#FFFFFF',
  surfaceSoft: '#EAF3F1',
  line: '#D9E2EC',
  primary: '#0B6E69',
  primaryDark: '#074E4B',
  primarySoft: '#DDF3F0',
  accent: '#ED8B32',
  accentSoft: '#FFF0E2',
  success: '#16856B',
  warning: '#B76516',
  danger: '#B42318',
  dangerSoft: '#FEECEB',
  info: '#2563A6',
  infoSoft: '#E8F1FC',
  white: '#FFFFFF',
  black: '#071C2C',
} as const;

export const radius = {
  sm: 10,
  md: 16,
  lg: 24,
  pill: 999,
} as const;

export const space = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 18,
  xl: 24,
  xxl: 36,
} as const;

export const shadows = {
  card: {
    shadowColor: '#102A43',
    shadowOffset: { width: 0, height: 7 },
    shadowOpacity: 0.08,
    shadowRadius: 18,
    elevation: 3,
  },
};

