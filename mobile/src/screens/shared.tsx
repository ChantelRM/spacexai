import { useNavigation } from '@react-navigation/native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import React, { useState } from 'react';
import { Alert, FlatList, Image, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { farmers, marketplace, messaging, notifications, orders } from '../api';
import { parseApiError } from '../api/errors';
import type { Order } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { ListingCard, OrderRow } from '../components/cards';
import { label, ORDER_STATUS_LABEL, QUALITY, STATUS_TONE } from '../constants';
import { POLL_INTERVAL_MS } from '../config';
import type { AppScreenProps } from '../navigation/types';
import { Badge, Body, Button, Card, Choice, distanceText, ErrorView, Field, FormError, Loading, money, qty, Row, Screen,
  Subtitle, Title } from '../ui/components';
import { QueryScreen } from '../ui/QueryScreen';
import { colors, radius, spacing } from '../ui/theme';

const STATUS_FILTERS = [
  { value: 'open', label: 'Open' }, { value: 'history', label: 'History' }, { value: 'all', label: 'All' },
];
const FILTER_STATUS: Record<string, string | undefined> = {
  open: 'PENDING,ACCEPTED,DISPATCHED,DELIVERED', history: 'COMPLETED,REJECTED,CANCELLED', all: undefined,
};

export function OrdersScreen() {
  const navigation = useNavigation();
  const { role } = useAuth();
  const [filter, setFilter] = useState('open');
  const query = useQuery({ queryKey: ['orders', filter], queryFn: () => orders.list(FILTER_STATUS[filter]),
    refetchInterval: POLL_INTERVAL_MS });
  return (
    <QueryScreen query={query} isEmpty={(d) => d.results.length === 0}
      emptyTitle={role === 'FARMER' ? 'No incoming orders' : 'No orders yet'}
      emptyHint={role === 'FARMER' ? undefined : 'Find produce in the Marketplace to place an order.'}
      header={<Choice label="Show" options={STATUS_FILTERS} value={filter} onChange={setFilter} />}>
      {(data) => data.results.map((o) => (
        <OrderRow key={o.id} order={o} onPress={() => navigation.navigate('OrderDetail', { id: o.id })} />
      ))}
    </QueryScreen>
  );
}

function OrderActions({ order, onAct }: { order: Order; onAct: (action: Parameters<typeof orders.act>[1], reason?: string) => void }) {
  const { user } = useAuth();
  const [reason, setReason] = useState('');
  const isFarmer = user?.id === order.farmer.id;
  const s = order.status;
  return (
    <View style={styles.actions}>
      {(s === 'PENDING' && isFarmer) || (s === 'ACCEPTED') ? (
        <Field label={isFarmer && s === 'PENDING' ? 'Reason (needed to decline)' : 'Reason (needed to cancel)'}
          value={reason} onChangeText={setReason} />
      ) : null}
      <Row>
        {isFarmer && s === 'PENDING' ? <Button small title="Accept" onPress={() => onAct('accept')} /> : null}
        {isFarmer && s === 'PENDING' ? <Button small variant="danger" title="Decline" onPress={() => onAct('reject', reason)} /> : null}
        {isFarmer && s === 'ACCEPTED' ? <Button small title="Mark dispatched" onPress={() => onAct('dispatch')} /> : null}
        {!isFarmer && s === 'DISPATCHED' ? <Button small title="Confirm received" onPress={() => onAct('confirm-receipt')} /> : null}
        {s === 'DELIVERED' ? <Button small title="Mark complete" onPress={() => onAct('complete')} /> : null}
        {(!isFarmer && s === 'PENDING') || s === 'ACCEPTED' ? (
          <Button small variant="secondary" title="Cancel order" onPress={() => onAct('cancel', reason)} />
        ) : null}
      </Row>
    </View>
  );
}

export function OrderDetailScreen({ route, navigation }: AppScreenProps<'OrderDetail'>) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ['order', route.params.id], queryFn: () => orders.get(route.params.id),
    refetchInterval: POLL_INTERVAL_MS });
  const [error, setError] = useState<string | null>(null);
  const act = useMutation({
    mutationFn: ({ action, reason }: { action: Parameters<typeof orders.act>[1]; reason?: string }) =>
      orders.act(route.params.id, action, reason),
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ['order', route.params.id] });
      void queryClient.invalidateQueries({ queryKey: ['orders'] });
    },
    onError: (e) => setError(parseApiError(e).message),
  });
  const payment = useMutation({
    mutationFn: (status: string) => orders.setPayment(route.params.id, status),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['order', route.params.id] }),
    onError: (e) => setError(parseApiError(e).message),
  });

  return (
    <QueryScreen query={query}>
      {(o) => {
        const isFarmer = user?.id === o.farmer.id;
        const other = isFarmer ? o.buyer : o.farmer;
        return (
          <>
            <Row style={styles.between}>
              <Title>Order #{o.id}</Title>
              <Badge text={ORDER_STATUS_LABEL[o.status] ?? o.status} tone={STATUS_TONE[o.status]} />
            </Row>
            <Body>{isFarmer ? 'From' : 'To'} {other.display_name}</Body>
            <FormError message={error} />
            <Card>
              {o.items.map((i) => (
                <Body key={i.id}>{qty(i.quantity, i.unit)} {i.produce_name} × {money(i.price_per_unit)} = {money(i.line_total)}</Body>
              ))}
              <Text style={styles.total}>Total {money(o.total_amount)}</Text>
              {o.delivery_date ? <Body muted>Delivery by {o.delivery_date}</Body> : null}
              {o.rejection_reason ? <Body muted>Declined: {o.rejection_reason}</Body> : null}
              {o.cancellation_reason ? <Body muted>Cancelled: {o.cancellation_reason}</Body> : null}
            </Card>
            <OrderActions order={o} onAct={(action, reason) => act.mutate({ action, reason })} />
            <Card>
              <Body>Payment: {o.payment_status?.toLowerCase()} (settled outside the app)</Body>
              <Row>
                {isFarmer && o.payment_status !== 'PAID' && ['ACCEPTED', 'DISPATCHED', 'DELIVERED', 'COMPLETED'].includes(o.status)
                  ? <Button small title="Mark paid" onPress={() => payment.mutate('PAID')} /> : null}
                {o.payment_status !== 'DISPUTED'
                  ? <Button small variant="secondary" title="Report a problem" onPress={() => payment.mutate('DISPUTED')} /> : null}
              </Row>
            </Card>
            <Button variant="secondary" title={`Message ${other.display_name}`} onPress={async () => {
              const thread = await messaging.start(other.id, undefined, o.id);
              navigation.navigate('Thread', { id: thread.id, title: other.display_name });
            }} />
            <Subtitle>History</Subtitle>
            {o.history.map((h, idx) => (
              <Body key={idx} muted>{new Date(h.created_at).toLocaleString('en-ZA')}: {ORDER_STATUS_LABEL[h.to_status]}
                {h.note ? ` · ${h.note}` : ''}</Body>
            ))}
          </>
        );
      }}
    </QueryScreen>
  );
}

