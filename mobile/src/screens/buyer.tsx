import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { useNavigation } from '@react-navigation/native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import React, { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { buyers, listings as listingsApi, marketplace, orders } from '../api';
import { parseApiError } from '../api/errors';
import type { QualityGrade, Unit } from '../api/types';
import { FarmerMatchCard, ListingCard, OrderRow } from '../components/cards';
import { label, PROVINCES, QUALITY, STATUS_TONE, UNITS } from '../constants';
import type { AppScreenProps, BuyerTabParams } from '../navigation/types';
import { Badge, Body, Button, Card, Choice, Empty, ErrorView, Field, FormError, Loading, money, qty, Row, Screen,
  Subtitle, Title, distanceText } from '../ui/components';
import { QueryScreen } from '../ui/QueryScreen';
import { colors, spacing } from '../ui/theme';

export function BuyerDashboard() {
  const navigation = useNavigation();
  const recs = useQuery({ queryKey: ['recommended-farmers'], queryFn: buyers.recommendedFarmers });
  const reqs = useQuery({ queryKey: ['requirements', 'OPEN'], queryFn: () => buyers.requirements('OPEN') });
  const active = useQuery({ queryKey: ['orders', 'active'], queryFn: () => orders.list('PENDING,ACCEPTED,DISPATCHED,DELIVERED') });

  return (
    <Screen refreshing={recs.isRefetching} onRefresh={() => { void recs.refetch(); void reqs.refetch(); void active.refetch(); }}>
      <Row>
        <Button small title="Notifications" variant="secondary" onPress={() => navigation.navigate('Notifications')} />
        <Button small title="Messages" variant="secondary" onPress={() => navigation.navigate('Messages')} />
      </Row>
      <Subtitle>Recommended farmers</Subtitle>
      {recs.isPending ? <Loading /> : recs.isError ? <ErrorView error={recs.error} onRetry={() => void recs.refetch()} />
        : recs.data.items.length === 0 ? (
          <Empty title="No recommendations yet" hint={recs.data.message ?? 'Post a requirement to get matched.'} />
        ) : recs.data.items.map((item) => (
          <View key={`${item.produce}-${item.requirement_id}`} style={styles.group}>
            <Text style={styles.groupTitle}>{qty(item.quantity, item.unit)} {item.produce}</Text>
            {item.results.length === 0
              ? <Body muted>{item.message ?? 'No farmers match yet.'}</Body>
              : item.results.slice(0, 3).map((m) => <FarmerMatchCard key={m.listing_id} match={m} />)}
          </View>
        ))}

      <Subtitle>My open requirements</Subtitle>
      {reqs.data?.results.length ? reqs.data.results.map((r) => (
        <Card key={r.id} onPress={() => navigation.navigate('RequirementForm', { id: r.id })} accessibilityLabel={r.produce_name}>
          <Body>{qty(r.quantity_needed, r.unit)} {r.produce_name} by {r.needed_by}</Body>
        </Card>
      )) : <Empty title="No open requirements" />}

      <Subtitle>Active orders</Subtitle>
      {active.data?.results.length ? active.data.results.map((o) => (
        <OrderRow key={o.id} order={o} onPress={() => navigation.navigate('OrderDetail', { id: o.id })} />
      )) : <Empty title="No active orders" />}
    </Screen>
  );
}

const SORTS = [
  { value: 'newest', label: 'Newest' }, { value: 'price', label: 'Cheapest' },
  { value: 'distance', label: 'Nearest' }, { value: '-quantity', label: 'Most stock' },
];

