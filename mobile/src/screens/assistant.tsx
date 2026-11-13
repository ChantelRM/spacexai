import { useNavigation } from '@react-navigation/native';
import { useQueryClient } from '@tanstack/react-query';
import React, { useRef, useState } from 'react';
import { ActivityIndicator, FlatList, KeyboardAvoidingView, Platform, StyleSheet, Text, TextInput, View } from 'react-native';

import { ai } from '../api';
import { parseApiError } from '../api/errors';
import type { BuyerMatch, ChatResponse, FarmerMatch, PendingActionBrief } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { BuyerMatchCard, FarmerMatchCard } from '../components/cards';
import { ConfirmationCard } from '../components/ConfirmationCard';
import { Body, Button, Card, distanceText, money } from '../ui/components';
import { colors, radius, spacing } from '../ui/theme';

type ChatItem =
  | { id: string; kind: 'user' | 'assistant' | 'error'; text: string }
  | { id: string; kind: 'data'; data: ChatResponse['data'] }
  | { id: string; kind: 'pending'; action: PendingActionBrief };

const SUGGESTIONS = {
  FARMER: ['Which buyers need my produce?', 'Find fertiliser bulk buys near me', 'Find a tractor to hire next week'],
  WHOLESALE_BUYER: ['Find farmers selling 100 kg of tomatoes near me', 'Show my orders', 'Find farmers near me'],
};

type AnyResult = Record<string, unknown> & { results?: Record<string, unknown>[]; available?: boolean; reason?: string;
  message?: string };

/** Renders structured tool results from `data` as tappable cards. */
function DataCards({ data }: { data: ChatResponse['data'] }) {
  const navigation = useNavigation();
  return (
    <View style={styles.cards}>
      {Object.entries(data as Record<string, AnyResult>).map(([tool, result]) => {
        if (result?.available === false) {
          return <Card key={tool}><Body muted>{result.reason ?? 'Not available yet.'}</Body></Card>;
        }
        const rows = (result?.results ?? []) as Record<string, unknown>[];
        if (tool === 'search_recommended_farmers') {
          return rows.map((m) => <FarmerMatchCard key={`${tool}-${m.listing_id}`} match={m as unknown as FarmerMatch} />);
        }
        if (tool === 'search_buyer_requirements') {
          return rows.map((m) => <BuyerMatchCard key={`${tool}-${m.requirement_id}`} match={m as unknown as BuyerMatch} />);
        }
        if (tool === 'find_nearby_farmers') {
          return rows.map((f) => {
            const loc = f.location as { town?: string; distance?: never } | undefined;
            return (
              <Card key={`${tool}-${f.farmer_id}`} accessibilityLabel={String(f.display_name)}
                onPress={() => navigation.navigate('FarmerProfile', { id: Number(f.farmer_id) })}>
                <Text style={styles.cardTitle}>{String(f.display_name)}</Text>
                <Body muted>{loc?.town} · {distanceText(loc?.distance)}</Body>
              </Card>
            );
          });
        }
        if (tool === 'compare_listings' || tool === 'get_my_orders') {
          return rows.map((r) => {
            const isOrder = tool === 'get_my_orders';
            const id = Number(isOrder ? r.order_id : r.id);
            return (
              <Card key={`${tool}-${id}`} accessibilityLabel={isOrder ? `Order ${id}` : String(r.produce_name)}
                onPress={() => isOrder ? navigation.navigate('OrderDetail', { id })
                  : navigation.navigate('ListingDetail', { id })}>
                <Text style={styles.cardTitle}>{isOrder ? `Order #${id} · ${String(r.status)}` : String(r.produce_name)}</Text>
                <Body muted>{isOrder ? money(r.total_amount as number) : `${money(r.price_per_unit as string)}/unit`}</Body>
              </Card>
            );
          });
        }
        const target = ({
          find_bulk_purchases: ['BulkDetail', 'bulk_purchase_id'], find_transport_requests: ['TransportDetail', 'transport_request_id'],
          find_farmer_groups: ['GroupDetail', 'group_id'], find_equipment: ['EquipmentDetail', 'equipment_id'],
        } as Record<string, [string, string]>)[tool];
        if (target) {
          return rows.map((r) => (
            <Card key={`${tool}-${String(r[target[1]])}`} accessibilityLabel={String(r.name ?? r.title ?? r.destination)}
              onPress={() => navigation.navigate(target[0] as 'BulkDetail', { id: Number(r[target[1]]) })}>
              <Text style={styles.cardTitle}>{String(r.name ?? r.title ?? r.destination)}</Text>
              <Body muted>{distanceText((r.distance ?? (r.from_area as { distance?: never })?.distance
                ?? (r.area as { distance?: never })?.distance) as never)}</Body>
            </Card>
          ));
        }
        return null;
      })}
    </View>
  );
}

