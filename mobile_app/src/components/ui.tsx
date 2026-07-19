import { colors, radius, shadows, space } from '@/constants/app-theme';
import type { UserRole } from '@/lib/types';
import type { PropsWithChildren, ReactNode } from 'react';
import {
  ActivityIndicator,
  KeyboardTypeOptions,
  Pressable,
  StyleProp,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  View,
  ViewStyle,
} from 'react-native';

export const roleLabels: Record<UserRole, string> = {
  CUSTOMER: 'Customer',
  LOAN: 'Loan Operations',
  CREDIT: 'Credit Manager',
  COMPLIANCE: 'Compliance',
  ADMIN: 'Administrator',
};

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <View style={styles.brandRow}>
      <View style={[styles.brandMark, compact && styles.brandMarkCompact]}>
        <Text style={[styles.brandMarkText, compact && styles.brandMarkTextCompact]}>BA</Text>
      </View>
      <View>
        <Text style={[styles.brandName, compact && styles.brandNameCompact]}>Banking AI</Text>
        {!compact && <Text style={styles.brandTag}>OPERATIONS INTELLIGENCE</Text>}
      </View>
    </View>
  );
}

export function Card({ children, style }: PropsWithChildren<{ style?: StyleProp<ViewStyle> }>) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function SectionTitle({ eyebrow, title, body }: { eyebrow?: string; title: string; body?: string }) {
  return (
    <View style={styles.sectionTitle}>
      {eyebrow ? <Text style={styles.eyebrow}>{eyebrow}</Text> : null}
      <Text style={styles.heading}>{title}</Text>
      {body ? <Text style={styles.body}>{body}</Text> : null}
    </View>
  );
}

type FieldProps = TextInputProps & {
  label: string;
  hint?: string;
  error?: string;
  keyboardType?: KeyboardTypeOptions;
};

export function Field({ label, hint, error, style, ...props }: FieldProps) {
  return (
    <View style={styles.fieldWrap}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        placeholderTextColor="#8AA0B4"
        selectionColor={colors.primary}
        style={[styles.input, props.multiline && styles.inputMultiline, error && styles.inputError, style]}
        {...props}
      />
      {error ? <Text style={styles.errorText}>{error}</Text> : hint ? <Text style={styles.hint}>{hint}</Text> : null}
    </View>
  );
}

export function Button({
  label,
  onPress,
  loading = false,
  disabled = false,
  variant = 'primary',
  compact = false,
  style,
}: {
  label: string;
  onPress: () => void;
  loading?: boolean;
  disabled?: boolean;
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  compact?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: disabled || loading, busy: loading }}
      disabled={disabled || loading}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        compact && styles.buttonCompact,
        styles[`button_${variant}`],
        (disabled || loading) && styles.buttonDisabled,
        pressed && styles.buttonPressed,
        style,
      ]}>
      {loading ? <ActivityIndicator color={variant === 'primary' || variant === 'danger' ? colors.white : colors.primary} /> : null}
      <Text style={[styles.buttonText, styles[`buttonText_${variant}`]]}>{label}</Text>
    </Pressable>
  );
}