export function MarketplaceScreen({ navigation }: BottomTabScreenProps<BuyerTabParams, 'Marketplace'>) {
  const [q, setQ] = useState('');
  const [submitted, setSubmitted] = useState<Record<string, string | undefined>>({ sort: 'newest' });
  const [filters, setFilters] = useState<Record<string, string | undefined>>({ sort: 'newest' });
  const [showFilters, setShowFilters] = useState(false);
  const [compare, setCompare] = useState<number[]>([]);
  const categories = useQuery({ queryKey: ['categories'], queryFn: listingsApi.categories });
  const results = useQuery({ queryKey: ['marketplace', submitted], queryFn: () => marketplace.search(submitted) });

  const set = (k: string) => (v: string) => setFilters((f) => ({ ...f, [k]: v || undefined }));
  const apply = () => setSubmitted({ ...filters, q: q || undefined });
  const toggle = (id: number) => setCompare((c) => c.includes(id) ? c.filter((x) => x !== id) : c.length < 3 ? [...c, id] : c);

  return (
    <QueryScreen
      query={results}
      isEmpty={(d) => d.results.length === 0}
      emptyTitle="No listings match"
      emptyHint="Try fewer filters or a different produce name."
      header={(
        <View style={styles.group}>
          <Field label="Search produce" value={q} onChangeText={setQ} placeholder="e.g. tomatoes" returnKeyType="search"
            onSubmitEditing={apply} />
          <Row>
            <Button small title="Search" onPress={apply} />
            <Button small variant="secondary" title={showFilters ? 'Hide filters' : 'Filters'}
              onPress={() => setShowFilters((s) => !s)} />
            {compare.length >= 2 ? (
              <Button small variant="secondary" title={`Compare (${compare.length})`}
                onPress={() => navigation.navigate('Compare', { ids: compare })} />
            ) : null}
          </Row>
          {showFilters ? (
            <Card>
              <Choice label="Sort" options={SORTS} value={filters.sort} onChange={set('sort')} />
              <Choice label="Category" options={(categories.data ?? []).map((c) => ({ value: c.slug, label: c.name }))}
                value={filters.category} onChange={set('category')} />
              <Row>
                <View style={styles.half}><Field label="Min price (R)" value={filters.min_price ?? ''}
                  onChangeText={set('min_price')} keyboardType="decimal-pad" /></View>
                <View style={styles.half}><Field label="Max price (R)" value={filters.max_price ?? ''}
                  onChangeText={set('max_price')} keyboardType="decimal-pad" /></View>
              </Row>
              <Row>
                <View style={styles.half}><Field label="Min quantity" value={filters.min_quantity ?? ''}
                  onChangeText={set('min_quantity')} keyboardType="decimal-pad" /></View>
                <View style={styles.half}><Field label="Within km" value={filters.max_distance_km ?? ''}
                  onChangeText={set('max_distance_km')} keyboardType="number-pad" /></View>
              </Row>
              <Choice<Unit> label="Unit (for min quantity)" options={UNITS} value={filters.unit as Unit}
                onChange={set('unit')} />
              <Choice<QualityGrade> label="Minimum quality" options={QUALITY} value={filters.quality_grade as QualityGrade}
                onChange={set('quality_grade')} />
              <Choice label="Province" options={PROVINCES} value={filters.province} onChange={set('province')} />
              <Field label="Town" value={filters.town ?? ''} onChangeText={set('town')} />
              <Row>
                <Button small title="Apply" onPress={apply} />
                <Button small variant="secondary" title="Clear" onPress={() => { setFilters({ sort: 'newest' });
                  setSubmitted({ sort: 'newest' }); setQ(''); }} />
              </Row>
            </Card>
          ) : null}
        </View>
      )}
    >
      {(data) => (
        <>
          <Body muted>{data.count} listing(s). Tap ☐ to compare up to 3.</Body>
          {data.results.map((l) => (
            <ListingCard key={l.id} listing={l} onPress={() => navigation.navigate('ListingDetail', { id: l.id })}
              right={(
                <Text onPress={() => toggle(l.id)} style={styles.check} accessibilityRole="checkbox"
                  accessibilityState={{ checked: compare.includes(l.id) }} accessibilityLabel="Compare">
                  {compare.includes(l.id) ? '☑' : '☐'} {money(l.price_per_unit)}
                </Text>
              )} />
          ))}
        </>
      )}
    </QueryScreen>
  );
}

