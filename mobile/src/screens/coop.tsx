import { useNavigation } from '@react-navigation/native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import React, { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { bulk, equipment, groups, services, transport } from '../api';
import { parseApiError } from '../api/errors';
import { useAuth } from '../auth/AuthContext';
import { PROVINCES, STATUS_TONE } from '../constants';
import type { AppScreenProps } from '../navigation/types';
import { Badge, Body, Button, Card, Choice, distanceText, Field, FormError, money, Row, Screen, Subtitle, Title }
  from '../ui/components';
import { QueryScreen } from '../ui/QueryScreen';
import { colors, spacing } from '../ui/theme';

/** Run an API action, refresh the given query keys, and surface errors. */
function useAction(keys: unknown[][]) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: () => {
      setError(null);
      keys.forEach((queryKey) => void queryClient.invalidateQueries({ queryKey }));
    },
    onError: (e) => setError(parseApiError(e).message),
  });
  return { run: mutation.mutate, busy: mutation.isPending, error };
}

export function CoopHubScreen() {
  const navigation = useNavigation();
  const sections = [
    { title: 'Farmer groups', hint: 'Join local, produce or interest groups', to: 'Groups' as const },
    { title: 'Bulk buying', hint: 'Buy fertiliser, seed and feed together for better prices', to: 'BulkList' as const },
    { title: 'Shared transport', hint: 'Share a truck to market and split the cost', to: 'TransportList' as const },
    { title: 'Security', hint: 'Shared patrols and local alerts', to: 'Security' as const },
    { title: 'Insurance info', hint: 'Learn about cover and request quotes', to: 'Insurance' as const },
    { title: 'Equipment & storage', hint: 'Hire tractors, irrigation and cold storage', to: 'EquipmentList' as const },
  ];
  return (
    <Screen>
      {sections.map((s) => (
        <Card key={s.to} onPress={() => navigation.navigate(s.to)} accessibilityLabel={s.title}>
          <Text style={styles.title}>{s.title}</Text>
          <Body muted>{s.hint}</Body>
        </Card>
      ))}
    </Screen>
  );
}

// --- Groups ---------------------------------------------------------------------------

export function GroupsScreen({ navigation }: AppScreenProps<'Groups'>) {
  const [focus, setFocus] = useState('');
  const [search, setSearch] = useState<string | undefined>();
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<Record<string, string>>({ group_type: 'LOCATION' });
  const query = useQuery({ queryKey: ['groups', search], queryFn: () => groups.list({ focus: search }) });
  const { run, busy, error } = useAction([['groups']]);
  const set = (k: string) => (v: string) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <QueryScreen query={query} isEmpty={(d) => d.results.length === 0} emptyTitle="No groups found"
      emptyHint="Start one for farmers in your area."
      header={(
        <View style={styles.gap}>
          <Field label="Search by produce or interest" value={focus} onChangeText={setFocus}
            onSubmitEditing={() => setSearch(focus || undefined)} />
          <Row>
            <Button small title="Search" onPress={() => setSearch(focus || undefined)} />
            <Button small variant="secondary" title={creating ? 'Close' : 'Start a group'} onPress={() => setCreating((c) => !c)} />
          </Row>
          {creating ? (
            <Card>
              <FormError message={error} />
              <Field label="Group name" value={form.name ?? ''} onChangeText={set('name')} />
              <Choice label="Type" value={form.group_type} onChange={set('group_type')} options={[
                { value: 'LOCATION', label: 'Local' }, { value: 'PRODUCE', label: 'Produce' },
                { value: 'INTEREST', label: 'Interest' }, { value: 'PURCHASING', label: 'Purchasing' },
                { value: 'TRANSPORT', label: 'Transport' }]} />
              <Field label="Focus (e.g. poultry, security)" value={form.focus ?? ''} onChangeText={set('focus')} />
              <Choice label="Province" options={PROVINCES} value={form.province} onChange={set('province')} />
              <Field label="Municipality" value={form.municipality ?? ''} onChangeText={set('municipality')} />
              <Field label="Town" value={form.town ?? ''} onChangeText={set('town')} />
              <Button title="Create group" loading={busy} onPress={() => run(async () => {
                const g = await groups.create({ ...form, is_open: true });
                setCreating(false);
                navigation.navigate('GroupDetail', { id: g.id });
              })} />
            </Card>
          ) : null}
        </View>
      )}>
      {(data) => data.results.map((g) => (
        <Card key={g.id} onPress={() => navigation.navigate('GroupDetail', { id: g.id })} accessibilityLabel={g.name}>
          <Row style={styles.between}>
            <Text style={styles.title}>{g.name}</Text>
            {g.my_status ? <Badge text={g.my_status} tone={g.my_status === 'ACTIVE' ? 'good' : 'warn'} /> : null}
          </Row>
          <Body muted>{g.member_count} members · {g.town || g.municipality} · {distanceText(g.distance as never)}
            {g.is_open ? '' : ' · approval needed'}</Body>
        </Card>
      ))}
    </QueryScreen>
  );
}

