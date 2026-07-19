import { AppPage } from '@/components/app-page';
import { Banner, Button, Card, CheckRow, ChoiceChips, Field, FormErrorModal, SectionTitle } from '@/components/ui';
import { colors, space } from '@/constants/app-theme';
import { useAuth } from '@/context/auth';
import { apiRequest, jsonBody } from '@/lib/api';
import type { LoanApplication } from '@/lib/types';
import { useRouter } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, Text, useWindowDimensions, View } from 'react-native';

const documentTypes = [
  ['PAN', 'PAN card'],
  ['AADHAAR', 'Aadhaar / identity proof'],
  ['BANK_STATEMENT', 'Bank statement'],
  ['SALARY_SLIP', 'Salary slips'],
  ['EMPLOYMENT_PROOF', 'Employment proof'],
  ['INCOME_TAX_RETURN', 'Income tax returns'],
  ['BUSINESS_REGISTRATION', 'Business registration'],
] as const;

type FormState = {
  applicant_name: string;
  date_of_birth: string;
  email: string;
  phone: string;
  residential_address: string;
  loan_product: string;
  requested_amount: string;
  tenure_months: string;
  loan_purpose: string;
  employment_type: string;
  employer_name: string;
  monthly_income: string;
  pan_for_bureau_lookup: string;
};

const initialForm: FormState = {
  applicant_name: '', date_of_birth: '', email: '', phone: '', residential_address: '', loan_product: 'PERSONAL',
  requested_amount: '', tenure_months: '24', loan_purpose: '', employment_type: 'SALARIED', employer_name: '',
  monthly_income: '', pan_for_bureau_lookup: '',
};

type FormErrorKey = keyof FormState | 'consent';

const fieldLabels: Record<FormErrorKey, string> = {
  applicant_name: 'Applicant name',
  date_of_birth: 'Date of birth',
  email: 'Email address',
  phone: 'Mobile number',
  residential_address: 'Residential address',
  loan_product: 'Loan product',
  requested_amount: 'Requested amount',
  tenure_months: 'Tenure',
  loan_purpose: 'Loan purpose',
  employment_type: 'Employment type',
  employer_name: 'Employer or business',
  monthly_income: 'Monthly income',
  pan_for_bureau_lookup: 'PAN for bureau lookup',
  consent: 'Credit-bureau consent',
};