export function CompareScreen({ route, navigation }: AppScreenProps<'Compare'>) {
  const query = useQuery({ queryKey: ['compare', route.params.ids], queryFn: () => marketplace.compare(route.params.ids) });
  return (
    <QueryScreen query={query}>
      {(data) => (
        <>
          {data.unavailable_listing_ids?.length ? <Body muted>Some listings are no longer available.</Body> : null}
          {data.results.map((l) => (
            <Card key={l.id} onPress={() => navigation.navigate('ListingDetail', { id: l.id })} accessibilityLabel={l.produce_name}>
              <Row style={styles.between}>
                <Text style={styles.groupTitle}>{l.farmer.display_name}</Text>
                <Row>
                  {l.id === data.cheapest_listing_id ? <Badge text="Cheapest" tone="good" /> : null}
                  {l.id === data.nearest_listing_id ? <Badge text="Nearest" tone="good" /> : null}
                </Row>
              </Row>
              <Body>{l.produce_name} · {money(l.price_per_unit)}/{l.unit.toLowerCase()}</Body>
              <Body muted>{qty(l.quantity_available, l.unit)} · {label(QUALITY, l.quality_grade)} · {distanceText(l.location?.distance)}</Body>
              <Body muted>
                {l.available_now ? 'Available now' : `From ${l.available_from}`} ·{' '}
                {l.reliability.completion_rate != null
                  ? `Completed ${l.reliability.completed_orders}/${l.reliability.finished_orders} orders`
                  : l.reliability.note}
              </Body>
            </Card>
          ))}
        </>
      )}
    </QueryScreen>
  );
}

export function PlaceOrderScreen({ route, navigation }: AppScreenProps<'PlaceOrder'>) {
  const listing = useQuery({ queryKey: ['public-listing', route.params.listingId],
    queryFn: () => marketplace.listing(route.params.listingId) });
  const queryClient = useQueryClient();
  const [quantity, setQuantity] = useState('');
  const [date, setDate] = useState('');
  const [notes, setNotes] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const place = useMutation({
    mutationFn: () => orders.create({ items: [{ listing_id: route.params.listingId, quantity }],
      delivery_date: date || undefined, delivery_notes: notes }),
    onSuccess: (order) => {
      void queryClient.invalidateQueries({ queryKey: ['orders'] });
      navigation.replace('OrderDetail', { id: order.id });
    },
    onError: (e) => {
      const err = parseApiError(e);
      setErrors(err.fieldErrors);
      setFormError(err.message);
    },
  });

  if (listing.isPending) return <Loading />;
  if (listing.isError) return <ErrorView error={listing.error} />;
  const l = listing.data;
  const total = Number(quantity) > 0 ? Number(quantity) * Number(l.price_per_unit) : 0;

  return (
    <Screen>
      <Title>{l.produce_name} from {l.farmer.display_name}</Title>
      <Body muted>{qty(l.quantity_available, l.unit)} available at {money(l.price_per_unit)}/{l.unit.toLowerCase()}</Body>
      <FormError message={formError} />
      <Field label={`Quantity (${l.unit.toLowerCase()})`} value={quantity} onChangeText={setQuantity}
        keyboardType="decimal-pad" error={errors.items ?? errors.quantity} />
      <Field label="Delivery date (YYYY-MM-DD, optional)" value={date} onChangeText={setDate} error={errors.delivery_date} />
      <Field label="Delivery notes (optional)" value={notes} onChangeText={setNotes} multiline />
      <Body>Estimated total: {money(total)}</Body>
      <Body muted>The farmer must accept your order. Payment is arranged directly with the farmer, outside the app.</Body>
      <Button title="Place order" onPress={() => {
        if (!(Number(quantity) > 0)) { setErrors({ quantity: 'Enter a quantity' }); return; }
        place.mutate();
      }} loading={place.isPending} />
    </Screen>
  );
}