export function GroupDetailScreen({ route }: AppScreenProps<'GroupDetail'>) {
  const id = route.params.id;
  const { user } = useAuth();
  const detail = useQuery({ queryKey: ['group', id], queryFn: () => groups.get(id) });
  const status = detail.data?.group.my_status;
  const posts = useQuery({ queryKey: ['group-posts', id], queryFn: () => groups.posts(id), enabled: status === 'ACTIVE' });
  const { run, busy, error } = useAction([['group', id], ['group-posts', id], ['groups']]);
  const [post, setPost] = useState('');
  const me = detail.data?.members.find((m) => m.farmer_id === user?.id);
  const isAdmin = me?.role === 'ADMIN' && me.status === 'ACTIVE';

  return (
    <QueryScreen query={detail}>
      {({ group, members }) => (
        <>
          <Title>{group.name}</Title>
          <Body muted>{group.town || group.municipality} · {group.member_count} members{group.focus ? ` · ${group.focus}` : ''}</Body>
          {group.description ? <Body>{group.description}</Body> : null}
          <FormError message={error} />
          {status === 'INVITED' ? (
            <Row>
              <Button small title="Accept invitation" onPress={() => run(() => groups.respondInvite(id, true))} />
              <Button small variant="secondary" title="Decline" onPress={() => run(() => groups.respondInvite(id, false))} />
            </Row>
          ) : status === 'ACTIVE' ? (
            <Button small variant="secondary" title="Leave group" onPress={() => run(() => groups.leave(id))} />
          ) : status === 'REQUESTED' ? <Badge text="Waiting for an admin to approve you" tone="warn" /> : (
            <Button title={group.is_open ? 'Join group' : 'Ask to join'} loading={busy} onPress={() => run(() => groups.join(id))} />
          )}
          <Subtitle>Members</Subtitle>
          {members.map((m) => (
            <Row key={m.farmer_id} style={styles.between}>
              <Body>{m.display_name}{m.role === 'ADMIN' ? ' (admin)' : ''}</Body>
              {isAdmin && m.status === 'REQUESTED' ? (
                <Row>
                  <Button small title="Approve" onPress={() => run(() => groups.decide(id, m.farmer_id, true))} />
                  <Button small variant="secondary" title="Decline" onPress={() => run(() => groups.decide(id, m.farmer_id, false))} />
                </Row>
              ) : m.status !== 'ACTIVE' ? <Badge text={m.status} tone="warn" /> : null}
            </Row>
          ))}
          {status === 'ACTIVE' ? (
            <>
              <Subtitle>Posts</Subtitle>
              <Field label="Write a post" value={post} onChangeText={setPost} multiline />
              <Row>
                <Button small title="Post" disabled={!post.trim()} onPress={() => run(async () => {
                  await groups.addPost(id, post);
                  setPost('');
                })} />
                {isAdmin ? <Button small variant="secondary" title="Post as announcement" disabled={!post.trim()}
                  onPress={() => run(async () => { await groups.addPost(id, post, true); setPost(''); })} /> : null}
              </Row>
              {posts.data?.results.map((p) => (
                <Card key={p.id} style={p.is_announcement ? styles.announcement : undefined}>
                  {p.is_announcement ? <Badge text="Announcement" tone="warn" /> : null}
                  <Body>{p.body}</Body>
                  <Body muted>{p.author_display_name} · {new Date(p.created_at).toLocaleDateString('en-ZA')}</Body>
                </Card>
              ))}
            </>
          ) : null}
        </>
      )}
    </QueryScreen>
  );
}

// --- Bulk purchasing ----------------------------------------------------------------------

