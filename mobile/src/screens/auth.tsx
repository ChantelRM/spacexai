import { zodResolver } from '@hookform/resolvers/zod';
import React, { useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { StyleSheet, Text, View } from 'react-native';
import { z } from 'zod';

import { parseApiError } from '../api/errors';
import { useAuth } from '../auth/AuthContext';
import type { AuthScreenProps } from '../navigation/types';
import { Body, Button, Choice, Field, FormError, Screen, Subtitle, Title } from '../ui/components';
import { colors, spacing } from '../ui/theme';

export function WelcomeScreen({ navigation }: AuthScreenProps<'Welcome'>) {
  return (
    <Screen style={styles.welcome}>
      <Text style={styles.logo} accessibilityElementsHidden>🌱</Text>
      <Title>Farm to Market Co-op</Title>
      <Body muted>
        Sell your produce to restaurants, shops and distributors, and team up with nearby farmers to buy inputs,
        share transport and equipment.
      </Body>
      <View style={styles.gap}>
        <Button title="I'm a farmer" onPress={() => navigation.navigate('Register', { role: 'FARMER' })} />
        <Button title="I'm a wholesale buyer" variant="secondary"
          onPress={() => navigation.navigate('Register', { role: 'WHOLESALE_BUYER' })} />
        <Button title="I already have an account — log in" variant="secondary"
          onPress={() => navigation.navigate('Login')} />
      </View>
    </Screen>
  );
}

const loginSchema = z.object({
  email: z.string().trim().email('Enter a valid email address'),
  password: z.string().min(1, 'Enter your password'),
});
type LoginValues = z.infer<typeof loginSchema>;

export function LoginScreen({ navigation }: AuthScreenProps<'Login'>) {
  const { login } = useAuth();
  const [formError, setFormError] = useState<string | null>(null);
  const { control, handleSubmit, formState: { errors, isSubmitting }, setError } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema), defaultValues: { email: '', password: '' },
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await login(values.email, values.password);
    } catch (e) {
      const err = parseApiError(e);
      Object.entries(err.fieldErrors).forEach(([f, m]) => {
        if (f === 'email' || f === 'password') setError(f, { message: m });
      });
      setFormError(err.code === 'authentication_failed' ? 'Wrong email or password.' : err.message);
    }
  });

  return (
    <Screen>
      <Title>Welcome back</Title>
      <FormError message={formError} />
      <Controller control={control} name="email" render={({ field }) => (
        <Field label="Email" value={field.value} onChangeText={field.onChange} onBlur={field.onBlur}
          autoCapitalize="none" keyboardType="email-address" autoComplete="email" error={errors.email?.message} />
      )} />
      <Controller control={control} name="password" render={({ field }) => (
        <Field label="Password" value={field.value} onChangeText={field.onChange} onBlur={field.onBlur}
          secureTextEntry autoComplete="password" error={errors.password?.message} />
      )} />
      <Button title="Log in" onPress={onSubmit} loading={isSubmitting} />
      <Button title="Forgot password?" variant="secondary" onPress={() => navigation.navigate('ForgotPassword')} />
      <Button title="Create an account" variant="secondary" onPress={() => navigation.navigate('Register')} />
    </Screen>
  );
}

const registerSchema = z.object({
  role: z.enum(['FARMER', 'WHOLESALE_BUYER'], { message: 'Choose an account type' }),
  display_name: z.string().trim().min(2, 'Enter your name or business name'),
  email: z.string().trim().email('Enter a valid email address'),
  phone_number: z.string().trim().max(20).optional(),
  password: z.string().min(8, 'Use at least 8 characters'),
});
type RegisterValues = z.infer<typeof registerSchema>;

export function RegisterScreen({ route }: AuthScreenProps<'Register'>) {
  const { register } = useAuth();
  const [formError, setFormError] = useState<string | null>(null);
  const { control, handleSubmit, formState: { errors, isSubmitting }, setError } = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { role: route.params?.role, display_name: '', email: '', phone_number: '', password: '' },
  });

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await register({ ...values, phone_number: values.phone_number || undefined });
    } catch (e) {
      const err = parseApiError(e);
      let mapped = false;
      Object.entries(err.fieldErrors).forEach(([f, m]) => {
        if (f in registerSchema.shape) {
          setError(f as keyof RegisterValues, { message: m });
          mapped = true;
        }
      });
      setFormError(mapped ? null : err.message);
    }
  });

  return (
    <Screen>
      <Title>Create your account</Title>
      <Body muted>Your account type can't be changed later.</Body>
      <FormError message={formError} />
      <Controller control={control} name="role" render={({ field }) => (
        <Choice label="I am a" value={field.value} onChange={field.onChange} error={errors.role?.message}
          options={[{ value: 'FARMER', label: 'Farmer' }, { value: 'WHOLESALE_BUYER', label: 'Wholesale buyer' }]} />
      )} />
      <Controller control={control} name="display_name" render={({ field }) => (
        <Field label="Name or business name" value={field.value} onChangeText={field.onChange}
          error={errors.display_name?.message} />
      )} />
      <Controller control={control} name="email" render={({ field }) => (
        <Field label="Email" value={field.value} onChangeText={field.onChange} autoCapitalize="none"
          keyboardType="email-address" error={errors.email?.message} />
      )} />
      <Controller control={control} name="phone_number" render={({ field }) => (
        <Field label="Phone (optional)" value={field.value} onChangeText={field.onChange} keyboardType="phone-pad"
          error={errors.phone_number?.message} />
      )} />
      <Controller control={control} name="password" render={({ field }) => (
        <Field label="Password" value={field.value} onChangeText={field.onChange} secureTextEntry
          error={errors.password?.message} />
      )} />
      <Button title="Create account" onPress={onSubmit} loading={isSubmitting} />
    </Screen>
  );
}

export function ForgotPasswordScreen() {
  return (
    <Screen>
      <Subtitle>Reset your password</Subtitle>
      <Body>
        Password reset by email is coming soon. For now, contact the platform administrator to reset your password.
      </Body>
    </Screen>
  );
}

const styles = StyleSheet.create({
  welcome: { justifyContent: 'center', flexGrow: 1, gap: spacing.lg },
  logo: { fontSize: 56, textAlign: 'center', color: colors.primary },
  gap: { gap: spacing.md },
});
