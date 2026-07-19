import { Banner, Brand, Button, Card, ChoiceChips, Field, LoadingState, roleLabels } from '@/components/ui';
import { colors, space } from '@/constants/app-theme';
import { useAuth } from '@/context/auth';
import type { UserRole } from '@/lib/types';
import { Redirect, useRouter } from 'expo-router';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

const roles = (Object.keys(roleLabels) as UserRole[]).map((value) => ({ value, label: roleLabels[value] }));

export default function SignupScreen() {
  const { session, loading, signup } = useAuth();
  const router = useRouter();
  const [role, setRole] = useState<UserRole>('CUSTOMER');
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (loading) return <SafeAreaView style={styles.safe}><LoadingState /></SafeAreaView>;
  if (session) return <Redirect href="/dashboard" />;

  const submit = async () => {
    if (!displayName.trim() || !email.trim() || !username.trim()) return setError('Complete your name, email, and username.');
    if (password.length < 10) return setError('Password must contain at least 10 characters.');
    if (password !== confirm) return setError('Passwords do not match.');
    setSubmitting(true);
    setError('');
    try {
      await signup({ display_name: displayName.trim(), email: email.trim(), username: username.trim(), password, user_type: role });
      router.replace({ pathname: '/login', params: { created: '1' } });
    } catch (value) {
      setError(value instanceof Error ? value.message : 'Account creation failed.');
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
              <Text style={styles.eyebrow}>CREATE YOUR PROFILE</Text>
              <Text style={styles.title}>Join your banking workspace</Text>
              <Text style={styles.body}>Access is role-scoped after authentication. Production deployments should provision staff through the bank identity provider.</Text>
            </View>
            {error ? <Banner tone="error" body={error} /> : null}
            <ChoiceChips label="User type" options={roles} value={role} onChange={setRole} />
            <Field label="Full name" value={displayName} onChangeText={setDisplayName} autoCapitalize="words" textContentType="name" />
            <Field label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" textContentType="emailAddress" />
            <Field label="Username" value={username} onChangeText={setUsername} autoCapitalize="none" autoCorrect={false} />
            <Field label="Password" hint="Use at least 10 characters." value={password} onChangeText={setPassword} secureTextEntry textContentType="newPassword" />
            <Field label="Confirm password" value={confirm} onChangeText={setConfirm} secureTextEntry textContentType="newPassword" onSubmitEditing={submit} />
            <Button label="Create account" loading={submitting} onPress={submit} />
            <Button label="Already registered? Sign in" variant="ghost" onPress={() => router.replace('/login')} />
          </Card>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.canvas },
  content: { flexGrow: 1, width: '100%', maxWidth: 680, alignSelf: 'center', justifyContent: 'center', padding: space.lg, gap: space.lg },
  brand: { alignItems: 'center', marginTop: 16 },
  card: { padding: space.xl, gap: space.lg },
  heading: { gap: 7 },
  eyebrow: { color: colors.primary, fontSize: 10, fontWeight: '900', letterSpacing: 1.5 },
  title: { color: colors.ink, fontSize: 30, lineHeight: 36, fontWeight: '900', letterSpacing: -1 },
  body: { color: colors.muted, fontSize: 14, lineHeight: 21 },
});

