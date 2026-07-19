import { Brand, Button, Card, LoadingState } from '@/components/ui';
import { colors, radius, space } from '@/constants/app-theme';
import { useAuth } from '@/context/auth';
import { Redirect, useRouter } from 'expo-router';
import { ScrollView, StyleSheet, Text, useWindowDimensions, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

const capabilities = [
  ['01', 'Loan exception resolution', 'AI diagnoses document, verification, and policy exceptions, then routes only the decisions that require human authority.'],
  ['02', 'Consent-led credit assessment', 'The score is fetched from the configured bureau provider after explicit consent. Customers never type or alter the score.'],
  ['03', 'Dormancy lifecycle', 'Customers can see eligible dormant accounts and submit KYC-backed reactivation requests with a complete approval trail.'],
];

export default function HomeScreen() {
  const { session, loading } = useAuth();
  const router = useRouter();
  const { width } = useWindowDimensions();
  if (loading) return <SafeAreaView style={styles.safe}><LoadingState /></SafeAreaView>;
  if (session) return <Redirect href="/dashboard" />;

  const wide = width >= 820;
  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.topbar}>
          <Brand />
          <View style={styles.topActions}>
            <Button compact label="Log in" variant="ghost" onPress={() => router.push('/login')} />
            {wide ? <Button compact label="Create account" onPress={() => router.push('/signup')} /> : null}
          </View>
        </View>

        <View style={[styles.hero, wide && styles.heroWide]}>
          <View style={styles.heroCopy}>
            <View style={styles.trustPill}><Text style={styles.trustText}>HUMAN-GOVERNED AGENTIC BANKING</Text></View>
            <Text style={[styles.heroTitle, wide && styles.heroTitleWide]}>Move banking exceptions from waiting to resolved.</Text>
            <Text style={styles.heroBody}>
              One secure workspace for customer applications, explainable AI decisions, human approvals, document evidence, and dormant-account service.
            </Text>
            <View style={styles.heroActions}>
              <Button label="Start an application" onPress={() => router.push('/signup')} />
              <Button label="Sign in to workspace" variant="secondary" onPress={() => router.push('/login')} />
            </View>
            <View style={styles.assuranceRow}>
              <Text style={styles.assurance}>✓ Explicit bureau consent</Text>
              <Text style={styles.assurance}>✓ Role-scoped data</Text>
              <Text style={styles.assurance}>✓ Auditable decisions</Text>
            </View>
          </View>
          <Card style={styles.heroPanel}>
            <Text style={styles.panelEyebrow}>LIVE WORKFLOW VIEW</Text>
            <Text style={styles.panelTitle}>Application assessment</Text>
            {['Application submitted', 'Bureau score retrieved', 'AI document review', 'Human review when required'].map((item, index) => (
              <View style={styles.flowRow} key={item}>
                <View style={[styles.flowDot, index < 2 && styles.flowDotDone]}><Text style={styles.flowDotText}>{index < 2 ? '✓' : index + 1}</Text></View>
                <View style={styles.flowCopy}>
                  <Text style={styles.flowTitle}>{item}</Text>
                  <Text style={styles.flowMeta}>{index < 2 ? 'Completed' : index === 2 ? 'AI agent active' : 'Policy controlled'}</Text>
                </View>
              </View>
            ))}
            <View style={styles.decisionStrip}>
              <Text style={styles.decisionLabel}>AUTOMATION BOUNDARY</Text>
              <Text style={styles.decisionText}>Exceptions and money movement remain governed by bank policy and approval roles.</Text>
            </View>
          </Card>
        </View>

        <View style={[styles.capabilityGrid, wide && styles.capabilityGridWide]}>
          {capabilities.map(([number, title, body]) => (
            <Card style={styles.capability} key={number}>
              <Text style={styles.capabilityNumber}>{number}</Text>
              <Text style={styles.capabilityTitle}>{title}</Text>
              <Text style={styles.capabilityBody}>{body}</Text>
            </Card>
          ))}
        </View>
        <Text style={styles.footer}>Banking Operations AI · Local demonstration client · Android, iOS, and web</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.canvas },
  content: { width: '100%', maxWidth: 1180, alignSelf: 'center', padding: space.lg, paddingBottom: 48, gap: 34 },
  topbar: { minHeight: 64, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  topActions: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  hero: { backgroundColor: colors.primaryDark, borderRadius: radius.lg, padding: space.xl, gap: 28, overflow: 'hidden' },
  heroWide: { minHeight: 520, flexDirection: 'row', alignItems: 'center', padding: 48 },
  heroCopy: { flex: 1, gap: 18 },
  trustPill: { alignSelf: 'flex-start', backgroundColor: 'rgba(255,255,255,0.1)', borderColor: 'rgba(255,255,255,0.22)', borderWidth: 1, borderRadius: radius.pill, paddingHorizontal: 13, paddingVertical: 8 },
  trustText: { color: '#BDE7E3', fontSize: 10, letterSpacing: 1.2, fontWeight: '900' },
  heroTitle: { color: colors.white, fontSize: 39, lineHeight: 44, fontWeight: '900', letterSpacing: -1.5 },
  heroTitleWide: { fontSize: 54, lineHeight: 58 },
  heroBody: { color: '#D6E5E5', fontSize: 17, lineHeight: 26, maxWidth: 620 },
  heroActions: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  assuranceRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 15 },
  assurance: { color: '#BDE7E3', fontSize: 12, fontWeight: '700' },
  heroPanel: { flex: 0.72, minWidth: 280, padding: 24, gap: 15, shadowOpacity: 0 },
  panelEyebrow: { color: colors.primary, fontWeight: '900', letterSpacing: 1.2, fontSize: 10 },
  panelTitle: { color: colors.ink, fontSize: 22, fontWeight: '900', marginBottom: 4 },
  flowRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  flowDot: { width: 31, height: 31, borderRadius: 16, backgroundColor: colors.infoSoft, alignItems: 'center', justifyContent: 'center' },
  flowDotDone: { backgroundColor: colors.primarySoft },
  flowDotText: { color: colors.primary, fontWeight: '900', fontSize: 12 },
  flowCopy: { flex: 1, gap: 2 },
  flowTitle: { color: colors.ink, fontWeight: '800', fontSize: 13 },
  flowMeta: { color: colors.muted, fontSize: 11 },
  decisionStrip: { backgroundColor: colors.accentSoft, borderRadius: radius.sm, padding: 13, gap: 4, marginTop: 4 },
  decisionLabel: { color: colors.warning, fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  decisionText: { color: colors.ink, fontSize: 12, lineHeight: 17 },
  capabilityGrid: { gap: 12 },
  capabilityGridWide: { flexDirection: 'row' },
  capability: { flex: 1, gap: 10, minHeight: 205 },
  capabilityNumber: { color: colors.accent, fontSize: 12, fontWeight: '900', letterSpacing: 1 },
  capabilityTitle: { color: colors.ink, fontSize: 20, lineHeight: 25, fontWeight: '900' },
  capabilityBody: { color: colors.muted, fontSize: 14, lineHeight: 21 },
  footer: { textAlign: 'center', color: colors.muted, fontSize: 11 },
});