export function ListingDetailScreen({ route, navigation }: AppScreenProps<'ListingDetail'>) {
  const { role } = useAuth();
  const query = useQuery({ queryKey: ['public-listing', route.params.id], queryFn: () => marketplace.listing(route.params.id) });
  return (
    <QueryScreen query={query}>
      {(l) => (
        <>
          {l.images.length ? (
            <ScrollView horizontal contentContainerStyle={styles.photos}>
              {l.images.map((uri) => <Image key={uri} source={{ uri }} style={styles.photo} accessibilityLabel="Produce photo" />)}
            </ScrollView>
          ) : null}
          <Title>{l.produce_name}</Title>
          <Text style={styles.total}>{money(l.price_per_unit)}/{l.unit.toLowerCase()}</Text>
          <Body>{qty(l.quantity_available, l.unit)} available · {label(QUALITY, l.quality_grade)}</Body>
          <Body muted>Available from {l.available_from}{l.available_until ? ` until ${l.available_until}` : ''}</Body>
          {l.description ? <Body>{l.description}</Body> : null}
          <Card onPress={() => navigation.navigate('FarmerProfile', { id: l.farmer.id })} accessibilityLabel="Farmer profile">
            <Body>{l.farmer.farm_name ?? l.farmer.display_name}{l.farmer.is_verified ? ' ✔ Verified' : ''}</Body>
            <Body muted>{l.location?.town}, {l.location?.municipality} · {distanceText(l.location?.distance)}</Body>
          </Card>
          {role === 'WHOLESALE_BUYER' && l.status === 'ACTIVE' ? (
            <>
              <Button title="Order this" onPress={() => navigation.navigate('PlaceOrder', { listingId: l.id })} />
              <Button variant="secondary" title="Message farmer" onPress={async () => {
                const thread = await messaging.start(l.farmer.id, `Hi, I'm interested in your ${l.produce_name}.`);
                navigation.navigate('Thread', { id: thread.id, title: l.farmer.display_name });
              }} />
            </>
          ) : null}
        </>
      )}
    </QueryScreen>
  );
}