type Breakdown = {
  total_quantity: string; unit_price: string; total: string; savings: string; shared_fees: string;
  applied_tier: { min_total_quantity: string; unit_price: string } | null;
  shares: { farmer_id: number; label: string; quantity: string; share_amount: string; confirmed: boolean }[];
};

export function BulkListScreen({ navigation }: AppScreenProps<'BulkList'>) {
  const query = useQuery({ queryKey: ['bulk'], queryFn: () => bulk.list({ status: 'OPEN' }) });
  return (
    <QueryScreen query={query} isEmpty={(d) => d.results.length === 0} emptyTitle="No open bulk purchases">
      {(data) => data.results.map((b) => {
        const br = b.breakdown as unknown as Breakdown;
        return (
          <Card key={b.id} onPress={() => navigation.navigate('BulkDetail', { id: b.id })} accessibilityLabel={b.item_name}>
            <Text style={styles.title}>{b.item_name}</Text>
            <Body>{money(br.unit_price)}/{b.unit} now · {br.total_quantity} {b.unit} committed · closes {b.deadline}</Body>
            <Body muted>Organised by {b.organiser}</Body>
          </Card>
        );
      })}
    </QueryScreen>
  );
}

export function BulkDetailScreen({ route }: AppScreenProps<'BulkDetail'>) {
  const id = route.params.id;
  const { user } = useAuth();
  const query = useQuery({ queryKey: ['bulk', id], queryFn: () => bulk.get(id) });
  const { run, busy, error } = useAction([['bulk', id], ['bulk']]);
  const [quantity, setQuantity] = useState('');

  return (
    <QueryScreen query={query}>
      {(b) => {
        const br = b.breakdown as unknown as Breakdown;
        const mine = br.shares.find((s) => s.farmer_id === user?.id);
        const isOrganiser = b.organiser === user?.display_name;
        return (
          <>
            <Title>{b.item_name}</Title>
            <Badge text={b.status ?? 'OPEN'} tone={STATUS_TONE[b.status ?? 'OPEN']} />
            <Body>Base price {money(b.unit_price)}/{b.unit}. Closes {b.deadline}.</Body>
            {(b.discount_tiers ?? []).map((t) => (
              <Body key={t.min_total_quantity} muted>{t.min_total_quantity}+ {b.unit}: {money(t.unit_price)}/{b.unit}</Body>
            ))}
            {b.supplier_name ? <Body muted>Supplier: {b.supplier_name}</Body> : null}
            <FormError message={error} />
            <Card>
              <Text style={styles.title}>Contribution breakdown</Text>
              <Body>{br.total_quantity} {b.unit} × {money(br.unit_price)}{Number(br.shared_fees) ? ` + fees ${money(br.shared_fees)}` : ''} = {money(br.total)}</Body>
              {Number(br.savings) > 0 ? <Badge text={`Group saves ${money(br.savings)}`} tone="good" /> : null}
              {br.shares.map((s) => (
                <Row key={s.farmer_id} style={styles.between}>
                  <Body>{s.farmer_id === user?.id ? 'You' : s.label} · {s.quantity} {b.unit}</Body>
                  <Body>{money(s.share_amount)} {s.confirmed ? '✓' : '…'}</Body>
                </Row>
              ))}
            </Card>
            {b.status === 'OPEN' ? (
              <>
                <Field label={mine ? `Change your quantity (${b.unit})` : `How many ${b.unit}?`} value={quantity}
                  onChangeText={setQuantity} keyboardType="decimal-pad" />
                <Button title={mine ? 'Update quantity' : 'Join'} variant={mine ? 'secondary' : 'primary'} loading={busy}
                  disabled={!(Number(quantity) > 0)} onPress={() => run(async () => { await bulk.join(id, quantity); setQuantity(''); })} />
                <Body muted>Joining doesn't commit you. Your share changes as others join.</Body>
                {mine && !mine.confirmed ? (
                  <Button title={`Confirm my contribution of ${money(mine.share_amount)}`} loading={busy}
                    onPress={() => run(() => bulk.confirm(id))} />
                ) : null}
                {mine ? <Button small variant="secondary" title="Leave" onPress={() => run(() => bulk.leave(id))} /> : null}
                {isOrganiser ? (
                  <Button variant="secondary" title="Lock purchase (everyone confirmed)" onPress={() => run(() => bulk.setStatus(id, 'LOCKED'))} />
                ) : null}
              </>
            ) : null}
            <Body muted>Payments are made to the organiser outside the app.</Body>
          </>
        );
      }}
    </QueryScreen>
  );
}

