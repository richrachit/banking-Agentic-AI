import { AuthProvider } from '@/context/auth';
import { colors } from '@/constants/app-theme';
import { DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

const bankingTheme = {
  ...DefaultTheme,
  colors: {
    ...DefaultTheme.colors,
    primary: colors.primary,
    background: colors.canvas,
    card: colors.surface,
    text: colors.ink,
    border: colors.line,
  },
};

export default function RootLayout() {
  return (
    <AuthProvider>
      <ThemeProvider value={bankingTheme}>
        <StatusBar style="dark" />
        <Stack screenOptions={{ headerShown: false, animation: 'fade' }} />
      </ThemeProvider>
    </AuthProvider>
  );
}

