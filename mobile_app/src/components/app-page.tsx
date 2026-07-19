import { colors, radius, space } from '@/constants/app-theme';
import { useAuth } from '@/context/auth';
import type { UserRole } from '@/lib/types';
import { Brand, Button, LoadingState, roleLabels } from '@/components/ui';
import { Redirect, usePathname, useRouter } from 'expo-router';
import type { PropsWithChildren } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

const navigation: { label: string; href: string; roles: UserRole[] }[] = [
  { label: 'Dashboard', href: '/dashboard', roles: ['CUSTOMER', 'LOAN', 'CREDIT', 'COMPLIANCE', 'ADMIN'] },
  { label: 'Loans', href: '/loans', roles: ['CUSTOMER', 'LOAN', 'CREDIT', 'COMPLIANCE', 'ADMIN'] },
  { label: 'New application', href: '/loans/new', roles: ['CUSTOMER'] },
  { label: 'Dormant accounts', href: '/accounts', roles: ['CUSTOMER', 'COMPLIANCE', 'ADMIN'] },
  { label: 'Approvals', href: '/approvals', roles: ['LOAN', 'CREDIT', 'COMPLIANCE', 'ADMIN'] },
  { label: 'AI registry', href: '/models', roles: ['ADMIN'] },
];

export function AppPage({ children, roles }: PropsWithChildren<{ roles?: UserRole[] }>) {
  const { session, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const { width } = useWindowDimensions();

  if (loading) {
    return <SafeAreaView style={styles.center}><LoadingState /></SafeAreaView>;
  }
  if (!session) return <Redirect href="/login" />;
  if (roles && !roles.includes(session.user.role)) {
    return <Redirect href="/dashboard" />;
  }

  const compact = width < 650;
  const items = navigation.filter((item) => item.roles.includes(session.user.role));
  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.header}>
        <Brand compact={compact} />
        <View style={styles.identity}>
          {!compact ? (
            <View style={styles.identityCopy}>
              <Text style={styles.identityName} numberOfLines={1}>{session.user.display_name}</Text>
              <Text style={styles.identityRole}>{roleLabels[session.user.role]}</Text>
            </View>
          ) : null}
          <Button
            compact
            label="Sign out"
            variant="ghost"
            onPress={() => logout().finally(() => router.replace('/'))}
          />
        </View>
      </View>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.navScroll}
        contentContainerStyle={styles.nav}>
        {items.map((item) => {
          const active = pathname === item.href || (item.href === '/loans' && pathname.startsWith('/loans/'));
          return (
            <Pressable key={item.href} onPress={() => router.push(item.href as never)} style={[styles.navItem, active && styles.navItemActive]}>
              <Text style={[styles.navText, active && styles.navTextActive]}>{item.label}</Text>
            </Pressable>
          );
        })}
      </ScrollView>
      <KeyboardAvoidingView style={styles.main} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          keyboardShouldPersistTaps="handled"
          contentInsetAdjustmentBehavior="automatic"
          contentContainerStyle={[styles.content, width >= 900 && styles.contentWide]}>
          {children}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.canvas },
  center: { flex: 1, justifyContent: 'center', backgroundColor: colors.canvas },
  header: { minHeight: 68, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, paddingHorizontal: space.lg, paddingVertical: 10, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.line },
  identity: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  identityCopy: { alignItems: 'flex-end', maxWidth: 220 },
  identityName: { color: colors.ink, fontWeight: '900', fontSize: 13 },
  identityRole: { color: colors.muted, fontSize: 11, marginTop: 2 },
  navScroll: { flexGrow: 0, backgroundColor: colors.surface },
  nav: { paddingHorizontal: space.lg, paddingVertical: 9, gap: 7 },
  navItem: { paddingHorizontal: 13, paddingVertical: 9, borderRadius: radius.pill },
  navItemActive: { backgroundColor: colors.primarySoft },
  navText: { color: colors.muted, fontWeight: '800', fontSize: 12 },
  navTextActive: { color: colors.primaryDark },
  main: { flex: 1 },
  content: { width: '100%', maxWidth: 1180, alignSelf: 'center', padding: space.lg, paddingBottom: 64, gap: space.lg },
  contentWide: { paddingHorizontal: space.xxl, paddingTop: space.xl },
});

