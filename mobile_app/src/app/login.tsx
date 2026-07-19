import { Banner, Brand, Button, Card, ChoiceChips, Field, LoadingState, roleLabels } from '@/components/ui';
import { colors, space } from '@/constants/app-theme';
import { useAuth } from '@/context/auth';
import type { UserRole } from '@/lib/types';
import { Redirect, useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

const roles = (Object.keys(roleLabels) as UserRole[]).map((value) => ({ value, label: roleLabels[value] }));

export default function LoginScreen() {
  const { session, loading, login } = useAuth();
  const router = useRouter();
  const params = useLocalSearchParams<{ created?: string }>();
  const [role, setRole] = useState<UserRole>('CUSTOMER');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (loading) return <SafeAreaView style={styles.safe}><LoadingState /></SafeAreaView>;
  if (session) return <Redirect href="/dashboard" />;

  const submit = async () => {
    if (!username.trim() || !password) {
      setError('Enter your username and password.');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      await login({ username: username.trim(), password, user_type: role });
      router.replace('/dashboard');
    } catch (value) {
      setError(value instanceof Error ? value.message : 'Login failed.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView style={styles.safe} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.content}>
          <View style={styles.brand}><Brand /></View>
          <Card style={styles.card}>
            <View style={styles.heading}>
              <Text style={styles.eyebrow}>SECURE WORKSPACE</Text>
              <Text style={styles.title}>Welcome back</Text>
              <Text style={styles.body}>Select your role and sign in. Your dashboard and available actions are scoped to that role.</Text>
            </View>
            {params.created === '1' ? <Banner tone="success" title="Account created" body="Your profile is ready. Sign in with the details you registered." /> : null}
            {error ? <Banner tone="error" body={error} /> : null}
            <ChoiceChips label="User type" options={roles} value={role} onChange={setRole} />
            <Field label="Username" value={username} onChangeText={setUsername} autoCapitalize="none" autoCorrect={false} textContentType="username" />
            <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry textContentType="password" onSubmitEditing={submit} />
            <Button label="Sign in" loading={submitting} onPress={submit} />
            <Button label="Create a new account" variant="ghost" onPress={() => router.push('/signup')} />
          </Card>
          <Button compact label="Back to home" variant="ghost" onPress={() => router.replace('/')} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.canvas },
  content: { flexGrow: 1, width: '100%', maxWidth: 610, alignSelf: 'center', justifyContent: 'center', padding: space.lg, gap: space.lg },
  brand: { alignItems: 'center' },
  card: { padding: space.xl, gap: space.lg },
  heading: { gap: 7 },
  eyebrow: { color: colors.primary, fontSize: 10, fontWeight: '900', letterSpacing: 1.5 },
  title: { color: colors.ink, fontSize: 32, fontWeight: '900', letterSpacing: -1 },
  body: { color: colors.muted, fontSize: 14, lineHeight: 21 },
});

