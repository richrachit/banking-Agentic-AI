import { AppPage } from '@/components/app-page';
import { Banner, Button, Card, EmptyState, LoadingState, SectionTitle, StatusPill } from '@/components/ui';
import { colors, radius, shadows, space } from '@/constants/app-theme';
import { useAuth } from '@/context/auth';
import { apiRequest, jsonBody } from '@/lib/api';
import type { AgentSetting, AgentSettingsResponse } from '@/lib/types';
import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Animated, Modal, StyleSheet, Switch, Text, View } from 'react-native';

type PendingChange = {
  agent: AgentSetting;
  enabled: boolean;
};

function formatChangeTimestamp(value: string | null) {
  if (!value) return 'Default configuration';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export default function AgentSettingsScreen() {
  const { session } = useAuth();
  const [data, setData] = useState<AgentSettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyKey, setBusyKey] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [pendingChange, setPendingChange] = useState<PendingChange | null>(null);
  const [pulse] = useState(() => new Animated.Value(0));

  useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 1200, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0, duration: 1200, useNativeDriver: true }),
      ]),
    );
    animation.start();
    return () => animation.stop();
  }, [pulse]);

  const load = useCallback(async () => {
    if (!session) return;
    setLoading(true);
    setError('');
    try {
      setData(await apiRequest<AgentSettingsResponse>('/api/v1/ai/agents', {}, session.accessToken));
    } catch (value) {
      setError(value instanceof Error ? value.message : 'AI agent settings could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [session]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const confirmChange = async () => {
    if (!session || !pendingChange) return;
    const { agent, enabled } = pendingChange;
    setBusyKey(agent.model_key);
    setError('');
    setMessage('');
    try {
      const updated = await apiRequest<AgentSetting>(
        `/api/v1/ai/agents/${encodeURIComponent(agent.model_key)}/settings`,
        { method: 'POST', ...jsonBody({ enabled }) },
        session.accessToken,
      );
      setData((current) => current ? {
        ...current,
        agents: current.agents.map((item) => item.model_key === updated.model_key ? updated : item),
      } : current);
      setMessage(`${updated.display_name} is now ${updated.enabled ? 'enabled' : 'disabled'}. This change is recorded in the audit trail.`);
      setPendingChange(null);
    } catch (value) {
      setError(value instanceof Error ? value.message : 'The agent setting could not be updated.');
    } finally {
      setBusyKey('');
    }
  };

  const enabledCount = data?.agents.filter((agent) => agent.enabled).length ?? 0;
  const pulseStyle = {
    opacity: pulse.interpolate({ inputRange: [0, 1], outputRange: [0.35, 1] }),
    transform: [{ scale: pulse.interpolate({ inputRange: [0, 1], outputRange: [0.88, 1.12] }) }],
  };

  return (
    <AppPage roles={['ADMIN']}>
      <View style={styles.headingRow}>
        <SectionTitle
          eyebrow="AI OPERATING CONTROLS"
          title="Agent settings"
          body="Enable or disable individual AI components. A disabled agent fails closed: its dependent workflow cannot silently bypass the control." />
        <View style={styles.liveStatus}>
          <Animated.View style={[styles.liveDot, pulseStyle]} />
          <Text style={styles.liveText}>{enabledCount} active</Text>
        </View>
      </View>

      <Banner
        title="Human-governed configuration"
        body="Changes take effect through the API and are attributable to the signed-in administrator. Enabling an agent does not grant it authority to approve credit, move funds, or override a required human decision." />
      {error ? <Banner tone="error" body={error} /> : null}
      {message ? <Banner tone="success" body={message} /> : null}

      {loading ? <LoadingState label="Loading AI agent controls…" /> : data?.agents.length ? (
        <View style={styles.list}>
          {data.chatbotTraining ? <ChatbotTrainingCard data={data.chatbotTraining} /> : null}
          {data.agents.map((agent) => (
            <Card key={agent.model_key} style={[styles.agentCard, !agent.enabled && styles.agentCardDisabled]}>
              <View style={styles.agentTopRow}>
                <View style={styles.agentTitleBlock}>
                  <Text style={styles.agentKey}>{agent.model_key.replaceAll('_', ' ')}</Text>
                  <Text style={styles.agentName}>{agent.display_name}</Text>
                  <Text style={styles.agentMeta}>{agent.component_type.replaceAll('_', ' ')} · {agent.risk_tier} risk</Text>
                </View>
                <View style={styles.toggleBlock}>
                  <StatusPill value={agent.enabled ? 'ENABLED' : 'DISABLED'} />
                  <Switch
                    accessibilityLabel={`${agent.enabled ? 'Disable' : 'Enable'} ${agent.display_name}`}
                    accessibilityHint="Opens a confirmation before changing this AI agent setting."
                    value={agent.enabled}
                    disabled={busyKey === agent.model_key}
                    onValueChange={(enabled) => setPendingChange({ agent, enabled })}
                    trackColor={{ false: '#CBD5E1', true: '#8DCECA' }}
                    thumbColor={agent.enabled ? colors.primary : '#FFFFFF'}
                  />
                </View>
              </View>

              <View style={styles.boundary}>
                <Text style={styles.boundaryLabel}>AUTHORITY BOUNDARY</Text>
                <Text style={styles.boundaryText}>{agent.authority_boundary}</Text>
              </View>
              <View style={styles.agentFooter}>
                <Text style={styles.footerText}>{agent.training_supported ? 'Governed training supported' : 'Deterministic or external control'}</Text>
                <Text style={styles.footerText}>{formatChangeTimestamp(agent.changed_at)}{agent.changed_by ? ` · ${agent.changed_by}` : ''}</Text>
              </View>
            </Card>
          ))}
        </View>
      ) : <EmptyState title="No AI agents are registered" body="Build or synchronize the local training and configuration database, then reopen this page." />}

      <Modal
        transparent
        animationType="fade"
        visible={Boolean(pendingChange)}
        onRequestClose={() => busyKey ? undefined : setPendingChange(null)}
        statusBarTranslucent>
        <View style={styles.modalBackdrop}>
          <View accessibilityViewIsModal style={styles.modalCard}>
            <View style={[styles.modalIcon, pendingChange?.enabled ? styles.modalIconEnable : styles.modalIconDisable]}>
              <Text style={[styles.modalIconText, pendingChange?.enabled ? styles.modalIconTextEnable : styles.modalIconTextDisable]}>{pendingChange?.enabled ? '✓' : '!'}</Text>
            </View>
            <Text style={styles.modalTitle}>{pendingChange?.enabled ? 'Enable AI agent?' : 'Disable AI agent?'}</Text>
            <Text style={styles.modalBody}>
              {pendingChange?.enabled
                ? `${pendingChange.agent.display_name} will be available to its dependent workflow.`
                : `${pendingChange?.agent.display_name} will fail closed. Its dependent workflow will be unavailable until an administrator enables it again.`}
            </Text>
            <View style={styles.modalActions}>
              <Button label="Cancel" variant="ghost" disabled={Boolean(busyKey)} onPress={() => setPendingChange(null)} style={styles.modalAction} />
              <Button
                label={pendingChange?.enabled ? 'Enable agent' : 'Disable agent'}
                variant={pendingChange?.enabled ? 'primary' : 'danger'}
                loading={Boolean(busyKey)}
                onPress={confirmChange}
                style={styles.modalAction}
              />
            </View>
          </View>
        </View>
      </Modal>
    </AppPage>
  );
}

function ChatbotTrainingCard({ data }: { data: NonNullable<AgentSettingsResponse['chatbotTraining']> }) {
  const intentCount = Object.keys(data.intent_counts || {}).length;
  const latestRun = data.latest_run;
  const metrics = latestRun?.metrics || {};
  const accuracy = typeof metrics.accuracy === 'number' ? `${Math.round(metrics.accuracy * 100)}%` : null;
  return (
    <Card style={styles.trainingCard}>
      <View style={styles.trainingTop}>
        <View>
          <Text style={styles.trainingEyebrow}>CHATBOT TRAINING</Text>
          <Text style={styles.trainingTitle}>Support assistant readiness</Text>
        </View>
        <StatusPill value={latestRun?.status || 'NOT TRAINED'} />
      </View>
      <Text style={styles.trainingBody}>{data.training_data_policy || 'Only governed, curated support examples are used for local model training. Customer chat text is not retained as training data.'}</Text>
      <View style={styles.trainingMetrics}>
        <TrainingMetric label="Curated examples" value={data.sample_count} />
        <TrainingMetric label="Intent classes" value={intentCount} />
        <TrainingMetric label="Latest run samples" value={latestRun?.sample_count} />
        <TrainingMetric label="Validation accuracy" value={accuracy || '—'} />
      </View>
      {latestRun ? <Text style={styles.latestRun}>Latest run: {latestRun.status || 'Recorded'}{latestRun.trained_at ? ` · ${formatChangeTimestamp(latestRun.trained_at)}` : ''}</Text> : null}
      {data.database ? <Text style={styles.trainingLocation}>Local training database: {data.database}</Text> : null}
    </Card>
  );
}

function TrainingMetric({ label, value }: { label: string; value?: number | string }) {
  return <View style={styles.trainingMetric}><Text style={styles.trainingMetricValue}>{value ?? '—'}</Text><Text style={styles.trainingMetricLabel}>{label}</Text></View>;
}

const styles = StyleSheet.create({
  headingRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 },
  liveStatus: { flexDirection: 'row', alignItems: 'center', gap: 8, borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: colors.primarySoft, borderWidth: 1, borderColor: '#BEE5E1' },
  liveDot: { width: 9, height: 9, borderRadius: 5, backgroundColor: colors.success },
  liveText: { color: colors.primaryDark, fontSize: 11, fontWeight: '900', textTransform: 'uppercase', letterSpacing: 0.7 },
  list: { gap: 12 },
  trainingCard: { gap: 12, backgroundColor: '#F1FBFA', borderColor: '#BEE5E1' },
  trainingTop: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 },
  trainingEyebrow: { color: colors.primary, fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  trainingTitle: { color: colors.ink, fontSize: 18, fontWeight: '900', marginTop: 4 },
  trainingBody: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  trainingMetrics: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  trainingMetric: { minWidth: 90, flexGrow: 1, padding: 10, borderRadius: radius.sm, backgroundColor: colors.surface },
  trainingMetricValue: { color: colors.ink, fontSize: 18, fontWeight: '900' },
  trainingMetricLabel: { color: colors.muted, fontSize: 9, fontWeight: '800', textTransform: 'uppercase', marginTop: 2 },
  latestRun: { color: colors.primaryDark, fontSize: 11, fontWeight: '700' },
  trainingLocation: { color: colors.muted, fontSize: 10, lineHeight: 15 },
  agentCard: { gap: 14 },
  agentCardDisabled: { backgroundColor: '#FBFCFD', borderColor: '#D7DEE7' },
  agentTopRow: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 14 },
  agentTitleBlock: { flex: 1, gap: 4 },
  agentKey: { color: colors.primary, fontSize: 9, fontWeight: '900', letterSpacing: 0.9, textTransform: 'uppercase' },
  agentName: { color: colors.ink, fontSize: 18, fontWeight: '900' },
  agentMeta: { color: colors.muted, fontSize: 11, lineHeight: 16, textTransform: 'capitalize' },
  toggleBlock: { alignItems: 'flex-end', gap: 7 },
  boundary: { borderRadius: radius.sm, backgroundColor: colors.canvas, padding: 12, gap: 4 },
  boundaryLabel: { color: colors.primary, fontSize: 9, fontWeight: '900', letterSpacing: 0.9 },
  boundaryText: { color: colors.ink, fontSize: 12, lineHeight: 18, fontWeight: '600' },
  agentFooter: { borderTopWidth: 1, borderTopColor: colors.line, paddingTop: 11, gap: 3 },
  footerText: { color: colors.muted, fontSize: 11, lineHeight: 16 },
  modalBackdrop: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.lg, backgroundColor: 'rgba(7, 28, 44, 0.54)' },
  modalCard: { width: '100%', maxWidth: 420, alignItems: 'center', gap: 11, padding: space.xl, borderRadius: radius.lg, backgroundColor: colors.surface, ...shadows.card },
  modalIcon: { width: 46, height: 46, borderRadius: 23, alignItems: 'center', justifyContent: 'center' },
  modalIconEnable: { backgroundColor: colors.primarySoft },
  modalIconDisable: { backgroundColor: colors.dangerSoft },
  modalIconText: { fontSize: 22, fontWeight: '900' },
  modalIconTextEnable: { color: colors.primary },
  modalIconTextDisable: { color: colors.danger },
  modalTitle: { color: colors.ink, fontSize: 20, fontWeight: '900', textAlign: 'center' },
  modalBody: { color: colors.muted, fontSize: 13, lineHeight: 20, textAlign: 'center' },
  modalActions: { flexDirection: 'row', alignSelf: 'stretch', gap: 9, marginTop: 5 },
  modalAction: { flex: 1 },
});
