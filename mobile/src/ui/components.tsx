import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  View,
  ViewStyle,
} from 'react-native';

import { parseApiError } from '../api/errors';
import type { Distance } from '../api/types';
import { colors, font, radius, spacing } from './theme';

export function Screen({ children, refreshing, onRefresh, style }: {
  children: React.ReactNode;
  refreshing?: boolean;
  onRefresh?: () => void;
  style?: ViewStyle;
}) {
  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={[styles.screenContent, style]}
      keyboardShouldPersistTaps="handled"
      refreshControl={onRefresh ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} /> : undefined}
    >
      {children}
    </ScrollView>
  );
}

export function Title({ children }: { children: React.ReactNode }) {
  return <Text style={styles.title} accessibilityRole="header">{children}</Text>;
}

export function Subtitle({ children }: { children: React.ReactNode }) {
  return <Text style={styles.subtitle}>{children}</Text>;
}

export function Body({ children, muted, style }: { children: React.ReactNode; muted?: boolean; style?: object }) {
  return <Text style={[styles.body, muted && styles.muted, style]}>{children}</Text>;
}

export function Card({ children, onPress, accessibilityLabel, style }: {
  children: React.ReactNode;
  onPress?: () => void;
  accessibilityLabel?: string;
  style?: ViewStyle;
}) {
  if (!onPress) return <View style={[styles.card, style]}>{children}</View>;
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      style={({ pressed }) => [styles.card, pressed && styles.pressed, style]}
    >
      {children}
    </Pressable>
  );
}

export function Button({ title, onPress, variant = 'primary', loading, disabled, accessibilityLabel, small }: {
  title: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'danger';
  loading?: boolean;
  disabled?: boolean;
  accessibilityLabel?: string;
  small?: boolean;
}) {
  const inactive = disabled || loading;
  return (
    <Pressable
      onPress={onPress}
      disabled={inactive}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? title}
      accessibilityState={{ disabled: !!inactive, busy: !!loading }}
      style={({ pressed }) => [
        styles.button,
        small && styles.buttonSmall,
        variant === 'secondary' && styles.buttonSecondary,
        variant === 'danger' && styles.buttonDanger,
        inactive && styles.disabled,
        pressed && styles.pressed,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={variant === 'secondary' ? colors.primary : '#fff'} />
      ) : (
        <Text style={[styles.buttonText, variant === 'secondary' && styles.buttonTextSecondary]}>{title}</Text>
      )}
    </Pressable>
  );
}

export function Field({ label, error, ...props }: TextInputProps & { label: string; error?: string }) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        placeholderTextColor={colors.muted}
        style={[styles.input, error && styles.inputError, props.multiline && styles.multiline]}
        {...props}
      />
      {error ? <Text style={styles.errorText} accessibilityLiveRegion="polite">{error}</Text> : null}
    </View>
  );
}

/** A row of pill buttons for picking one option (role, unit, province, ...). */
export function Choice<T extends string>({ label, options, value, onChange, error }: {
  label: string;
  options: { value: T; label: string }[];
  value: T | undefined | null;
  onChange: (value: T) => void;
  error?: string;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.choices}>
        {options.map((o) => {
          const selected = o.value === value;
          return (
            <Pressable
              key={o.value}
              onPress={() => onChange(o.value)}
              accessibilityRole="radio"
              accessibilityState={{ selected }}
              accessibilityLabel={`${label}: ${o.label}`}
              style={[styles.choice, selected && styles.choiceSelected]}
            >
              <Text style={[styles.choiceText, selected && styles.choiceTextSelected]}>{o.label}</Text>
            </Pressable>
          );
        })}
      </View>
      {error ? <Text style={styles.errorText}>{error}</Text> : null}
    </View>
  );
}

export function Badge({ text, tone = 'neutral' }: { text: string; tone?: 'neutral' | 'good' | 'warn' | 'bad' }) {
  const bg = { neutral: '#ECEFF1', good: colors.primaryLight, warn: colors.warningLight, bad: colors.dangerLight }[tone];
  return <Text style={[styles.badge, { backgroundColor: bg }]}>{text}</Text>;
}

