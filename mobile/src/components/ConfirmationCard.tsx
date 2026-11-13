import React, { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { parseApiError } from '../api/errors';
import type { ActionResult, PendingActionBrief } from '../api/types';
import { Body, Button, Row } from '../ui/components';
import { colors, radius, spacing } from '../ui/theme';

type State = 'pending' | 'working' | 'confirmed' | 'cancelled' | 'expired' | 'error';

function minutesLeft(expiresAt: string, now: number) {
  return Math.max(0, Math.ceil((new Date(expiresAt).getTime() - now) / 60000));
}

/**
 * Shows an action the assistant proposed. NOTHING is committed until the user
 * taps Confirm, which calls POST /ai/actions/{id}/confirm/.
 */
export function ConfirmationCard({ action, onConfirm, onCancel, onDone, now = Date.now }: {
  action: PendingActionBrief;
  onConfirm: (id: string) => Promise<ActionResult>;
  onCancel: (id: string) => Promise<ActionResult>;
  onDone?: (result: ActionResult | null, state: State) => void;
  now?: () => number;
}) {
  const [state, setState] = useState<State>(() => (minutesLeft(action.expires_at, now()) === 0 ? 'expired' : 'pending'));
  const [message, setMessage] = useState<string | null>(null);
  const [left, setLeft] = useState(() => minutesLeft(action.expires_at, now()));

  useEffect(() => {
    if (state !== 'pending') return undefined;
    const timer = setInterval(() => {
      const m = minutesLeft(action.expires_at, now());
      setLeft(m);
      if (m === 0) setState('expired');
    }, 30000);
    return () => clearInterval(timer);
  }, [action.expires_at, now, state]);

  async function run(kind: 'confirm' | 'cancel') {
    setState('working');
    setMessage(null);
    try {
      const result = await (kind === 'confirm' ? onConfirm : onCancel)(action.id);
      const next = kind === 'confirm' ? 'confirmed' : 'cancelled';
      setState(next);
      onDone?.(result, next);
    } catch (e) {
      const err = parseApiError(e);
      if (err.code === 'action_expired') {
        setState('expired');
      } else {
        setState(err.code === 'action_not_pending' ? 'cancelled' : 'error');
        setMessage(err.message);
      }
      onDone?.(null, 'error');
    }
  }

  return (
    <View style={styles.card} accessibilityRole="summary" accessibilityLabel="Action waiting for your confirmation">
      <Text style={styles.heading}>Please confirm</Text>
      <Body>{action.summary}</Body>
      {state === 'pending' || state === 'working' ? (
        <>
          <Body muted>Nothing has been done yet. Expires in {left} min.</Body>
          <Row>
            <Button small title="Confirm" onPress={() => void run('confirm')} loading={state === 'working'}
              accessibilityLabel={`Confirm: ${action.summary}`} />
            <Button small variant="secondary" title="Cancel" onPress={() => void run('cancel')}
              disabled={state === 'working'} />
          </Row>
        </>
      ) : null}
      {state === 'confirmed' ? <Text style={styles.ok}>✓ Confirmed and done.</Text> : null}
      {state === 'cancelled' ? <Text style={styles.muted}>Cancelled. Nothing was done.</Text> : null}
      {state === 'expired' ? <Text style={styles.muted}>This expired. Ask the assistant again.</Text> : null}
      {state === 'error' ? <Text style={styles.err}>{message}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 2, borderColor: colors.accent, backgroundColor: colors.warningLight, borderRadius: radius.md,
    padding: spacing.md, gap: spacing.sm,
  },
  heading: { fontWeight: '700', fontSize: 16, color: colors.text },
  ok: { color: colors.primaryDark, fontWeight: '600' },
  muted: { color: colors.muted },
  err: { color: colors.danger },
});
