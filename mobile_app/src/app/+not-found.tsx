import { Button, Card } from '@/components/ui';
import { colors, space } from '@/constants/app-theme';
import { useRouter } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

export default function NotFoundScreen() {
  const router = useRouter();
  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.wrap}>
        <Card style={styles.card}>
          <Text style={styles.code}>404</Text>
          <Text style={styles.title}>This workspace page does not exist.</Text>
          <Text style={styles.body}>Return to your dashboard to continue with the banking workflow.</Text>
          <Button label="Go to dashboard" onPress={() => router.replace('/dashboard')} />
        </Card>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.canvas },
  wrap: { flex: 1, justifyContent: 'center', width: '100%', maxWidth: 560, alignSelf: 'center', padding: space.lg },
  card: { alignItems: 'center', gap: 14, padding: space.xxl },
  code: { color: colors.accent, fontWeight: '900', fontSize: 13, letterSpacing: 2 },
  title: { color: colors.ink, fontWeight: '900', fontSize: 25, textAlign: 'center' },
  body: { color: colors.muted, fontSize: 14, lineHeight: 21, textAlign: 'center' },
});

