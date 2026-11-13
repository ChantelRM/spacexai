import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { AxiosError, AxiosResponse } from 'axios';
import React from 'react';

import { ConfirmationCard } from '../src/components/ConfirmationCard';

const NOW = new Date('2026-11-13T10:00:00Z').getTime();
const action = {
  id: 'abc-123',
  tool_name: 'create_order',
  summary: 'Place an order with Thandi: 20 kg Tomatoes at R14.00/kg = R280.00. Total R280.00.',
  expires_at: new Date(NOW + 15 * 60000).toISOString(),
};
const result = { id: 'abc-123', status: 'confirmed', tool_name: 'create_order', summary: action.summary,
  executed_at: null, result: {} };

test('shows the summary and commits nothing until Confirm is tapped', async () => {
  const onConfirm = jest.fn(async () => result);
  const onCancel = jest.fn();
  render(<ConfirmationCard action={action} onConfirm={onConfirm} onCancel={onCancel} now={() => NOW} />);
  expect(screen.getByText(action.summary)).toBeTruthy();
  expect(screen.getByText(/Nothing has been done yet\. Expires in 15 min/)).toBeTruthy();
  expect(onConfirm).not.toHaveBeenCalled();

  fireEvent.press(screen.getByRole('button', { name: `Confirm: ${action.summary}` }));
  await waitFor(() => expect(screen.getByText('✓ Confirmed and done.')).toBeTruthy());
  expect(onConfirm).toHaveBeenCalledTimes(1);
  expect(onConfirm).toHaveBeenCalledWith('abc-123');
  expect(screen.queryByRole('button', { name: /Confirm/ })).toBeNull(); // can't confirm twice
});

test('cancel calls the cancel endpoint', async () => {
  const onCancel = jest.fn(async () => ({ ...result, status: 'cancelled' }));
  render(<ConfirmationCard action={action} onConfirm={jest.fn()} onCancel={onCancel} now={() => NOW} />);
  fireEvent.press(screen.getByRole('button', { name: 'Cancel' }));
  await waitFor(() => expect(screen.getByText('Cancelled. Nothing was done.')).toBeTruthy());
  expect(onCancel).toHaveBeenCalledWith('abc-123');
});

test('expired actions cannot be confirmed', async () => {
  const later = NOW + 16 * 60000;
  render(<ConfirmationCard action={action} onConfirm={jest.fn()} onCancel={jest.fn()} now={() => later} />);
  expect(screen.getByText('This expired. Ask the assistant again.')).toBeTruthy();
  expect(screen.queryByRole('button', { name: /Confirm/ })).toBeNull();
});

test('server-side expiry is shown as expired', async () => {
  const response = { status: 410, data: { error: { code: 'action_expired', message: 'Expired', details: {} } } } as AxiosResponse;
  const onConfirm = jest.fn(async () => { throw new AxiosError('410', '410', undefined, null, response); });
  render(<ConfirmationCard action={action} onConfirm={onConfirm} onCancel={jest.fn()} now={() => NOW} />);
  fireEvent.press(screen.getByRole('button', { name: `Confirm: ${action.summary}` }));
  await waitFor(() => expect(screen.getByText('This expired. Ask the assistant again.')).toBeTruthy());
});