export function FarmerProfileScreen({ route, navigation }: AppScreenProps<'FarmerProfile'>) {
  const profile = useQuery({ queryKey: ['farmer', route.params.id], queryFn: () => farmers.publicProfile(route.params.id) });
  const listings = useQuery({ queryKey: ['marketplace', { farmer_id: route.params.id }],
    queryFn: () => marketplace.search({ farmer_id: route.params.id }) });
  return (
    <QueryScreen query={profile}>
      {(f) => (
        <>
          <Title>{f.farm_name ?? f.display_name}</Title>
          <Row>
            {f.is_verified ? <Badge text="✔ Verified" tone="good" /> : null}
            <Badge text={`${f.completed_orders_count} completed orders`} />
          </Row>
          <Body muted>{f.location?.town}, {f.location?.municipality}, {f.location?.province_display} · {distanceText(f.location?.distance)}</Body>
          {f.bio ? <Body>{f.bio}</Body> : null}
          {f.main_produce.length ? <Body>Grows: {f.main_produce.join(', ')}</Body> : null}
          <Subtitle>Listings ({f.active_listings_count})</Subtitle>
          {listings.data?.results.map((l) => (
            <ListingCard key={l.id} listing={l} onPress={() => navigation.push('ListingDetail', { id: l.id })} />
          ))}
        </>
      )}
    </QueryScreen>
  );
}

export function ProfileScreen() {
  const navigation = useNavigation();
  const { user, logout } = useAuth();
  return (
    <Screen>
      <Title>{user?.display_name}</Title>
      <Body muted>{user?.email} · {user?.role === 'FARMER' ? 'Farmer' : 'Wholesale buyer'}</Body>
      <Button title="Edit profile & location" variant="secondary"
        onPress={() => navigation.navigate('Onboarding', { editing: true })} />
      <Button title="Messages" variant="secondary" onPress={() => navigation.navigate('Messages')} />
      <Button title="Notifications" variant="secondary" onPress={() => navigation.navigate('Notifications')} />
      <Body muted>Your exact GPS location is never shown to other users.</Body>
      <Button title="Log out" variant="danger" onPress={() => Alert.alert('Log out?', undefined, [
        { text: 'Stay', style: 'cancel' }, { text: 'Log out', style: 'destructive', onPress: () => void logout() },
      ])} />
    </Screen>
  );
}

export function MessagesScreen({ navigation }: AppScreenProps<'Messages'>) {
  const query = useQuery({ queryKey: ['threads'], queryFn: messaging.threads, refetchInterval: POLL_INTERVAL_MS });
  return (
    <QueryScreen query={query} isEmpty={(d) => d.results.length === 0} emptyTitle="No conversations yet"
      emptyHint="Message a farmer or buyer from a listing or an order.">
      {(data) => data.results.map((t) => {
        const other = t.other_party as { display_name: string };
        const last = t.last_message as { body: string } | null;
        return (
          <Card key={t.id} onPress={() => navigation.navigate('Thread', { id: t.id, title: other.display_name })}
            accessibilityLabel={`Conversation with ${other.display_name}`}>
            <Row style={styles.between}>
              <Text style={styles.name}>{other.display_name}</Text>
              {t.unread_count ? <Badge text={`${t.unread_count} new`} tone="warn" /> : null}
            </Row>
            {last ? <Body muted>{last.body}</Body> : null}
          </Card>
        );
      })}
    </QueryScreen>
  );
}

