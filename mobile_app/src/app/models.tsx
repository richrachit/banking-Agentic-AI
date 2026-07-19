import { AppPage } from '@/components/app-page';
import { Banner, Card, EmptyState, LoadingState, SectionTitle, StatusPill } from '@/components/ui';
import { colors, space } from '@/constants/app-theme';
import { useAuth } from '@/context/auth';
import { apiRequest } from '@/lib/api';
import type { ModelRegistry } from '@/lib/types';
import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

export default function ModelsScreen() {
  const { session } = useAuth();
  const [data, setData] = useState<ModelRegistry | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!session) return;
    setLoading(true);
    setError('');
    try {
      setData(await apiRequest('/api/v1/ai/models', {}, session.accessToken));
    } catch (value) {
      setError(value instanceof Error ? value.message : 'Model registry could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [session]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  return (
    <AppPage roles={['ADMIN']}>
      <SectionTitle eyebrow="AI GOVERNANCE" title="Model registry" body="Inventory, training-data balance, lifecycle state, and decision authority for every automated component." />
      <Banner title="Advisory models only" body="Synthetic demo metrics are not production validation. Models must meet bank governance, human-label, drift, fairness, security, and approval requirements before they influence live decisions." />
      {error ? <Banner tone="error" body={error} /> : null}
      {loading ? <LoadingState label="Loading model governance data…" /> : data?.components.length ? (
        <View style={styles.list}>
          {data.components.map((model) => (
            <Card style={styles.card} key={model.model_key}>
              <View style={styles.topRow}>
                <View style={styles.main}>
                  <Text style={styles.key}>{model.model_key}</Text>
                  <Text style={styles.name}>{model.display_name}</Text>
                  <Text style={styles.meta}>{model.component_type.replaceAll('_', ' ')} · {model.implementation}</Text>
                </View>
                <StatusPill value={model.latest_run?.status || (model.training_supported ? 'NOT TRAINED' : model.risk_tier)} />
              </View>
              <View style={styles.metrics}>
                <ModelMetric label="Examples" value={model.examples.total} />
                <ModelMetric label="Positive" value={model.examples.positive} />
                <ModelMetric label="Negative" value={model.examples.negative} />
                <ModelMetric label="Human verified" value={model.examples.human_verified} />
                <ModelMetric label="Synthetic" value={model.examples.synthetic} />
              </View>
              <View style={styles.run}>
                <Text style={styles.runLabel}>LATEST RUN</Text>
                <Text style={styles.runValue}>{model.latest_run ? `${model.latest_run.status} · ${model.latest_run.algorithm}` : 'No training run recorded'}</Text>
                <Text style={styles.training}>{model.training_supported ? 'Training supported under governance controls' : 'Deterministic or external component — local training not applicable'}</Text>
                <Text style={styles.boundary}>Authority boundary: {model.authority_boundary}</Text>
              </View>
            </Card>
          ))}
        </View>
      ) : <EmptyState title="Registry has no entries" body="Build or synchronize the local model training database, then refresh this page." />}
    </AppPage>
  );
}

function ModelMetric({ label, value }: { label: string; value: number }) {
  return <View style={styles.metric}><Text style={styles.metricValue}>{value}</Text><Text style={styles.metricLabel}>{label}</Text></View>;
}

const styles = StyleSheet.create({
  list: { gap: 12 },
  card: { gap: space.lg },
  topRow: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 },
  main: { flex: 1, gap: 4 },
  key: { color: colors.primary, fontSize: 10, fontWeight: '900', letterSpacing: 0.7 },
  name: { color: colors.ink, fontSize: 18, fontWeight: '900' },
  meta: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  metrics: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  metric: { minWidth: 105, flexGrow: 1, backgroundColor: colors.canvas, borderRadius: 11, padding: 11, gap: 3 },
  metricValue: { color: colors.ink, fontSize: 21, fontWeight: '900' },
  metricLabel: { color: colors.muted, fontSize: 9, fontWeight: '800', textTransform: 'uppercase' },
  run: { gap: 5, borderTopWidth: 1, borderTopColor: colors.line, paddingTop: 12 },
  runLabel: { color: colors.primary, fontSize: 9, fontWeight: '900', letterSpacing: 0.8 },
  runValue: { color: colors.ink, fontSize: 13, fontWeight: '800' },
  training: { color: colors.muted, fontSize: 11, lineHeight: 16 },
  boundary: { color: colors.ink, fontSize: 11, lineHeight: 17, fontWeight: '700' },
});