export function RequirementsScreen({ navigation }: BottomTabScreenProps<BuyerTabParams, 'Requirements'>) {
  const query = useQuery({ queryKey: ['requirements'], queryFn: () => buyers.requirements() });
  return (
    <QueryScreen query={query} isEmpty={(d) => d.results.length === 0} emptyTitle="No requirements yet"
      emptyHint="Tell farmers what you need and we'll recommend the best matches."
      header={<Button title="+ New requirement" onPress={() => navigation.navigate('RequirementForm')} />}>
      {(data) => data.results.map((r) => (
        <Card key={r.id} onPress={() => navigation.navigate('RequirementForm', { id: r.id })} accessibilityLabel={r.produce_name}>
          <Row style={styles.between}>
            <Text style={styles.groupTitle}>{r.produce_name}</Text>
            <Badge text={r.status ?? 'OPEN'} tone={STATUS_TONE[r.status ?? 'OPEN']} />
          </Row>
          <Body>{qty(r.quantity_needed, r.unit)} by {r.needed_by}{r.max_price_per_unit ? ` · max ${money(r.max_price_per_unit)}` : ''}</Body>
        </Card>
      ))}
    </QueryScreen>
  );
}

export function RequirementFormScreen({ route, navigation }: AppScreenProps<'RequirementForm'>) {
  const id = route.params?.id;
  const queryClient = useQueryClient();
  const existing = useQuery({ queryKey: ['requirement', id], queryFn: () => buyers.requirement(id!), enabled: !!id });
  const [form, setForm] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const r = existing.data;
  const value = (k: string, fallback = '') => form[k] ?? (r ? String((r as Record<string, unknown>)[k] ?? '') : fallback);
  const set = (k: string) => (v: string) => setForm((f) => ({ ...f, [k]: v }));

  async function save() {
    setSaving(true);
    setErrors({});
    setFormError(null);
    const body = {
      produce_name: value('produce_name'), quantity_needed: value('quantity_needed'), unit: value('unit', 'KG'),
      needed_by: value('needed_by'), max_price_per_unit: value('max_price_per_unit') || null,
      max_distance_km: value('max_distance_km') ? Number(value('max_distance_km')) : null,
      min_quality_grade: value('min_quality_grade'), notes: value('notes'),
    };
    try {
      if (id) await buyers.updateRequirement(id, body);
      else await buyers.createRequirement(body);
      void queryClient.invalidateQueries({ queryKey: ['requirements'] });
      void queryClient.invalidateQueries({ queryKey: ['recommended-farmers'] });
      navigation.goBack();
    } catch (e) {
      const err = parseApiError(e);
      setErrors(err.fieldErrors);
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  }

  if (id && existing.isPending) return <Loading />;
  return (
    <Screen>
      <Title>{id ? 'Edit requirement' : 'What do you need?'}</Title>
      <FormError message={formError} />
      <Field label="Produce" value={value('produce_name')} onChangeText={set('produce_name')} error={errors.produce_name} />
      <Field label="Quantity" value={value('quantity_needed')} onChangeText={set('quantity_needed')}
        keyboardType="decimal-pad" error={errors.quantity_needed} />
      <Choice<Unit> label="Unit" options={UNITS} value={value('unit', 'KG') as Unit} onChange={set('unit')} />
      <Field label="Needed by (YYYY-MM-DD)" value={value('needed_by')} onChangeText={set('needed_by')} error={errors.needed_by} />
      <Field label="Max price per unit (R, optional)" value={value('max_price_per_unit')}
        onChangeText={set('max_price_per_unit')} keyboardType="decimal-pad" error={errors.max_price_per_unit} />
      <Field label="Max distance km (optional)" value={value('max_distance_km')} onChangeText={set('max_distance_km')}
        keyboardType="number-pad" />
      <Choice<QualityGrade> label="Minimum quality (optional)" options={QUALITY}
        value={value('min_quality_grade') as QualityGrade} onChange={set('min_quality_grade')} />
      <Field label="Notes" value={value('notes')} onChangeText={set('notes')} multiline />
      <Button title="Save" onPress={() => void save()} loading={saving} />
      {id ? (
        <Button title="Close requirement" variant="danger" onPress={async () => {
          await buyers.closeRequirement(id);
          void queryClient.invalidateQueries({ queryKey: ['requirements'] });
          navigation.goBack();
        }} />
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  group: { gap: spacing.sm },
  groupTitle: { fontWeight: '700', fontSize: 16, color: colors.text },
  half: { flex: 1, minWidth: 130 },
  between: { justifyContent: 'space-between' },
  check: { fontWeight: '700', color: colors.primaryDark, padding: 4 },
});