export function AssistantScreen() {
  const { role } = useAuth();
  const queryClient = useQueryClient();
  const [items, setItems] = useState<ChatItem[]>([{
    id: 'hello', kind: 'assistant',
    text: 'Hi! I can find matches, explain them and prepare actions for you to confirm. What do you need?',
  }]);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const conversationId = useRef<string | undefined>(undefined);
  const list = useRef<FlatList<ChatItem>>(null);
  const add = (...next: ChatItem[]) => setItems((prev) => [...prev, ...next]);

  async function send(message: string) {
    const trimmed = message.trim();
    if (!trimmed || busy) return;
    setText('');
    add({ id: `u${Date.now()}`, kind: 'user', text: trimmed });
    setBusy(true);
    try {
      const res = await ai.chat(trimmed, conversationId.current);
      conversationId.current = res.conversation_id;
      const next: ChatItem[] = [{ id: `a${Date.now()}`, kind: 'assistant', text: res.reply }];
      if (res.data && Object.keys(res.data).length) next.push({ id: `d${Date.now()}`, kind: 'data', data: res.data });
      if (res.pending_action) next.push({ id: `p${res.pending_action.id}`, kind: 'pending', action: res.pending_action });
      add(...next);
    } catch (e) {
      const err = parseApiError(e);
      add({
        id: `e${Date.now()}`, kind: 'error',
        text: err.status === 503 || err.code === 'ai_service_unavailable'
          ? 'The assistant is unavailable right now. Everything else in the app still works. Please try again later.'
          : err.code === 'throttled' ? 'You are sending messages too quickly. Wait a moment and try again.' : err.message,
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={90}>
      <FlatList
        ref={list}
        data={items}
        keyExtractor={(i) => i.id}
        contentContainerStyle={styles.list}
        onContentSizeChange={() => list.current?.scrollToEnd({ animated: true })}
        renderItem={({ item }) => {
          if (item.kind === 'data') return <DataCards data={item.data} />;
          if (item.kind === 'pending') {
            return (
              <ConfirmationCard action={item.action} onConfirm={ai.confirm} onCancel={ai.cancel}
                onDone={() => void queryClient.invalidateQueries()} />
            );
          }
          return (
            <View style={[styles.bubble, item.kind === 'user' ? styles.user : styles.bot, item.kind === 'error' && styles.err]}>
              <Text style={item.kind === 'user' ? styles.userText : styles.botText}>{item.text}</Text>
            </View>
          );
        }}
        ListFooterComponent={busy ? (
          <View style={styles.thinking} accessibilityLiveRegion="polite">
            <ActivityIndicator color={colors.primary} />
            <Text style={styles.muted}>Thinking… this may take a moment.</Text>
          </View>
        ) : items.length === 1 ? (
          <View style={styles.cards}>
            {(SUGGESTIONS[role ?? 'FARMER'] ?? []).map((s) => (
              <Button key={s} small variant="secondary" title={s} onPress={() => void send(s)} />
            ))}
          </View>
        ) : null}
      />
      <View style={styles.composer}>
        <TextInput
          value={text}
          onChangeText={setText}
          placeholder="Ask the assistant…"
          accessibilityLabel="Message to the assistant"
          style={styles.input}
          maxLength={2000}
          multiline
        />
        <Button small title="Send" onPress={() => void send(text)} disabled={busy || !text.trim()} />
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.background },
  list: { padding: spacing.md, gap: spacing.sm },
  bubble: { maxWidth: '88%', padding: spacing.md, borderRadius: radius.lg },
  user: { alignSelf: 'flex-end', backgroundColor: colors.primary },
  bot: { alignSelf: 'flex-start', backgroundColor: '#fff', borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  err: { backgroundColor: colors.dangerLight },
  userText: { color: '#fff', fontSize: 15 },
  botText: { color: colors.text, fontSize: 15, lineHeight: 21 },
  cards: { gap: spacing.sm },
  cardTitle: { fontWeight: '700', color: colors.text },
  thinking: { flexDirection: 'row', gap: spacing.sm, alignItems: 'center', padding: spacing.sm },
  muted: { color: colors.muted },
  composer: {
    flexDirection: 'row', gap: spacing.sm, padding: spacing.sm, alignItems: 'flex-end', backgroundColor: '#fff',
    borderTopWidth: StyleSheet.hairlineWidth, borderColor: colors.border,
  },
  input: {
    flex: 1, minHeight: 44, maxHeight: 120, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm, fontSize: 15,
  },
});
