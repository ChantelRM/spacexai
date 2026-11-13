import { zodResolver } from '@hookform/resolvers/zod';
import React from 'react';
import { Controller, useForm } from 'react-hook-form';
import { View } from 'react-native';
import { z } from 'zod';

import type { QualityGrade, Unit } from '../api/types';
import { QUALITY, UNITS } from '../constants';
import { Button, Choice, Field } from '../ui/components';

const decimal = (msg: string) => z.string().trim().regex(/^\d+(\.\d{1,2})?$/, msg);

export const listingSchema = z.object({
  produce_name: z.string().trim().min(2, 'Enter the produce name'),
  quantity_available: decimal('Enter a quantity, e.g. 120 or 12.5'),
  unit: z.enum(['KG', 'TONNE', 'BAG', 'CRATE', 'BOX', 'DOZEN', 'LITRE', 'UNIT'], { message: 'Choose a unit' }),
  price_per_unit: decimal('Enter a price in rand, e.g. 12.50').refine((v) => Number(v) > 0, 'Price must be more than 0'),
  quality_grade: z.enum(['PREMIUM', 'ORGANIC', 'GRADE_A', 'GRADE_B', 'STANDARD']),
  available_from: z.string().trim().regex(/^\d{4}-\d{2}-\d{2}$/, 'Use YYYY-MM-DD').or(z.literal('')),
  description: z.string().max(2000).optional(),
});
export type ListingValues = z.infer<typeof listingSchema>;

export const emptyListing: ListingValues = {
  produce_name: '', quantity_available: '', unit: 'KG', price_per_unit: '', quality_grade: 'STANDARD',
  available_from: '', description: '',
};

/** Create/edit form. ``serverErrors`` are field errors from the API error format. */
export function ListingForm({ initial = emptyListing, onSubmit, serverErrors = {}, submitLabel = 'Save listing' }: {
  initial?: ListingValues;
  onSubmit: (values: ListingValues) => Promise<void>;
  serverErrors?: Record<string, string>;
  submitLabel?: string;
}) {
  const { control, handleSubmit, formState: { errors, isSubmitting } } = useForm<ListingValues>({
    resolver: zodResolver(listingSchema), defaultValues: initial,
  });
  const err = (name: keyof ListingValues) => errors[name]?.message ?? serverErrors[name];

  return (
    <View style={{ gap: 12 }}>
      <Controller control={control} name="produce_name" render={({ field }) => (
        <Field label="Produce" value={field.value} onChangeText={field.onChange} placeholder="e.g. Tomatoes"
          error={err('produce_name')} />
      )} />
      <Controller control={control} name="quantity_available" render={({ field }) => (
        <Field label="Quantity available" value={field.value} onChangeText={field.onChange} keyboardType="decimal-pad"
          error={err('quantity_available')} />
      )} />
      <Controller control={control} name="unit" render={({ field }) => (
        <Choice<Unit> label="Unit" options={UNITS} value={field.value} onChange={field.onChange} error={err('unit')} />
      )} />
      <Controller control={control} name="price_per_unit" render={({ field }) => (
        <Field label="Price per unit (R)" value={field.value} onChangeText={field.onChange} keyboardType="decimal-pad"
          error={err('price_per_unit')} />
      )} />
      <Controller control={control} name="quality_grade" render={({ field }) => (
        <Choice<QualityGrade> label="Quality" options={QUALITY} value={field.value} onChange={field.onChange} />
      )} />
      <Controller control={control} name="available_from" render={({ field }) => (
        <Field label="Available from (YYYY-MM-DD, optional)" value={field.value} onChangeText={field.onChange}
          placeholder="Today if empty" error={err('available_from')} />
      )} />
      <Controller control={control} name="description" render={({ field }) => (
        <Field label="Description (optional)" value={field.value} onChangeText={field.onChange} multiline />
      )} />
      <Button title={submitLabel} onPress={handleSubmit(onSubmit)} loading={isSubmitting} />
    </View>
  );
}
