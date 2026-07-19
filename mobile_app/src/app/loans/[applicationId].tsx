import { AppPage } from '@/components/app-page';
import { Banner, Button, Card, EmptyState, Field, LoadingState, SectionTitle, StatusPill, formatMoney } from '@/components/ui';
import { colors, radius, space } from '@/constants/app-theme';
import { useAuth } from '@/context/auth';
import { apiRequest } from '@/lib/api';
import type { LoanDetail } from '@/lib/types';
import * as DocumentPicker from 'expo-document-picker';
import { useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useMemo, useState } from 'react';
import { Platform, StyleSheet, Text, useWindowDimensions, View } from 'react-native';

const standardDocuments = ['PAN', 'AADHAAR', 'ADDRESS_PROOF', 'BANK_STATEMENT', 'INCOME_PROOF', 'SALARY_SLIP', 'EMPLOYMENT_PROOF', 'INCOME_TAX_RETURN', 'PROPERTY_DOCUMENT', 'BUSINESS_REGISTRATION', 'FINANCIAL_STATEMENT'];

export default function LoanDetailScreen() {
  const { session } = useAuth();
  const params = useLocalSearchParams<{ applicationId: string | string[] }>();
  const applicationId = Array.isArray(params.applicationId) ? params.applicationId[0] : params.applicationId;
  const { width } = useWindowDimensions();
  const [detail, setDetail] = useState<LoanDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [reviewReason, setReviewReason] = useState('');
  const [disputeReference, setDisputeReference] = useState('');

  const load = useCallback(async () => {
    if (!session || !applicationId) return;
    setLoading(true);
    setError('');
    try {
      setDetail(await apiRequest(`/api/v1/loan-applications/${encodeURIComponent(applicationId)}`, {}, session.accessToken));
    } catch (value) {
      setError(value instanceof Error ? value.message : 'Application could not be loaded.');
    } finally {
      setLoading(false);
    }
  }, [applicationId, session]);

  useFocusEffect(useCallback(() => { load(); }, [load]));
  const documentTypes = useMemo(() => {
    const fromLoan = detail ? [...Object.keys(detail.application.document_evidence), ...detail.application.requested_documents] : [];
    return [...new Set([...fromLoan, ...standardDocuments])];
  }, [detail]);

  const upload = async (documentType: string) => {
    if (!session || !applicationId) return;
    const result = await DocumentPicker.getDocumentAsync({
      copyToCacheDirectory: true,
      multiple: false,
      type: ['application/pdf', 'image/png', 'image/jpeg'],
    });
    if (result.canceled) return;
    const asset = result.assets[0];
    const body = new FormData();
    body.append('document_type', documentType);
    if (Platform.OS === 'web' && asset.file) {
      body.append('file', asset.file, asset.name);
    } else {
      body.append('file', { uri: asset.uri, name: asset.name, type: asset.mimeType || 'application/octet-stream' } as unknown as Blob);
    }
    setBusy(documentType);
    setError('');
    setMessage('');
    try {
      await apiRequest(`/api/v1/loan-applications/${encodeURIComponent(applicationId)}/documents`, { method: 'POST', body }, session.accessToken);
      setMessage(`${documentType.replaceAll('_', ' ')} uploaded and queued for AI verification.`);
      await load();
    } catch (value) {
      setError(value instanceof Error ? value.message : 'Document upload failed.');
    } finally {
      setBusy('');
    }
  };

  const runAgent = async () => {
    if (!session || !applicationId) return;
    setBusy('agent');
    setError('');
    setMessage('');
    try {
      await apiRequest(`/api/v1/loan-applications/${encodeURIComponent(applicationId)}/run-exception-agent`, { method: 'POST' }, session.accessToken);
      setMessage('The exception agent completed this assessment cycle.');
      await load();
    } catch (value) {
      setError(value instanceof Error ? value.message : 'Agent cycle failed.');
    } finally {
      setBusy('');
    }
  };

  const requestCreditReview = async () => {
    if (!session || !applicationId) return;
    if (reviewReason.trim().length < 10) {
      setError('Explain the reconsideration request in at least 10 characters.');
      return;
    }
    setBusy('credit-review');
    setError('');
    setMessage('');
    try {
      await apiRequest(`/api/v1/loan-applications/${encodeURIComponent(applicationId)}/credit-review-requests`, {
        method: 'POST',
        body: JSON.stringify({ reason: reviewReason.trim(), bureau_dispute_reference: disputeReference.trim() }),
      }, session.accessToken);
      setMessage('Your credit reconsideration request was routed to an authorised credit manager.');
      setReviewReason('');
      setDisputeReference('');
    } catch (value) {
      setError(value instanceof Error ? value.message : 'Credit reconsideration could not be submitted.');
    } finally {
      setBusy('');
    }
  };

  const loan = detail?.application;
  const mayUpload = session && ['CUSTOMER', 'LOAN', 'ADMIN'].includes(session.user.role);
  const mayRun = session && ['LOAN', 'ADMIN'].includes(session.user.role);
  const wide = width >= 820;

  return (
    <AppPage roles={['CUSTOMER', 'LOAN', 'CREDIT', 'ADMIN']}>
      {loading && !detail ? <LoadingState label="Loading application…" /> : null}
      {error ? <Banner tone="error" body={error} /> : null}
      {message ? <Banner tone="success" body={message} /> : null}
      {!loading && !detail ? <EmptyState title="Application unavailable" body="It may not exist or may fall outside your role scope." /> : null}
      {loan && detail ? (
        <>
          <View style={styles.headingRow}>
            <SectionTitle eyebrow={loan.application_id} title={loan.applicant_name || 'Loan application'} body={`${loan.loan_product.replaceAll('_', ' ')} · ${formatMoney(loan.requested_amount)} · ${loan.tenure_months} months`} />
            <StatusPill value={loan.status} />
          </View>
          {loan.status === 'REJECTED' ? (
            <Banner tone="error" title="Application declined under configured policy" body={loan.diagnosis || 'Review the recorded decision reason. Contact the bank if bureau data is incorrect or you need a human reconsideration.'} />
          ) : null}
          {session?.user.role === 'CUSTOMER' && loan.status === 'REJECTED' && loan.credit_score_decision === 'REJECTED_LOW_SCORE' ? (
            <Card style={styles.section}>
              <Text style={styles.cardEyebrow}>CUSTOMER REVIEW RIGHT</Text>
              <Text style={styles.cardTitle}>Request human reconsideration</Text>
              <Text style={styles.privacyNote}>If the bureau information is inaccurate, dispute it with the bureau and include the reference. A credit manager—not the AI agent—will review this request.</Text>
              <Field label="Reason for reconsideration *" value={reviewReason} onChangeText={setReviewReason} multiline maxLength={1000} />
              <Field label="Bureau dispute reference" value={disputeReference} onChangeText={setDisputeReference} maxLength={100} />
              <View style={styles.reviewAction}><Button label="Send for credit-manager review" loading={busy === 'credit-review'} onPress={requestCreditReview} /></View>
            </Card>
          ) : null}
          <View style={[styles.twoColumn, wide && styles.twoColumnWide]}>
            <Card style={styles.column}>
              <Text style={styles.cardEyebrow}>APPLICATION</Text>
              <Text style={styles.cardTitle}>Request summary</Text>
              <Info label="Purpose" value={loan.loan_purpose || '—'} />
              <Info label="Employment" value={loan.employment_type.replaceAll('_', ' ')} />
              <Info label="Monthly income" value={formatMoney(loan.monthly_income)} />
              <Info label="Exception" value={loan.exception_code.replaceAll('_', ' ')} />
              <Info label="Diagnosis" value={loan.diagnosis || 'Assessment is running'} />
            </Card>
            <Card style={styles.column}>
              <Text style={styles.cardEyebrow}>CREDIT-BUREAU AGENT</Text>
              <Text style={styles.cardTitle}>Consent-led assessment</Text>
              <View style={styles.scoreRow}>
                <Text style={styles.score}>{loan.credit_score ?? '—'}</Text>
                <View style={styles.scoreCopy}>
                  <Text style={styles.scoreBand}>{loan.credit_score_band.replaceAll('_', ' ')}</Text>
                  <StatusPill value={loan.credit_score_decision} />
                </View>
              </View>
              <Info label="Provider" value={loan.credit_score_provider || 'Not checked'} />
              <Info label="Checked" value={loan.credit_score_checked_at ? new Date(loan.credit_score_checked_at).toLocaleString() : 'Not checked'} />
              <Text style={styles.privacyNote}>The customer never supplies this score. It is returned by the configured provider after recorded consent.</Text>
            </Card>
          </View>

          <Card style={styles.section}>
            <View style={styles.sectionHeader}>
              <View><Text style={styles.cardEyebrow}>PROCESS PROGRESSION</Text><Text style={styles.cardTitle}>Where AI is working</Text></View>
              {mayRun ? <Button compact label="Run exception agent" loading={busy === 'agent'} onPress={runAgent} /> : null}
            </View>
            <View style={styles.timeline}>
              {detail.progress.map((stage, index) => (
                <View key={stage.name} style={styles.stage}>
                  <View style={[styles.stageDot, stage.completed && styles.stageDotDone]}><Text style={[styles.stageDotText, stage.completed && styles.stageDotTextDone]}>{stage.completed ? '✓' : index + 1}</Text></View>
                  <View style={styles.stageCopy}>
                    <View style={styles.stageTitleRow}>
                      <Text style={styles.stageTitle}>{stage.name}</Text>
                      {stage.ai_active ? <View style={styles.aiBadge}><Text style={styles.aiBadgeText}>AI ACTIVE</Text></View> : null}
                    </View>
                    <Text style={styles.stageOwner}>Owner: {stage.owner} · {stage.completed ? 'Completed' : 'Upcoming / awaiting action'}</Text>
                  </View>
                </View>
              ))}
            </View>
          </Card>

          <Card style={styles.section}>
            <Text style={styles.cardEyebrow}>DOCUMENT EVIDENCE</Text>
            <Text style={styles.cardTitle}>Upload by document type</Text>
            <Text style={styles.privacyNote}>PDF, PNG, or JPG · maximum 10 MB per file. Every upload is stored against this server-generated application ID and queued for verification.</Text>
            <View style={styles.documentList}>
              {documentTypes.map((type) => {
                const status = loan.document_evidence[type] || 'NOT_UPLOADED';
                return (
                  <View style={styles.documentRow} key={type}>
                    <View style={styles.documentCopy}>
                      <Text style={styles.documentName}>{type.replaceAll('_', ' ')}</Text>
                      <StatusPill value={status} />
                    </View>
                    {mayUpload ? <Button compact label={status === 'NOT_UPLOADED' ? 'Choose file' : 'Replace file'} variant="secondary" loading={busy === type} onPress={() => upload(type)} /> : null}
                  </View>
                );
              })}
            </View>
          </Card>
        </>
      ) : null}
    </AppPage>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return <View style={styles.info}><Text style={styles.infoLabel}>{label}</Text><Text style={styles.infoValue}>{value}</Text></View>;
}

const styles = StyleSheet.create({
  headingRow: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' },
  twoColumn: { gap: 12 },
  twoColumnWide: { flexDirection: 'row' },
  column: { flex: 1, gap: 13 },
  cardEyebrow: { color: colors.primary, fontSize: 10, fontWeight: '900', letterSpacing: 1.2 },
  cardTitle: { color: colors.ink, fontSize: 19, fontWeight: '900', marginBottom: 3 },
  info: { gap: 3, borderTopWidth: 1, borderTopColor: colors.line, paddingTop: 10 },
  infoLabel: { color: colors.muted, fontSize: 10, fontWeight: '800', letterSpacing: 0.7, textTransform: 'uppercase' },
  infoValue: { color: colors.ink, fontSize: 13, lineHeight: 19, fontWeight: '700' },
  scoreRow: { flexDirection: 'row', alignItems: 'center', gap: 15, backgroundColor: colors.primarySoft, borderRadius: radius.sm, padding: 15 },
  score: { color: colors.primaryDark, fontSize: 39, fontWeight: '900', letterSpacing: -1.5 },
  scoreCopy: { gap: 6 },
  scoreBand: { color: colors.primaryDark, fontWeight: '900', fontSize: 12 },
  privacyNote: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  section: { gap: space.lg },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 },
  timeline: { gap: 6 },
  stage: { flexDirection: 'row', gap: 12, minHeight: 57 },
  stageDot: { width: 31, height: 31, borderRadius: 16, borderWidth: 2, borderColor: colors.line, backgroundColor: colors.white, alignItems: 'center', justifyContent: 'center' },
  stageDotDone: { backgroundColor: colors.primary, borderColor: colors.primary },
  stageDotText: { color: colors.muted, fontSize: 11, fontWeight: '900' },
  stageDotTextDone: { color: colors.white },
  stageCopy: { flex: 1, gap: 5, paddingBottom: 12 },
  stageTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  stageTitle: { color: colors.ink, fontSize: 14, fontWeight: '900' },
  stageOwner: { color: colors.muted, fontSize: 11, lineHeight: 16 },
  aiBadge: { backgroundColor: colors.accentSoft, borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 4 },
  aiBadgeText: { color: colors.warning, fontWeight: '900', fontSize: 8, letterSpacing: 0.7 },
  documentList: { gap: 8 },
  documentRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, borderTopWidth: 1, borderTopColor: colors.line, paddingTop: 11 },
  documentCopy: { flex: 1, gap: 6 },
  documentName: { color: colors.ink, fontSize: 13, fontWeight: '900' },
  reviewAction: { alignItems: 'flex-end' },
});