export function Row({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  return <View style={[styles.row, style]}>{children}</View>;
}

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <View style={styles.center} accessibilityLabel={label}>
      <ActivityIndicator color={colors.primary} size="large" />
      <Text style={styles.muted}>{label}</Text>
    </View>
  );
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <View style={styles.center}>
      <Text style={styles.subtitle}>{title}</Text>
      {hint ? <Text style={[styles.muted, styles.centerText]}>{hint}</Text> : null}
    </View>
  );
}

export function ErrorView({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const parsed = parseApiError(error);
  return (
    <View style={styles.center} accessibilityLiveRegion="polite">
      <Text style={styles.errorTitle}>Something went wrong</Text>
      <Text style={[styles.muted, styles.centerText]}>{parsed.message}</Text>
      {onRetry ? <Button title="Try again" variant="secondary" onPress={onRetry} small /> : null}
    </View>
  );
}

export function FormError({ message }: { message?: string | null }) {
  if (!message) return null;
  return <Text style={styles.formError} accessibilityLiveRegion="polite">{message}</Text>;
}

/** "≈ 12 km away" or "Same municipality". Never coordinates. */
export function distanceText(distance?: Distance | null): string {
  if (!distance) return 'Distance unknown';
  return distance.basis === 'gps' ? `${distance.label} away` : distance.label;
}

export function money(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  const n = typeof value === 'number' ? value : Number(value);
  return `R${n.toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function qty(value: string | number, unit: string): string {
  const n = typeof value === 'number' ? value : Number(value);
  return `${Number.isInteger(n) ? n : n.toFixed(2).replace(/0+$/, '')} ${unit.toLowerCase()}`;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  screenContent: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xl * 2 },
  title: { fontSize: font.heading, fontWeight: '700', color: colors.text },
  subtitle: { fontSize: font.title, fontWeight: '600', color: colors.text },
  body: { fontSize: font.body, color: colors.text, lineHeight: 21 },
  muted: { color: colors.muted, fontSize: font.small },
  card: {
    backgroundColor: colors.card, borderRadius: radius.md, padding: spacing.md, gap: spacing.xs,
    borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  pressed: { opacity: 0.75 },
  button: {
    backgroundColor: colors.primary, borderRadius: radius.md, paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg, alignItems: 'center', justifyContent: 'center', minHeight: 48,
  },
  buttonSmall: { minHeight: 40, paddingVertical: spacing.sm },
  buttonSecondary: { backgroundColor: '#fff', borderWidth: 1, borderColor: colors.primary },
  buttonDanger: { backgroundColor: colors.danger },
  buttonText: { color: '#fff', fontWeight: '600', fontSize: font.body },
  buttonTextSecondary: { color: colors.primary },
  disabled: { opacity: 0.5 },
  field: { gap: spacing.xs },
  label: { fontSize: font.small, fontWeight: '600', color: colors.text },
  input: {
    backgroundColor: '#fff', borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm, fontSize: font.body, minHeight: 44, color: colors.text,
  },
  multiline: { minHeight: 88, textAlignVertical: 'top' },
  inputError: { borderColor: colors.danger },
  errorText: { color: colors.danger, fontSize: font.small },
  choices: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  choice: {
    borderWidth: 1, borderColor: colors.border, borderRadius: 999, paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm, backgroundColor: '#fff', minHeight: 36, justifyContent: 'center',
  },
  choiceSelected: { backgroundColor: colors.primary, borderColor: colors.primary },
  choiceText: { color: colors.text, fontSize: font.small },
  choiceTextSelected: { color: '#fff', fontWeight: '600' },
  badge: {
    alignSelf: 'flex-start', paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: 999,
    fontSize: 12, overflow: 'hidden', color: colors.text,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, flexWrap: 'wrap' },
  center: { alignItems: 'center', justifyContent: 'center', padding: spacing.xl, gap: spacing.sm },
  centerText: { textAlign: 'center' },
  errorTitle: { fontSize: font.title, fontWeight: '600', color: colors.danger },
  formError: {
    color: colors.danger, backgroundColor: colors.dangerLight, padding: spacing.sm, borderRadius: radius.sm,
  },
});