export function ThreadScreen({ route }: AppScreenProps<'Thread'>) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const id = route.params.id;
  const query = useQuery({
    queryKey: ['thread', id],
    queryFn: async () => {
      const res = await messaging.messages(id);
      void messaging.markRead(id);
      return res;
    },
    refetchInterval: 5000,
  });
  const [text, setText] = useState('');
  const send = useMutation({
    mutationFn: () => messaging.send(id, text),
    onSuccess: () => {
      setText('');
      void queryClient.invalidateQueries({ queryKey: ['thread', id] });
    },
  });
  if (query.isPending) return <Loading />;
  if (query.isError) return <ErrorView error={query.error} onRetry={() => void query.refetch()} />;
  return (
    <View style={styles.flex}>
      <FlatList
        data={query.data.results}
        keyExtractor={(m) => String(m.id)}
        contentContainerStyle={styles.list}
        renderItem={({ item }) => (
          <View style={[styles.bubble, item.sender_id === user?.id ? styles.mine : styles.theirs]}>
            <Text style={item.sender_id === user?.id ? styles.mineText : undefined}>{item.body}</Text>
          </View>
        )}
      />
      <View style={styles.composer}>
        <TextInput value={text} onChangeText={setText} placeholder="Write a message" style={styles.input}
          accessibilityLabel="Message" multiline />
        <Button small title="Send" onPress={() => send.mutate()} disabled={!text.trim()} loading={send.isPending} />
      </View>
    </View>
  );
}

export function NotificationsScreen() {
  const navigation = useNavigation();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ['notifications'], queryFn: notifications.list, refetchInterval: POLL_INTERVAL_MS });
  const open = async (id: number, link: string) => {
    await notifications.read(id);
    void queryClient.invalidateQueries({ queryKey: ['notifications'] });
    const [kind, ref] = link.split('/');
    if (kind === 'orders') navigation.navigate('OrderDetail', { id: Number(ref) });
    else if (kind === 'messages') navigation.navigate('Messages');
    else if (kind === 'groups') navigation.navigate('GroupDetail', { id: Number(ref) });
    else if (kind === 'bulk') navigation.navigate('BulkDetail', { id: Number(ref) });
    else if (kind === 'transport') navigation.navigate('TransportDetail', { id: Number(ref) });
  };
  return (
    <QueryScreen query={query} isEmpty={(d) => d.results.length === 0} emptyTitle="No notifications"
      header={<Button small variant="secondary" title="Mark all read" onPress={async () => {
        await notifications.readAll();
        void queryClient.invalidateQueries({ queryKey: ['notifications'] });
      }} />}>
      {(data) => data.results.map((n) => (
        <Card key={n.id} onPress={() => void open(n.id, n.link)} accessibilityLabel={n.message}
          style={n.is_read ? undefined : styles.unread}>
          <Body>{n.message}</Body>
          <Body muted>{new Date(n.created_at).toLocaleString('en-ZA')}</Body>
        </Card>
      ))}
    </QueryScreen>
  );
}

const styles = StyleSheet.create({
  between: { justifyContent: 'space-between' },
  actions: { gap: spacing.sm },
  total: { fontWeight: '700', fontSize: 17, color: colors.primaryDark },
  name: { fontWeight: '700', color: colors.text },
  photos: { gap: spacing.sm },
  photo: { width: 220, height: 160, borderRadius: radius.md, backgroundColor: '#eee' },
  unread: { borderColor: colors.primary, borderWidth: 1 },
  flex: { flex: 1, backgroundColor: colors.background },
  list: { padding: spacing.md, gap: spacing.sm },
  bubble: { maxWidth: '85%', padding: spacing.md, borderRadius: radius.lg },
  mine: { alignSelf: 'flex-end', backgroundColor: colors.primary },
  mineText: { color: '#fff' },
  theirs: { alignSelf: 'flex-start', backgroundColor: '#fff' },
  composer: { flexDirection: 'row', gap: spacing.sm, padding: spacing.sm, backgroundColor: '#fff', alignItems: 'flex-end' },
  input: { flex: 1, minHeight: 44, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.md },
});
