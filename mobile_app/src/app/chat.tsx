import { AppPage } from '@/components/app-page';
import { Banner, Button, Card, Field, SectionTitle } from '@/components/ui';
import { colors, radius, space } from '@/constants/app-theme';
import { useAuth } from '@/context/auth';
import { apiRequest } from '@/lib/api';
import type { ChatAction, ChatAssistantResult, UserRole } from '@/lib/types';
import { useRouter } from 'expo-router';
import { useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, useWindowDimensions, View } from 'react-native';

type ChatMessage = {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  intent?: string;
};

const starterPrompts: Record<UserRole, string[]> = {
  CUSTOMER: ['What is the status of my latest loan?', 'Which documents are required?', 'How do I reactivate a dormant account?', 'How does the CIBIL step work?'],
  LOAN: ['Summarize my loan exception queue', 'Which documents are required for a home loan?', 'Explain credit-bureau review', 'What can the AI automate?'],
  CREDIT: ['How many approvals are pending?', 'Explain low-score reconsideration', 'Show the latest loan status', 'What remains human-controlled?'],
  COMPLIANCE: ['Summarize dormant accounts', 'How does reactivation work?', 'How many approvals are pending?', 'Explain unclaimed balances'],
  ADMIN: ['Summarize pending approvals', 'Explain all AI agents', 'Show the latest loan status', 'How is automation governed?'],
};