// --- Transport ------------------------------------------------------------------------------

export function TransportListScreen({ navigation }: AppScreenProps<'TransportList'>) {
  const query = useQuery({ queryKey: ['transport'], queryFn: () => transport.list({ status: 'OPEN' }) });
  return (
    <QueryScreen query={query} isEmpty={(d) => d.results.length === 0} emptyTitle="No shared trips open">
      {(data) => data.results.map((t) => (
        <Card key={t.id} onPress={() => navigation.navigate('TransportDetail', { id: t.id })} accessibilityLabel={t.destination}>
          <Text style={styles.title}>{t.pickup_town} → {t.destination}</Text>
          <Body>{t.travel_date} · {t.participants.length} farmer(s) · {t.total_cost ? money(t.total_cost) : 'cost not quoted yet'}</Body>
          <Body muted>Split: {t.cost_split_method?.toLowerCase()} · {t.vehicle_description}</Body>
        </Card>
      ))}
    </QueryScreen>
  );
}

export function TransportDetailScreen({ route }: AppScreenProps<'TransportDetail'>) {
  const id = route.params.id;
  const { user } = useAuth();
  const query = useQuery({ queryKey: ['transport', id], queryFn: () => transport.get(id) });
  const { run, busy, error } = useAction([['transport', id], ['transport']]);
  const [load, setLoad] = useState<Record<string, string>>({});
  const set = (k: string) => (v: string) => setLoad((l) => ({ ...l, [k]: v }));

  return (
    <QueryScreen query={query}>
      {(t) => {
        const mine = t.participants.find((p) => p.farmer_id === user?.id);
        const field = { WEIGHT: ['load_weight_kg', 'Load (kg)'], VOLUME: ['load_volume_m3', 'Load (m³)'],
          SPACE: ['load_space_units', 'Space (crates/pallets)'], AGREED: ['agreed_amount', 'Amount you agreed to pay (R)'] }[
          t.cost_split_method as string] ?? ['load_weight_kg', 'Load (kg)'];
        return (
          <>
            <Title>{t.pickup_town} → {t.destination}</Title>
            <Badge text={t.status ?? 'OPEN'} tone={STATUS_TONE[t.status ?? 'OPEN']} />
            <Body>{t.travel_date} · {t.vehicle_description}</Body>
            <Body>Total: {t.total_cost ? money(t.total_cost) : 'not quoted yet'} · split {t.cost_split_method?.toLowerCase()}</Body>
            {t.split_problem ? <Badge text={t.split_problem} tone="warn" /> : null}
            <FormError message={error} />
            <Card>
              {t.participants.map((p) => (
                <Row key={p.farmer_id} style={styles.between}>
                  <Body>{p.farmer_id === user?.id ? 'You' : p.display_name}{p.load_weight_kg ? ` · ${p.load_weight_kg} kg` : ''}</Body>
                  <Body>{p.calculated_share ? money(p.calculated_share) : '—'} {p.confirmed ? '✓' : ''}</Body>
                </Row>
              ))}
            </Card>
            {t.status === 'OPEN' || t.status === 'FULL' ? (
              <>
                {t.status === 'OPEN' ? (
                  <>
                    <Field label={field[1]} value={load[field[0]] ?? ''} onChangeText={set(field[0])} keyboardType="decimal-pad" />
                    <Field label="Your pickup town (optional)" value={load.pickup_town ?? ''} onChangeText={set('pickup_town')} />
                    <Button title={mine ? 'Update my load' : 'Join this trip'} loading={busy}
                      onPress={() => run(() => transport.join(id, load))} />
                  </>
                ) : null}
                {mine && !mine.confirmed && mine.calculated_share ? (
                  <Button title={`Confirm my share of ${money(mine.calculated_share)}`} onPress={() => run(() => transport.confirm(id))} />
                ) : null}
                {mine ? <Button small variant="secondary" title="Leave trip" onPress={() => run(() => transport.leave(id))} /> : null}
              </>
            ) : null}
            <Body muted>Costs are paid to the organiser outside the app.</Body>
          </>
        );
      }}
    </QueryScreen>
  );
}

// --- Security & insurance --------------------------------------------------------------------

