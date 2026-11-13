import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import React from 'react';

import { ListingForm } from '../src/components/ListingForm';

test('shows validation messages and does not submit invalid data', async () => {
  const onSubmit = jest.fn(async () => undefined);
  render(<ListingForm onSubmit={onSubmit} />);
  fireEvent.press(screen.getByRole('button', { name: 'Save listing' }));
  expect(await screen.findByText('Enter the produce name')).toBeTruthy();
  expect(screen.getByText('Enter a quantity, e.g. 120 or 12.5')).toBeTruthy();
  expect(screen.getByText('Enter a price in rand, e.g. 12.50')).toBeTruthy();
  expect(onSubmit).not.toHaveBeenCalled();
});

test('submits valid values with the chosen unit and quality', async () => {
  const onSubmit = jest.fn(async () => undefined);
  render(<ListingForm onSubmit={onSubmit} />);
  fireEvent.changeText(screen.getByLabelText('Produce'), 'Tomatoes');
  fireEvent.changeText(screen.getByLabelText('Quantity available'), '120');
  fireEvent.press(screen.getByLabelText('Unit: crate'));
  fireEvent.changeText(screen.getByLabelText('Price per unit (R)'), '85.50');
  fireEvent.press(screen.getByLabelText('Quality: Grade A'));
  fireEvent.press(screen.getByRole('button', { name: 'Save listing' }));
  await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
  expect((onSubmit.mock.calls[0] as unknown[])[0]).toMatchObject({
    produce_name: 'Tomatoes', quantity_available: '120', unit: 'CRATE', price_per_unit: '85.50', quality_grade: 'GRADE_A',
  });
});

test('shows field errors returned by the API', () => {
  render(<ListingForm onSubmit={jest.fn()} serverErrors={{ price_per_unit: 'Ensure this value is greater than 0.' }} />);
  expect(screen.getByText('Ensure this value is greater than 0.')).toBeTruthy();
});