export default function ChatScreen() {
  const { session } = useAuth();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const role = session?.user.role || 'CUSTOMER';
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [suggestions, setSuggestions] = useState(starterPrompts[role]);
  const [actions, setActions] = useState<ChatAction[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      sender: 'assistant',
      text: 'Hello. I can explain the banking workflow and information your role is authorised to view. What would you like to understand?',
      intent: 'WELCOME',
    },
  ]);

  const compact = width < 720;
  const nextId = useMemo(() => () => `${Date.now()}-${Math.random().toString(16).slice(2)}`, []);

  const send = async (prompt?: string) => {
    const message = (prompt ?? draft).trim();
    if (!message || !session || busy) return;
    setError('');
    setBusy(true);
    setDraft('');
    setActions([]);
    setMessages((current) => [...current, { id: nextId(), sender: 'user', text: message }]);
    try {
      const result = await apiRequest<ChatAssistantResult>(
        '/api/v1/chat/messages',
        { method: 'POST', body: JSON.stringify({ message }) },
        session.accessToken,
      );
      setMessages((current) => [...current, { id: nextId(), sender: 'assistant', text: result.reply, intent: result.intent }]);
      setSuggestions(result.suggested_prompts);
      setActions(result.actions);
    } catch (value) {
      setError(value instanceof Error ? value.message : 'The assistant could not answer right now.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <AppPage>
      <View style={[styles.headingRow, compact && styles.headingCompact]}>
        <SectionTitle
          eyebrow="READ-ONLY AI ASSISTANT"
          title="Ask about your banking workflow"
          body="Answers use role-scoped application data and explain what happens next without taking a banking decision." />
        <Button
          compact
          label="Clear conversation"
          variant="ghost"
          onPress={() => {
            setMessages((current) => current.slice(0, 1));
            setActions([]);
            setError('');
          }} />
      </View>

      <Banner
        title="Human authority remains in control"
        body="The assistant cannot approve, reject, verify KYC, change a credit score, disburse a loan, transfer funds, or update an account." />
      {error ? <Banner tone="error" body={error} /> : null}

      <Card style={styles.chatCard}>
        <View style={styles.onlineRow}>
          <View style={styles.agentMark}><Text style={styles.agentMarkText}>AI</Text></View>
          <View style={styles.agentCopy}>
            <Text style={styles.agentName}>Banking Support Assistant</Text>
            <Text style={styles.agentMeta}>Role-aware · Read only · Audit event recorded</Text>
          </View>
          <View style={styles.onlineDot} />
        </View>

        <View style={styles.transcript}>
          {messages.map((message) => (
            <View key={message.id} style={[styles.messageRow, message.sender === 'user' && styles.messageRowUser]}>
              <View style={[styles.bubble, message.sender === 'user' ? styles.userBubble : styles.assistantBubble]}>
                <Text style={[styles.sender, message.sender === 'user' && styles.userText]}>
                  {message.sender === 'user' ? 'You' : 'Banking Assistant'}
                </Text>
                <Text style={[styles.messageText, message.sender === 'user' && styles.userText]}>{message.text}</Text>
                {message.intent ? <Text style={styles.intent}>{message.intent.replaceAll('_', ' ')}</Text> : null}
              </View>
            </View>
          ))}
          {busy ? (
            <View style={styles.thinking}><View style={styles.thinkingDot} /><Text style={styles.thinkingText}>Checking authorised workflow data…</Text></View>
          ) : null}
        </View>

        <View style={styles.suggestions}>
          {suggestions.slice(0, 4).map((prompt) => (
            <Pressable key={prompt} disabled={busy} onPress={() => send(prompt)} style={styles.suggestion}>
              <Text style={styles.suggestionText}>{prompt}</Text>
            </Pressable>
          ))}
        </View>

        {actions.length ? (
          <View style={styles.actions}>
            {actions.map((action) => <Button key={`${action.path}-${action.label}`} compact label={action.label} variant="secondary" onPress={() => router.push(action.path as never)} />)}
          </View>
        ) : null}

        <View style={[styles.composer, compact && styles.composerCompact]}>
          <View style={styles.inputWrap}>
            <Field
              label="Your question"
              value={draft}
              multiline
              maxLength={1000}
              placeholder="Ask about status, documents, approvals, CIBIL, AI agents, or dormant accounts"
              onChangeText={setDraft}
            />
          </View>
          <Button label="Send" loading={busy} disabled={!draft.trim()} onPress={() => send()} />
        </View>
      </Card>
    </AppPage>
  );
}

const styles = StyleSheet.create({
  headingRow: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 },
  headingCompact: { flexDirection: 'column' },
  chatCard: { padding: 0, overflow: 'hidden' },
  onlineRow: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: space.lg, borderBottomWidth: 1, borderBottomColor: colors.line },
  agentMark: { width: 44, height: 44, borderRadius: 14, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center' },
  agentMarkText: { color: colors.white, fontWeight: '900', fontSize: 14 },
  agentCopy: { flex: 1, gap: 3 },
  agentName: { color: colors.ink, fontWeight: '900', fontSize: 15 },
  agentMeta: { color: colors.muted, fontSize: 11 },
  onlineDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.success },
  transcript: { minHeight: 300, gap: 12, padding: space.lg, backgroundColor: '#F8FAFC' },
  messageRow: { flexDirection: 'row' },
  messageRowUser: { justifyContent: 'flex-end' },
  bubble: { maxWidth: '86%', borderRadius: radius.md, padding: 14, gap: 5 },
  assistantBubble: { backgroundColor: colors.primarySoft, borderTopLeftRadius: 5 },
  userBubble: { backgroundColor: colors.primaryDark, borderTopRightRadius: 5 },
  sender: { color: colors.primaryDark, fontSize: 10, fontWeight: '900', letterSpacing: 0.8, textTransform: 'uppercase' },
  messageText: { color: colors.ink, fontSize: 14, lineHeight: 21 },
  userText: { color: colors.white },
  intent: { color: colors.primary, fontSize: 9, fontWeight: '800', letterSpacing: 0.7, marginTop: 3 },
  thinking: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  thinkingDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.accent },
  thinkingText: { color: colors.muted, fontSize: 12 },
  suggestions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, paddingHorizontal: space.lg, paddingTop: space.md },
  suggestion: { paddingHorizontal: 12, paddingVertical: 9, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.white },
  suggestionText: { color: colors.primaryDark, fontSize: 11, fontWeight: '800' },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, paddingHorizontal: space.lg, paddingTop: space.md },
  composer: { flexDirection: 'row', alignItems: 'flex-end', gap: 12, padding: space.lg },
  composerCompact: { flexDirection: 'column', alignItems: 'stretch' },
  inputWrap: { flex: 1 },
});