export function SecurityScreen() {
  const { user } = useAuth();
  const shared = useQuery({ queryKey: ['security'], queryFn: services.security });
  const alerts = useQuery({ queryKey: ['alerts'], queryFn: services.alerts });
  const { run, busy, error } = useAction([['security'], ['alerts']]);
  const [alert, setAlert] = useState<Record<string, string>>({ alert_type: 'SUSPICIOUS_ACTIVITY' });
  const set = (k: string) => (v: string) => setAlert((a) => ({ ...a, [k]: v }));

  return (
    <QueryScreen query={shared}>
      {(data) => (
        <>
          <Subtitle>Shared security</Subtitle>
          <FormError message={error} />
          {data.results.length === 0 ? <Body muted>No shared security arrangements yet.</Body> : data.results.map((s) => {
            const mine = s.contributions.find((c) => c.farmer_id === user?.id);
            return (
              <Card key={s.id}>
                <Text style={styles.title}>{s.title}</Text>
                <Body>{s.town || s.municipality} · {s.total_monthly_cost ? `${money(s.total_monthly_cost)}/month` : 'cost to be agreed'}
                  {' · '}{s.contributions.length} farmer(s)</Body>
                {s.split_problem ? <Badge text={s.split_problem} tone="warn" /> : null}
                {mine ? (
                  mine.confirmed ? <Badge text={`You confirmed ${money(mine.amount)}/month`} tone="good" />
                    : mine.amount ? <Button small title={`Confirm ${money(mine.amount)}/month`}
                      onPress={() => run(() => services.confirmSecurity(s.id))} /> : null
                ) : <Button small variant="secondary" title="Join" onPress={() => run(() => services.joinSecurity(s.id))} />}
              </Card>
            );
          })}
          <Subtitle>Local alerts</Subtitle>
          <Card>
            <Body muted>Share what happened, where and when. Never post names, ID numbers or phone numbers. Report crimes to SAPS (10111).</Body>
            <Choice label="Type" value={alert.alert_type} onChange={set('alert_type')} options={[
              { value: 'THEFT', label: 'Theft' }, { value: 'SUSPICIOUS_ACTIVITY', label: 'Suspicious' },
              { value: 'LIVESTOCK', label: 'Livestock' }, { value: 'FIRE', label: 'Fire' }, { value: 'OTHER', label: 'Other' }]} />
            <Field label="Title" value={alert.title ?? ''} onChangeText={set('title')} />
            <Field label="What happened" value={alert.body ?? ''} onChangeText={set('body')} multiline />
            <Choice label="Province" options={PROVINCES} value={alert.province} onChange={set('province')} />
            <Field label="Municipality" value={alert.municipality ?? ''} onChangeText={set('municipality')} />
            <Button small title="Post alert" loading={busy} onPress={() => run(async () => {
              await services.postAlert(alert);
              setAlert({ alert_type: 'SUSPICIOUS_ACTIVITY' });
            })} />
          </Card>
          {alerts.data?.results.map((a) => (
            <Card key={a.id}>
              <Badge text={a.alert_type} tone="warn" />
              <Text style={styles.title}>{a.title}</Text>
              <Body>{a.body}</Body>
              <Body muted>{a.town || a.municipality} · {new Date(a.created_at).toLocaleDateString('en-ZA')}</Body>
            </Card>
          ))}
        </>
      )}
    </QueryScreen>
  );
}

export function InsuranceScreen() {
  const products = useQuery({ queryKey: ['insurance'], queryFn: services.insuranceProducts });
  const mine = useQuery({ queryKey: ['quotes'], queryFn: services.quoteRequests });
  const { run, busy, error } = useAction([['quotes']]);
  const [category, setCategory] = useState('CROP');
  const [details, setDetails] = useState('');

  return (
    <QueryScreen query={products}>
      {(data) => (
        <>
          <Card style={styles.disclaimer}>
            <Text style={styles.title}>Important</Text>
            <Body>{data.disclaimer}</Body>
          </Card>
          {data.results.map((p) => (
            <Card key={p.id}>
              <Text style={styles.title}>{p.name}</Text>
              <Body muted>{p.provider_name} · {p.category?.toLowerCase()}{p.is_authorised_provider ? ' · FSCA authorised (checked by admin)' : ''}</Body>
              <Body>{p.summary}</Body>
            </Card>
          ))}
          <Subtitle>Ask for a quote</Subtitle>
          <FormError message={error} />
          <Choice label="Type of cover" value={category} onChange={setCategory} options={[
            { value: 'CROP', label: 'Crop' }, { value: 'LIVESTOCK', label: 'Livestock' },
            { value: 'EQUIPMENT', label: 'Equipment' }, { value: 'PROPERTY', label: 'Property' }]} />
          <Field label="Details (what you farm, size, value)" value={details} onChangeText={setDetails} multiline />
          <Button title="Request quote" loading={busy} disabled={!details.trim()} onPress={() => run(async () => {
            await services.requestQuote({ category, details });
            setDetails('');
          })} />
          <Subtitle>Your quote requests</Subtitle>
          {mine.data?.results.length ? mine.data.results.map((q) => (
            <Card key={q.id}>
              <Body>{q.category} · {q.status}</Body>
              {q.quote_note ? <Body muted>{q.quote_note}{q.quote_amount ? ` · ${money(q.quote_amount)}` : ''}</Body> : null}
            </Card>
          )) : <Body muted>None yet.</Body>}
        </>
      )}
    </QueryScreen>
  );
}

