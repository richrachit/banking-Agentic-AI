import { AppPage } from '@/components/app-page';
import { Banner, Button, Card, EmptyState, LoadingState, Metric, SectionTitle, StatusPill, formatMoney, roleLabels } from '@/components/ui';
import { colors, space } from '@/constants/app-theme';
import { useAuth } from '@/context/auth';
import { apiRequest } from '@/lib/api';
import type { Dashboard } from '@/lib/types';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, StyleSheet, Text, useWindowDimensions, View } from 'react-native';

export default function DashboardScreen() {
  const { session } = useAuth();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (!session) return;
    setRefreshing(true);
    setError('');
    try {
      setData(await apiRequest<Dashboard>('/api/v1/me/dashboard', {}, session.accessToken));
    } catch (value) {
      setError(value instanceof Error ? value.message : 'Dashboard could not be loaded.');
    } finally {
      setRefreshing(false);
    }
  }, [session]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  return (
    <AppPage>
      <View style={styles.titleRow}>
        <SectionTitle
          eyebrow={session ? roleLabels[session.user.role].toUpperCase() : 'WORKSPACE'}
          title={`Good to see you, ${session?.user.display_name || ''}`}
          body="Your role-aware view of applications, approvals, and customer actions." />
        <Button compact label="Refresh" variant="secondary" loading={refreshing} onPress={load} />
      </View>
      {error ? <Banner tone="error" body={error} /> : null}
      {!data && refreshing ? <LoadingState /> : null}
      {data ? (
        <>
          <View style={[styles.metrics, width >= 720 && styles.metricsWide]}>
            <Metric label="Loan applications" value={data.metrics.loanApplications} note="Visible to your role" />
            <Metric label="Dormant accounts" value={data.metrics.accounts} note="Within your service scope" />
            <Metric label="Pending approvals" value={data.metrics.pendingApprovals} note="Awaiting an authorised decision" />
          </View>

          {data.recentApplications.length ? (
            <View style={styles.section}>
              <View style={styles.sectionRow}>
                <Text style={styles.sectionHeading}>Recent loan applications</Text>
                <Button compact label="View all" variant="ghost" onPress={() => router.push('/loans')} />
              </View>
              <View style={styles.list}>
                {data.recentApplications.slice().reverse().slice(0, 5).map((loan) => (
                  <Pressable key={loan.application_id} onPress={() => router.push(`/loans/${loan.application_id}` as never)}>
                    <Card style={styles.rowCard}>
                      <View style={styles.rowMain}>
                        <Text style={styles.rowTitle}>{loan.applicant_name || loan.application_id}</Text>
                        <Text style={styles.rowMeta}>{loan.application_id} · {loan.loan_product.replaceAll('_', ' ')}</Text>
                      </View>
                      <View style={styles.rowEnd}>
                        <Text style={styles.amount}>{formatMoney(loan.requested_amount)}</Text>
                        <StatusPill value={loan.status} />
                      </View>
                    </Card>
                  </Pressable>
                ))}
              </View>
            </View>
          ) : (
            <EmptyState
              title="No loan applications yet"
              body={session?.user.role === 'CUSTOMER' ? 'Create your first application. The application ID will be generated securely by the server.' : 'Applications visible to your role will appear here.'}
              action={session?.user.role === 'CUSTOMER' ? <Button label="Start application" onPress={() => router.push('/loans/new')} /> : undefined}
            />
          )}

          {data.pendingActions.length ? (
            <View style={styles.section}>
              <View style={styles.sectionRow}>
                <Text style={styles.sectionHeading}>Pending decisions</Text>
                <Button compact label="Open approvals" variant="ghost" onPress={() => router.push('/approvals')} />
              </View>
              <Banner body={`${data.pendingActions.length} item${data.pendingActions.length === 1 ? '' : 's'} require an authorised review. AI recommendations do not replace the recorded human decision.`} />
            </View>
          ) : null}
        </>
      ) : null}
    </AppPage>
  );
}

const styles = StyleSheet.create({
  titleRow: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 },
  metrics: { gap: 12 },
  metricsWide: { flexDirection: 'row' },
  section: { gap: 12 },
  sectionRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  sectionHeading: { color: colors.ink, fontSize: 18, fontWeight: '900' },
  list: { gap: 9 },
  rowCard: { flexDirection: 'row', alignItems: 'center', gap: space.md, padding: 15 },
  rowMain: { flex: 1, gap: 4 },
  rowTitle: { color: colors.ink, fontWeight: '900', fontSize: 15 },
  rowMeta: { color: colors.muted, fontSize: 12 },
  rowEnd: { alignItems: 'flex-end', gap: 7 },
  amount: { color: colors.ink, fontWeight: '900', fontSize: 14 },
});

