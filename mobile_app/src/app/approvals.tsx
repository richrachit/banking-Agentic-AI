import { AppPage } from '@/components/app-page';
import { Banner, Button, Card, EmptyState, Field, LoadingState, SectionTitle, StatusPill } from '@/components/ui';
import { colors, space } from '@/constants/app-theme';
import { useAuth } from '@/context/auth';
import { apiRequest, jsonBody } from '@/lib/api';
import type { Approval } from '@/lib/types';
import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

export default function ApprovalsScreen() {
  const { session } = useAuth();
  const [items, setItems] = useState<Approval[]>([]);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const load = useCallback(async () => {
    if (!session) return;
    setLoading(true);
    setError('');
    try {
      setItems(await apiRequest('/api/v1/approvals', {}, session.accessToken));
    } catch (value) {
      setError(value instanceof Error ? value.message : 'Approvals could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [session]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const decide = async (approval: Approval, decision: 'APPROVED' | 'REJECTED') => {
    if (!session) return;
    setBusy(`${approval.approval_id}:${decision}`);
    setError('');
    setMessage('');
    try {
      await apiRequest(`/api/v1/approvals/${encodeURIComponent(approval.approval_id)}/decision`, {
        method: 'POST', ...jsonBody({ decision, note: notes[approval.approval_id] || '' }),
      }, session.accessToken);
      setMessage(`${approval.approval_id} was ${decision.toLowerCase()} and recorded in the audit trail.`);
      await load();
    } catch (value) {
      setError(value instanceof Error ? value.message : 'Decision could not be recorded.');
    } finally {
      setBusy('');
    }
  };

  const canDecide = session && ['CREDIT', 'COMPLIANCE', 'ADMIN'].includes(session.user.role);
  return (
    <AppPage roles={['LOAN', 'CREDIT', 'COMPLIANCE', 'ADMIN']}>
      <SectionTitle eyebrow="MAKER-CHECKER CONTROL" title="Approval workbench" body="Review the agent-assembled context and record an accountable human decision." />
      <Banner body="AI can gather evidence and recommend a route. This page records the authorised approver, decision, and note before a deviation or transfer proceeds." />
      {error ? <Banner tone="error" body={error} /> : null}
      {message ? <Banner tone="success" body={message} /> : null}
      {loading ? <LoadingState label="Loading approval queue…" /> : items.length ? (
        <View style={styles.list}>
          {items.map((approval) => (
            <Card style={styles.card} key={approval.approval_id}>
              <View style={styles.topRow}>
                <View style={styles.main}>
                  <Text style={styles.id}>{approval.approval_id}</Text>
                  <Text style={styles.kind}>{approval.kind.replaceAll('_', ' ')}</Text>
                  <Text style={styles.meta}>Entity {approval.entity_id} · Authority {approval.required_role}</Text>
                </View>
                <StatusPill value={approval.status} />
              </View>
              <View style={styles.package}>
                <Text style={styles.packageLabel}>AGENT-ASSEMBLED CONTEXT</Text>
                {Object.entries(approval.package).slice(0, 8).map(([key, value]) => (
                  <View key={key} style={styles.packageRow}>
                    <Text style={styles.packageKey}>{key.replaceAll('_', ' ')}</Text>
                    <Text style={styles.packageValue}>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</Text>
                  </View>
                ))}
              </View>
              {approval.status === 'PENDING' && canDecide ? (
                <View style={styles.actions}>
                  <Field label="Decision note" hint="Add evidence or rationale for a defensible audit trail." value={notes[approval.approval_id] || ''} onChangeText={(value) => setNotes((current) => ({ ...current, [approval.approval_id]: value }))} multiline />
                  <View style={styles.buttonRow}>
                    <Button label="Reject" variant="danger" loading={busy === `${approval.approval_id}:REJECTED`} onPress={() => decide(approval, 'REJECTED')} />
                    <Button label="Approve" loading={busy === `${approval.approval_id}:APPROVED`} onPress={() => decide(approval, 'APPROVED')} />
                  </View>
                </View>
              ) : null}
              {approval.status !== 'PENDING' ? <Text style={styles.decided}>Decided by {approval.decision_by || 'authorised user'} · {approval.decision_note || 'No note recorded'}</Text> : null}
            </Card>
          ))}
        </View>
      ) : <EmptyState title="Approval queue is clear" body="New credit deviations, reactivation requests, and unclaimed-balance transfers will appear here when they need your role." />}
    </AppPage>
  );
}

const styles = StyleSheet.create({
  list: { gap: 12 },
  card: { gap: space.lg },
  topRow: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 },
  main: { flex: 1, gap: 4 },
  id: { color: colors.primary, fontSize: 11, fontWeight: '900', letterSpacing: 0.7 },
  kind: { color: colors.ink, fontSize: 18, fontWeight: '900' },
  meta: { color: colors.muted, fontSize: 12 },
  package: { borderRadius: 12, backgroundColor: colors.canvas, padding: 14, gap: 8 },
  packageLabel: { color: colors.primary, fontWeight: '900', letterSpacing: 1, fontSize: 9 },
  packageRow: { flexDirection: 'row', gap: 12, justifyContent: 'space-between', borderTopWidth: 1, borderTopColor: colors.line, paddingTop: 7 },
  packageKey: { color: colors.muted, fontSize: 11, fontWeight: '800', textTransform: 'capitalize', flex: 0.45 },
  packageValue: { color: colors.ink, fontSize: 11, lineHeight: 16, fontWeight: '700', flex: 0.55, textAlign: 'right' },
  actions: { gap: 12 },
  buttonRow: { flexDirection: 'row', justifyContent: 'flex-end', gap: 9, flexWrap: 'wrap' },
  decided: { color: colors.muted, fontSize: 12, fontStyle: 'italic' },
});