export function ChoiceChips<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <View style={styles.fieldWrap}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.chipRow}>
        {options.map((option) => {
          const active = option.value === value;
          return (
            <Pressable
              accessibilityRole="radio"
              accessibilityState={{ selected: active }}
              key={option.value}
              onPress={() => onChange(option.value)}
              style={[styles.choiceChip, active && styles.choiceChipActive]}>
              <Text style={[styles.choiceText, active && styles.choiceTextActive]}>{option.label}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

export function CheckRow({ checked, onChange, title, body }: { checked: boolean; onChange: (value: boolean) => void; title: string; body?: string }) {
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityState={{ checked }}
      onPress={() => onChange(!checked)}
      style={[styles.checkRow, checked && styles.checkRowActive]}>
      <View style={[styles.checkbox, checked && styles.checkboxActive]}>{checked ? <Text style={styles.checkmark}>✓</Text> : null}</View>
      <View style={styles.checkCopy}>
        <Text style={styles.checkTitle}>{title}</Text>
        {body ? <Text style={styles.hint}>{body}</Text> : null}
      </View>
    </Pressable>
  );
}

export function StatusPill({ value }: { value: string }) {
  const normalized = value.toUpperCase();
  const danger = normalized.includes('REJECT') || normalized.includes('FAILED');
  const success = normalized.includes('APPROV') || normalized.includes('READY') || normalized === 'ACTIVE' || normalized.includes('SUCCEED');
  const warning = normalized.includes('PENDING') || normalized.includes('HELD') || normalized.includes('AWAITING') || normalized.includes('DORMANT');
  return (
    <View style={[styles.status, danger && styles.statusDanger, success && styles.statusSuccess, warning && styles.statusWarning]}>
      <Text style={[styles.statusText, danger && styles.statusTextDanger, success && styles.statusTextSuccess, warning && styles.statusTextWarning]}>
        {value.replaceAll('_', ' ')}
      </Text>
    </View>
  );
}

export function Metric({ label, value, note }: { label: string; value: string | number; note?: string }) {
  return (
    <Card style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
      {note ? <Text style={styles.hint}>{note}</Text> : null}
    </Card>
  );
}

export function Banner({ title, body, tone = 'info' }: { title?: string; body: string; tone?: 'info' | 'error' | 'success' }) {
  return (
    <View style={[styles.banner, tone === 'error' && styles.bannerError, tone === 'success' && styles.bannerSuccess]}>
      {title ? <Text style={styles.bannerTitle}>{title}</Text> : null}
      <Text style={styles.bannerBody}>{body}</Text>
    </View>
  );
}

export function LoadingState({ label = 'Loading secure workspace…' }: { label?: string }) {
  return (
    <View style={styles.loading}>
      <ActivityIndicator color={colors.primary} size="large" />
      <Text style={styles.body}>{label}</Text>
    </View>
  );
}

export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <Card style={styles.empty}>
      <View style={styles.emptyMark}><Text style={styles.emptyMarkText}>✓</Text></View>
      <Text style={styles.emptyTitle}>{title}</Text>
      <Text style={styles.body}>{body}</Text>
      {action}
    </Card>
  );
}

export const formatMoney = (value: number) => `₹${Number(value || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

const styles = StyleSheet.create({
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  brandMark: { width: 48, height: 48, borderRadius: 15, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center' },
  brandMarkCompact: { width: 38, height: 38, borderRadius: 12 },
  brandMarkText: { color: colors.white, fontSize: 17, fontWeight: '900', letterSpacing: -0.5 },
  brandMarkTextCompact: { fontSize: 14 },
  brandName: { color: colors.ink, fontSize: 21, fontWeight: '900', letterSpacing: -0.6 },
  brandNameCompact: { fontSize: 17 },
  brandTag: { color: colors.primary, fontSize: 9, fontWeight: '800', letterSpacing: 1.4, marginTop: 2 },
  card: { backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.line, padding: space.lg, ...shadows.card },
  sectionTitle: { gap: 7, marginBottom: space.md },
  eyebrow: { color: colors.primary, fontSize: 11, fontWeight: '900', letterSpacing: 1.5 },
  heading: { color: colors.ink, fontSize: 25, lineHeight: 31, fontWeight: '900', letterSpacing: -0.7 },
  body: { color: colors.muted, fontSize: 15, lineHeight: 22 },
  fieldWrap: { gap: 7, minWidth: 0 },
  label: { color: colors.ink, fontWeight: '800', fontSize: 13 },
  input: { minHeight: 50, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.line, backgroundColor: '#FBFCFE', paddingHorizontal: 14, paddingVertical: 12, color: colors.ink, fontSize: 15 },
  inputMultiline: { minHeight: 96, textAlignVertical: 'top' },
  inputError: { borderColor: colors.danger },
  hint: { color: colors.muted, fontSize: 12, lineHeight: 17 },
  errorText: { color: colors.danger, fontSize: 12, fontWeight: '700' },
  button: { minHeight: 50, paddingHorizontal: 20, borderRadius: radius.sm, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 9, borderWidth: 1 },
  buttonCompact: { minHeight: 39, paddingHorizontal: 14 },
  button_primary: { backgroundColor: colors.primary, borderColor: colors.primary },
  button_secondary: { backgroundColor: colors.white, borderColor: colors.primary },
  button_danger: { backgroundColor: colors.danger, borderColor: colors.danger },
  button_ghost: { backgroundColor: 'transparent', borderColor: colors.line },
  buttonDisabled: { opacity: 0.48 },
  buttonPressed: { opacity: 0.78, transform: [{ scale: 0.99 }] },
  buttonText: { fontWeight: '900', fontSize: 14 },
  buttonText_primary: { color: colors.white },
  buttonText_secondary: { color: colors.primary },
  buttonText_danger: { color: colors.white },
  buttonText_ghost: { color: colors.ink },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  choiceChip: { borderWidth: 1, borderColor: colors.line, paddingHorizontal: 13, paddingVertical: 10, borderRadius: radius.pill, backgroundColor: colors.white },
  choiceChipActive: { backgroundColor: colors.primarySoft, borderColor: colors.primary },
  choiceText: { color: colors.muted, fontWeight: '700', fontSize: 12 },
  choiceTextActive: { color: colors.primaryDark },
  checkRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.white, borderRadius: radius.sm, padding: 14 },
  checkRowActive: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  checkbox: { width: 23, height: 23, borderWidth: 2, borderColor: '#9FB3C8', borderRadius: 7, alignItems: 'center', justifyContent: 'center', marginTop: 1 },
  checkboxActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  checkmark: { color: colors.white, fontWeight: '900', fontSize: 14 },
  checkCopy: { flex: 1, gap: 3 },
  checkTitle: { color: colors.ink, fontSize: 14, lineHeight: 20, fontWeight: '800' },
  status: { alignSelf: 'flex-start', borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: colors.infoSoft },
  statusDanger: { backgroundColor: colors.dangerSoft },
  statusSuccess: { backgroundColor: colors.primarySoft },
  statusWarning: { backgroundColor: colors.accentSoft },
  statusText: { color: colors.info, fontSize: 10, fontWeight: '900', letterSpacing: 0.5 },
  statusTextDanger: { color: colors.danger },
  statusTextSuccess: { color: colors.success },
  statusTextWarning: { color: colors.warning },
  metric: { flex: 1, minWidth: 180, gap: 7 },
  metricLabel: { color: colors.muted, fontWeight: '800', fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.8 },
  metricValue: { color: colors.ink, fontSize: 31, lineHeight: 37, fontWeight: '900', letterSpacing: -1 },
  banner: { backgroundColor: colors.infoSoft, borderLeftWidth: 4, borderLeftColor: colors.info, borderRadius: radius.sm, padding: 14, gap: 4 },
  bannerError: { backgroundColor: colors.dangerSoft, borderLeftColor: colors.danger },
  bannerSuccess: { backgroundColor: colors.primarySoft, borderLeftColor: colors.success },
  bannerTitle: { color: colors.ink, fontWeight: '900', fontSize: 14 },
  bannerBody: { color: colors.ink, fontSize: 13, lineHeight: 19 },
  loading: { minHeight: 240, alignItems: 'center', justifyContent: 'center', gap: 14 },
  empty: { alignItems: 'center', gap: 12, paddingVertical: 32 },
  emptyMark: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center' },
  emptyMarkText: { color: colors.primary, fontWeight: '900', fontSize: 20 },
  emptyTitle: { color: colors.ink, fontSize: 18, fontWeight: '900', textAlign: 'center' },
});