export default function NewLoanScreen() {
  const { session } = useAuth();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const [form, setForm] = useState(initialForm);
  const [documents, setDocuments] = useState<string[]>(['PAN', 'BANK_STATEMENT']);
  const [consent, setConsent] = useState(false);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<FormErrorKey, string>>>({});
  const [validationItems, setValidationItems] = useState<string[]>([]);
  const [showValidationModal, setShowValidationModal] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const wide = width >= 760;

  const set = (key: keyof FormState) => (value: string) => {
    setForm((current) => ({ ...current, [key]: value }));
    setFieldErrors((current) => ({ ...current, [key]: undefined }));
  };
  const toggleDocument = (value: string) => setDocuments((current) => current.includes(value) ? current.filter((item) => item !== value) : [...current, value]);
  const updateConsent = (value: boolean) => {
    setConsent(value);
    if (value) setFieldErrors((current) => ({ ...current, consent: undefined }));
  };

  const validate = () => {
    const next: Partial<Record<FormErrorKey, string>> = {};
    const required: (keyof FormState)[] = [
      'applicant_name', 'date_of_birth', 'email', 'phone', 'residential_address', 'requested_amount',
      'tenure_months', 'loan_purpose', 'employment_type', 'monthly_income', 'pan_for_bureau_lookup',
    ];
    required.forEach((key) => {
      if (!form[key].trim()) next[key] = `${fieldLabels[key]} is required.`;
    });
    if (form.email.trim() && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) next.email = 'Enter a valid email address.';
    if (form.date_of_birth.trim() && !/^\d{4}-\d{2}-\d{2}$/.test(form.date_of_birth.trim())) next.date_of_birth = 'Use YYYY-MM-DD.';
    if (form.pan_for_bureau_lookup.trim() && !/^[A-Z]{5}\d{4}[A-Z]$/i.test(form.pan_for_bureau_lookup.trim())) next.pan_for_bureau_lookup = 'Enter a valid 10-character PAN.';
    if (form.requested_amount.trim() && !(Number(form.requested_amount) > 0)) next.requested_amount = 'Enter an amount greater than zero.';
    if (form.monthly_income.trim() && !(Number(form.monthly_income) > 0)) next.monthly_income = 'Enter an income greater than zero.';
    if (form.tenure_months.trim() && !(Number(form.tenure_months) > 0)) next.tenure_months = 'Enter a tenure greater than zero.';
    if (!consent) next.consent = 'Explicit consent is required before a bureau enquiry.';

    if (Object.keys(next).length) {
      setFieldErrors(next);
      setValidationItems(Object.entries(next).map(([key, message]) => `${fieldLabels[key as FormErrorKey]}: ${message}`));
      setShowValidationModal(true);
      return false;
    }
    return true;
  };

  const submit = async () => {
    if (!validate()) return;
    const amount = Number(form.requested_amount);
    const income = Number(form.monthly_income);
    const tenure = Number(form.tenure_months);
    setSubmitting(true);
    setError('');
    try {
      const created = await apiRequest<LoanApplication>('/api/v1/loan-applications', {
        method: 'POST',
        ...jsonBody({
          ...form,
          loan_product: form.loan_product,
          requested_amount: amount,
          monthly_income: income,
          tenure_months: Math.round(tenure),
          pan_for_bureau_lookup: form.pan_for_bureau_lookup.toUpperCase().trim(),
          credit_bureau_consent: consent,
          consent_version: 'CREDIT_BUREAU_CONSENT_V1',
          uploaded_document_types: documents,
        }),
      }, session?.accessToken);
      router.replace(`/loans/${created.application_id}` as never);
    } catch (value) {
      setError(value instanceof Error ? value.message : 'Application could not be submitted.');
    } finally {
      setSubmitting(false);
    }
  };

  const pair = (left: React.ReactNode, right: React.ReactNode) => (
    <View style={[styles.pair, wide && styles.pairWide]}><View style={styles.pairItem}>{left}</View><View style={styles.pairItem}>{right}</View></View>
  );

  return (
    <AppPage roles={['CUSTOMER']}>
      <SectionTitle eyebrow="CUSTOMER APPLICATION" title="Apply for a loan" body="Your application ID is generated by the banking database after submission. The bureau score is fetched by the agent—it is never entered by the applicant." />
      {error ? <Banner tone="error" body={error} /> : null}

      <Card style={styles.section}>
        <Text style={styles.sectionNumber}>01</Text><Text style={styles.sectionHeading}>Personal information</Text>
        {pair(
          <Field label="Applicant name *" value={form.applicant_name} onChangeText={set('applicant_name')} autoCapitalize="words" />,
          <Field label="Date of birth *" hint="YYYY-MM-DD" value={form.date_of_birth} onChangeText={set('date_of_birth')} keyboardType="numbers-and-punctuation" />,
        )}
        {pair(
          <Field label="Email *" value={form.email} onChangeText={set('email')} keyboardType="email-address" autoCapitalize="none" />,
          <Field label="Mobile number *" value={form.phone} onChangeText={set('phone')} keyboardType="phone-pad" />,
        )}
        <Field label="Residential address *" value={form.residential_address} onChangeText={set('residential_address')} multiline numberOfLines={3} />
      </Card>

      <Card style={styles.section}>
        <Text style={styles.sectionNumber}>02</Text><Text style={styles.sectionHeading}>Employment and income</Text>
        <ChoiceChips
          label="Employment type *"
          value={form.employment_type}
          onChange={set('employment_type')}
          options={[{ value: 'SALARIED', label: 'Salaried' }, { value: 'SELF_EMPLOYED', label: 'Self-employed' }, { value: 'BUSINESS_OWNER', label: 'Business owner' }]}
        />
        {pair(
          <Field label="Employer / business" value={form.employer_name} onChangeText={set('employer_name')} />,
          <Field label="Monthly income (₹) *" value={form.monthly_income} onChangeText={set('monthly_income')} keyboardType="decimal-pad" />,
        )}
      </Card>

      <Card style={styles.section}>
        <Text style={styles.sectionNumber}>03</Text><Text style={styles.sectionHeading}>Loan request</Text>
        <ChoiceChips
          label="Loan product"
          value={form.loan_product}
          onChange={set('loan_product')}
          options={[{ value: 'PERSONAL', label: 'Personal' }, { value: 'HOME', label: 'Home' }, { value: 'BUSINESS', label: 'Business' }]}
        />
        {pair(
          <Field label="Requested amount (₹) *" value={form.requested_amount} onChangeText={set('requested_amount')} keyboardType="decimal-pad" />,
          <Field label="Tenure (months) *" value={form.tenure_months} onChangeText={set('tenure_months')} keyboardType="number-pad" />,
        )}
        <Field label="Loan purpose *" value={form.loan_purpose} onChangeText={set('loan_purpose')} multiline numberOfLines={3} />
      </Card>

      <Card style={styles.section}>
        <Text style={styles.sectionNumber}>04</Text><Text style={styles.sectionHeading}>Documents to provide</Text>
        <Text style={styles.supporting}>Select the evidence relevant to this application. You can choose and upload each PDF, PNG, or JPG from the generated application page.</Text>
        <View style={[styles.documentGrid, wide && styles.documentGridWide]}>
          {documentTypes.map(([value, label]) => (
            <View style={styles.documentItem} key={value}>
              <CheckRow checked={documents.includes(value)} onChange={() => toggleDocument(value)} title={label} />
            </View>
          ))}
        </View>
      </Card>

      <Card style={styles.section}>
        <Text style={styles.sectionNumber}>05</Text><Text style={styles.sectionHeading}>Credit-bureau consent</Text>
        <Field
          label="PAN for bureau lookup *"
          hint="Used only by the configured bureau adapter. The app does not derive or allow entry of a credit score."
          value={form.pan_for_bureau_lookup}
          onChangeText={set('pan_for_bureau_lookup')}
          autoCapitalize="characters"
          autoCorrect={false}
          maxLength={10}
        />
        <Banner title="How the decision works" body="After consent, the credit-bureau agent retrieves the available result. High-score cases continue through document and exception checks; low-score cases may be declined under configured bank policy; borderline or unavailable results require human review." />
        <CheckRow
          checked={consent}
          onChange={setConsent}
          title="I explicitly authorise this credit-bureau enquiry."
          body="I understand the result is used for this loan assessment and the decision and reference are retained in the audit trail."
        />
      </Card>

      <View style={styles.submitRow}>
        <Button label="Cancel" variant="ghost" onPress={() => router.back()} />
        <Button label="Submit and run assessment" loading={submitting} onPress={submit} />
      </View>
    </AppPage>
  );
}

const styles = StyleSheet.create({
  section: { gap: space.lg },
  sectionNumber: { color: colors.accent, fontSize: 10, fontWeight: '900', letterSpacing: 1.2 },
  sectionHeading: { color: colors.ink, fontSize: 20, fontWeight: '900', marginTop: -12 },
  pair: { gap: space.lg },
  pairWide: { flexDirection: 'row' },
  pairItem: { flex: 1, minWidth: 0 },
  supporting: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  documentGrid: { gap: 8 },
  documentGridWide: { flexDirection: 'row', flexWrap: 'wrap' },
  documentItem: { minWidth: 260, flexGrow: 1, flexBasis: '42%' },
  submitRow: { flexDirection: 'row', justifyContent: 'flex-end', flexWrap: 'wrap', gap: 10 },
});
