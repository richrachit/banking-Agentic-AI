import { AppPage } from '@/components/app-page';
import { Banner, Button, Card, CheckRow, EmptyState, LoadingState, SectionTitle, StatusPill, formatMoney } from '@/components/ui';
import { colors, space } from '@/constants/app-theme';
import { useAuth } from '@/context/auth';
import { apiRequest, jsonBody } from '@/lib/api';
import type { Account } from '@/lib/types';
import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

export default function AccountsScreen() {
  const { session } = useAuth();
  const [items, setItems] = useState<Account[]>([]);
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const load = useCallback(async () => {
    if (!session) return;
    setLoading(true);
    setError('');
    try {
      setItems(await apiRequest('/api/v1/accounts', {}, session.accessToken));
    } catch (value) {
      setError(value instanceof Error ? value.message : 'Accounts could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [session]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const reactivate = async (accountId: string) => {
    if (!session) return;
    setBusy(accountId);
    setError('');
    setMessage('');
    try {
      await apiRequest(`/api/v1/accounts/${encodeURIComponent(accountId)}/reactivation-requests`, {
        method: 'POST', ...jsonBody({ kyc_confirmed: Boolean(confirmed[accountId]) }),
      }, session.accessToken);
      setMessage(`Reactivation request for ${accountId} was sent to Compliance for approval.`);
    } catch (value) {
      setError(value instanceof Error ? value.message : 'Reactivation request failed.');
    } finally {
      setBusy('');
    }
  };

  return (
    <AppPage roles={['CUSTOMER', 'COMPLIANCE', 'ADMIN']}>
      <SectionTitle eyebrow="DORMANCY & UNCLAIMED BALANCES" title="Dormant accounts" body="A role-scoped view of statutory status, outreach, transfer timelines, and customer reactivation." />
      <Banner title="Human control is retained" body="Reactivation requests require current KYC confirmation and compliance approval. Unclaimed-balance transfers are executed only after the authorised maker-checker decision." />
      {error ? <Banner tone="error" body={error} /> : null}
      {message ? <Banner tone="success" body={message} /> : null}
      {loading ? <LoadingState label="Loading dormant-account data…" /> : items.length ? (
        <View style={styles.list}>
          {items.map((account) => (
            <Card style={styles.card} key={account.account_id}>
              <View style={styles.topRow}>
                <View style={styles.main}>
                  <Text style={styles.accountId}>{account.account_id}</Text>
                  <Text style={styles.jurisdiction}>{account.jurisdiction} · Customer {account.customer_id}</Text>
                </View>
                <View style={styles.end}>
                  <Text style={styles.balance}>{formatMoney(account.balance)}</Text>
                  <StatusPill value={account.status} />
                </View>
              </View>
              <View style={styles.dataGrid}>
                <Info label="Last customer activity" value={account.last_customer_activity} />
                <Info label="Dormant on" value={account.dormant_on || 'Not classified'} />
                <Info label="Transfer due" value={account.transfer_due_on || 'Not scheduled'} />
                <Info label="Outreach" value={account.outreach_sent ? 'Sent' : 'Not yet sent'} />
                {account.transferred_amount > 0 ? <Info label="Transferred" value={formatMoney(account.transferred_amount)} /> : null}
              </View>
              {session?.user.role === 'CUSTOMER' && ['DORMANT', 'OUTREACH', 'TRANSFER_PENDING'].includes(account.status) ? (
                <View style={styles.actionBox}>
                  <CheckRow
                    checked={Boolean(confirmed[account.account_id])}
                    onChange={(value) => setConfirmed((current) => ({ ...current, [account.account_id]: value }))}
                    title="I confirm my KYC details are current"
                    body="Compliance will review the request before the account status changes."
                  />
                  <Button
                    label="Request reactivation"
                    loading={busy === account.account_id}
                    disabled={!confirmed[account.account_id]}
                    onPress={() => reactivate(account.account_id)}
                  />
                </View>
              ) : null}
            </Card>
          ))}
        </View>
      ) : (
        <EmptyState title="No accounts in this view" body="Dormant accounts within your customer or compliance scope will appear here." />
      )}
    </AppPage>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return <View style={styles.info}><Text style={styles.infoLabel}>{label}</Text><Text style={styles.infoValue}>{value}</Text></View>;
}

const styles = StyleSheet.create({
  list: { gap: 12 },
  card: { gap: space.lg },
  topRow: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 },
  main: { flex: 1, gap: 4 },
  accountId: { color: colors.ink, fontSize: 18, fontWeight: '900' },
  jurisdiction: { color: colors.muted, fontSize: 12 },
  end: { alignItems: 'flex-end', gap: 7 },
  balance: { color: colors.ink, fontSize: 18, fontWeight: '900' },
  dataGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  info: { minWidth: 150, flexGrow: 1, flexBasis: '28%', borderTopWidth: 1, borderTopColor: colors.line, paddingTop: 9, gap: 3 },
  infoLabel: { color: colors.muted, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.6 },
  infoValue: { color: colors.ink, fontSize: 13, fontWeight: '800' },
  actionBox: { gap: 10, backgroundColor: colors.canvas, borderRadius: 12, padding: 12 },
});
