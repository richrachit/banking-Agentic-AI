import { AppPage } from '@/components/app-page';
import { Banner, Button, Card, EmptyState, LoadingState, SectionTitle, StatusPill, formatMoney } from '@/components/ui';
import { colors, space } from '@/constants/app-theme';
import { useAuth } from '@/context/auth';
import { apiRequest } from '@/lib/api';
import type { LoanApplication } from '@/lib/types';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

export default function LoansScreen() {
  const { session } = useAuth();
  const router = useRouter();
  const [items, setItems] = useState<LoanApplication[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!session) return;
    setLoading(true);
    setError('');
    try {
      setItems(await apiRequest('/api/v1/loan-applications', {}, session.accessToken));
    } catch (value) {
      setError(value instanceof Error ? value.message : 'Applications could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [session]);

  useFocusEffect(useCallback(() => { load(); }, [load]));
  const visible = useMemo(() => {
    const key = query.trim().toLowerCase();
    if (!key) return items;
    return items.filter((item) => [item.application_id, item.applicant_name, item.loan_product, item.status].some((value) => value.toLowerCase().includes(key)));
  }, [items, query]);

  return (
    <AppPage roles={['CUSTOMER', 'LOAN', 'CREDIT', 'ADMIN']}>
      <View style={styles.headingRow}>
        <SectionTitle eyebrow="LOAN ORIGINATION" title="Applications" body="Track assessment, exception resolution, approvals, and customer evidence from one queue." />
        {session?.user.role === 'CUSTOMER' ? <Button label="New application" onPress={() => router.push('/loans/new')} /> : null}
      </View>
      {error ? <Banner tone="error" body={error} /> : null}
      <TextInput
        accessibilityLabel="Search applications"
        value={query}
        onChangeText={setQuery}
        placeholder="Search by application, applicant, product, or status"
        placeholderTextColor="#8AA0B4"
        style={styles.search}
      />
      {loading ? <LoadingState label="Loading applications…" /> : visible.length ? (
        <View style={styles.list}>
          {visible.slice().reverse().map((loan) => (
            <Pressable key={loan.application_id} onPress={() => router.push(`/loans/${loan.application_id}` as never)}>
              <Card style={styles.card}>
                <View style={styles.main}>
                  <Text style={styles.name}>{loan.applicant_name || 'Loan applicant'}</Text>
                  <Text style={styles.meta}>{loan.application_id} · {loan.loan_product.replaceAll('_', ' ')}</Text>
                  <Text style={styles.purpose} numberOfLines={2}>{loan.loan_purpose || loan.diagnosis || 'Assessment in progress'}</Text>
                </View>
                <View style={styles.end}>
                  <Text style={styles.amount}>{formatMoney(loan.requested_amount)}</Text>
                  <StatusPill value={loan.status} />
                  <Text style={styles.open}>Open →</Text>
                </View>
              </Card>
            </Pressable>
          ))}
        </View>
      ) : (
        <EmptyState title="No matching applications" body={query ? 'Try a different search term.' : 'Applications within your role scope will appear here.'} />
      )}
    </AppPage>
  );
}

const styles = StyleSheet.create({
  headingRow: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 },
  search: { minHeight: 50, borderRadius: 12, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.white, paddingHorizontal: 15, color: colors.ink, fontSize: 14 },
  list: { gap: 10 },
  card: { flexDirection: 'row', alignItems: 'center', gap: space.md, padding: 16 },
  main: { flex: 1, gap: 4 },
  name: { color: colors.ink, fontWeight: '900', fontSize: 16 },
  meta: { color: colors.primary, fontSize: 11, fontWeight: '800', letterSpacing: 0.3 },
  purpose: { color: colors.muted, fontSize: 13, lineHeight: 18, marginTop: 3 },
  end: { alignItems: 'flex-end', gap: 7 },
  amount: { color: colors.ink, fontWeight: '900', fontSize: 15 },
  open: { color: colors.primary, fontWeight: '800', fontSize: 11 },
});