// --- Equipment --------------------------------------------------------------------------------

export function EquipmentListScreen({ navigation }: AppScreenProps<'EquipmentList'>) {
  const query = useQuery({ queryKey: ['equipment'], queryFn: () => equipment.list() });
  return (
    <QueryScreen query={query} isEmpty={(d) => d.results.length === 0} emptyTitle="No equipment listed nearby">
      {(data) => data.results.map((e) => (
        <Card key={e.id} onPress={() => navigation.navigate('EquipmentDetail', { id: e.id })} accessibilityLabel={e.name}>
          <Text style={styles.title}>{e.name}</Text>
          <Body>{money(e.rate)} {e.rate_unit?.replace(/_/g, ' ').toLowerCase()}{e.capacity ? ` · ${e.capacity} t capacity` : ''}</Body>
          <Body muted>{e.owner} · {distanceText((e.location as { distance?: never } | null)?.distance)}</Body>
        </Card>
      ))}
    </QueryScreen>
  );
}

export function EquipmentDetailScreen({ route }: AppScreenProps<'EquipmentDetail'>) {
  const id = route.params.id;
  const { user } = useAuth();
  const query = useQuery({ queryKey: ['equipment', id], queryFn: () => equipment.get(id) });
  const { run, busy, error } = useAction([['equipment', id]]);
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [tonnes, setTonnes] = useState('');
  const [done, setDone] = useState<string | null>(null);

  return (
    <QueryScreen query={query}>
      {(e) => {
        const storage = e.type === 'COLD_STORAGE' || e.type === 'WAREHOUSE';
        return (
          <>
            <Title>{e.name}</Title>
            <Body>{money(e.rate)} {e.rate_unit?.replace(/_/g, ' ').toLowerCase()}{e.capacity ? ` · ${e.capacity} tonnes` : ''}</Body>
            {e.description ? <Body>{e.description}</Body> : null}
            <Body muted>{e.owner} · {distanceText((e.location as { distance?: never } | null)?.distance)}</Body>
            {e.owner !== user?.display_name ? (
              <Card>
                <FormError message={error} />
                <Field label="From (YYYY-MM-DD)" value={start} onChangeText={setStart} />
                <Field label="To (YYYY-MM-DD)" value={end} onChangeText={setEnd} />
                {storage ? <Field label="Tonnes of space" value={tonnes} onChangeText={setTonnes} keyboardType="decimal-pad" /> : null}
                <Button title="Request booking" loading={busy} onPress={() => run(async () => {
                  const b = await equipment.book(id, {
                    start: `${start}T07:00:00+02:00`, end: `${end}T17:00:00+02:00`, quantity: storage ? tonnes : undefined,
                  });
                  setDone(`Requested. Estimated cost ${money(b.estimated_cost)}. The owner must approve.`);
                })} />
                {done ? <Text style={styles.ok}>{done}</Text> : null}
              </Card>
            ) : <Body muted>This is your equipment.</Body>}
          </>
        );
      }}
    </QueryScreen>
  );
}

const styles = StyleSheet.create({
  title: { fontWeight: '700', fontSize: 16, color: colors.text },
  between: { justifyContent: 'space-between' },
  gap: { gap: spacing.sm },
  announcement: { borderColor: colors.accent, borderWidth: 1 },
  disclaimer: { borderColor: colors.accent, borderWidth: 2, backgroundColor: colors.warningLight },
  ok: { color: colors.primaryDark, fontWeight: '600' },
});
