import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { useNavigation } from '@react-navigation/native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import * as ImagePicker from 'expo-image-picker';
import React, { useState } from 'react';
import { Alert, Image, ScrollView, StyleSheet, View } from 'react-native';

import { farmers, groups, listings, orders } from '../api';
import { parseApiError } from '../api/errors';
import type { MyListing } from '../api/types';
import { emptyListing, ListingForm, ListingValues } from '../components/ListingForm';
import { BuyerMatchCard, OrderRow } from '../components/cards';
import { label, QUALITY, STATUS_TONE } from '../constants';
import type { AppScreenProps, FarmerTabParams } from '../navigation/types';
import { Badge, Body, Button, Card, Empty, ErrorView, FormError, Loading, money, qty, Row, Screen, Subtitle, Title }
  from '../ui/components';
import { QueryScreen } from '../ui/QueryScreen';
import { spacing } from '../ui/theme';

export function FarmerDashboard() {
  const navigation = useNavigation();
  const recs = useQuery({ queryKey: ['recommended-buyers'], queryFn: farmers.recommendedBuyers });
  const open = useQuery({ queryKey: ['orders', 'open'], queryFn: () => orders.list('PENDING,ACCEPTED,DISPATCHED') });
  const myGroups = useQuery({ queryKey: ['groups', 'mine'], queryFn: () => groups.list({ mine: 'true' }) });
  const refreshing = recs.isRefetching || open.isRefetching;

  return (
    <Screen refreshing={refreshing} onRefresh={() => { void recs.refetch(); void open.refetch(); void myGroups.refetch(); }}>
      <Row>
        <Button small title="Notifications" variant="secondary" onPress={() => navigation.navigate('Notifications')} />
        <Button small title="Messages" variant="secondary" onPress={() => navigation.navigate('Messages')} />
      </Row>

      <Subtitle>Buyers looking for your produce</Subtitle>
      {recs.isPending ? <Loading /> : recs.isError ? <ErrorView error={recs.error} onRetry={() => void recs.refetch()} />
        : recs.data.results.length === 0 ? (
          <Empty title="No matching buyer requests yet" hint={recs.data.message ?? 'Add listings to get matched.'} />
        ) : recs.data.results.slice(0, 5).map((m) => <BuyerMatchCard key={m.requirement_id} match={m} />)}

      <Subtitle>Open orders</Subtitle>
      {open.isPending ? <Loading /> : open.isError ? <ErrorView error={open.error} />
        : open.data.results.length === 0 ? <Empty title="No open orders" />
          : open.data.results.map((o) => (
            <OrderRow key={o.id} order={o} onPress={() => navigation.navigate('OrderDetail', { id: o.id })} />
          ))}

      <Subtitle>Your groups</Subtitle>
      {myGroups.data?.results.length ? myGroups.data.results.map((g) => (
        <Card key={g.id} onPress={() => navigation.navigate('GroupDetail', { id: g.id })} accessibilityLabel={g.name}>
          <Body>{g.name}</Body>
          <Body muted>{g.member_count} members · {g.town || g.municipality}</Body>
        </Card>
      )) : <Empty title="You're not in a group yet" hint="Find one in the Co-op hub." />}
    </Screen>
  );
}

export function MyListingsScreen({ navigation }: BottomTabScreenProps<FarmerTabParams, 'MyListings'>) {
  const query = useQuery({ queryKey: ['my-listings'], queryFn: () => listings.mine() });
  return (
    <QueryScreen
      query={query}
      header={<Button title="+ New listing" onPress={() => navigation.navigate('ListingForm')} />}
      isEmpty={(d) => d.results.length === 0}
      emptyTitle="No listings yet"
      emptyHint="Create a listing so buyers can find your produce."
    >
      {(data) => data.results.map((l) => (
        <Card key={l.id} onPress={() => navigation.navigate('ListingForm', { id: l.id })}
          accessibilityLabel={`${l.produce_name}, ${l.status}`}>
          <Row style={styles.between}>
            <Body>{l.produce_name}</Body>
            <Badge text={l.status.replace('_', ' ')} tone={STATUS_TONE[l.status]} />
          </Row>
          <Body muted>
            {qty(l.quantity_available, l.unit)} · {money(l.price_per_unit)}/{l.unit.toLowerCase()} ·{' '}
            {label(QUALITY, l.quality_grade)}
          </Body>
        </Card>
      ))}
    </QueryScreen>
  );
}

function toValues(l: MyListing): ListingValues {
  return {
    produce_name: l.produce_name, quantity_available: String(l.quantity_available), unit: l.unit,
    price_per_unit: String(l.price_per_unit), quality_grade: l.quality_grade ?? 'STANDARD',
    available_from: l.available_from ?? '', description: l.description ?? '',
  };
}

export function ListingFormScreen({ navigation, route }: AppScreenProps<'ListingForm'>) {
  const id = route.params?.id;
  const queryClient = useQueryClient();
  const existing = useQuery({ queryKey: ['listing', id], queryFn: () => listings.get(id!), enabled: !!id });
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['my-listings'] });
    void queryClient.invalidateQueries({ queryKey: ['listing', id] });
  };
  const action = useMutation({
    mutationFn: (fn: () => Promise<unknown>) => fn(),
    onSuccess: refresh,
    onError: (e) => setFormError(parseApiError(e).message),
  });

  async function submit(values: ListingValues) {
    setServerErrors({});
    setFormError(null);
    const body = { ...values, available_from: values.available_from || undefined };
    try {
      if (id) await listings.update(id, body);
      else await listings.create(body);
      refresh();
      navigation.goBack();
    } catch (e) {
      const err = parseApiError(e);
      setServerErrors(err.fieldErrors);
      setFormError(err.message);
    }
  }

  async function addPhoto() {
    if (!id) return;
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setFormError('Photo access was not given.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.7 });
    if (result.canceled || !result.assets?.length) return;
    const asset = result.assets[0];
    if (asset.fileSize && asset.fileSize > 5 * 1024 * 1024) {
      setFormError('Photos must be 5 MB or smaller.');
      return;
    }
    action.mutate(() => listings.addImage(id, {
      uri: asset.uri, name: asset.fileName ?? 'photo.jpg', type: asset.mimeType ?? 'image/jpeg',
    }));
  }

  if (id && existing.isPending) return <Loading />;
  if (id && existing.isError) return <ErrorView error={existing.error} onRetry={() => void existing.refetch()} />;
  const listing = existing.data;

  return (
    <Screen>
      <Title>{id ? 'Edit listing' : 'New listing'}</Title>
      <FormError message={formError} />
      <ListingForm initial={listing ? toValues(listing) : emptyListing} onSubmit={submit} serverErrors={serverErrors}
        submitLabel={id ? 'Save changes' : 'Publish listing'} />
      {listing ? (
        <View style={styles.section}>
          <Subtitle>Photos ({listing.images.length}/5)</Subtitle>
          <ScrollView horizontal contentContainerStyle={styles.photos}>
            {listing.images.map((img) => (
              <View key={img.id} style={styles.photoWrap}>
                <Image source={{ uri: img.image }} style={styles.photo} accessibilityLabel="Listing photo" />
                <Button small variant="secondary" title="Remove"
                  onPress={() => action.mutate(() => listings.removeImage(listing.id, img.id))} />
              </View>
            ))}
          </ScrollView>
          {listing.images.length < 5 ? (
            <Button title="Add photo" variant="secondary" onPress={() => void addPhoto()} loading={action.isPending} />
          ) : null}
          <Subtitle>Status: {listing.status.replace('_', ' ').toLowerCase()}</Subtitle>
          <Row>
            {listing.status === 'PAUSED' ? (
              <Button small title="Resume" onPress={() => action.mutate(() => listings.resume(listing.id))} />
            ) : (
              <Button small variant="secondary" title="Pause"
                onPress={() => action.mutate(() => listings.pause(listing.id))} />
            )}
            <Button small variant="danger" title="Delete" onPress={() => Alert.alert('Delete listing?',
              'Buyers will no longer see it.', [
                { text: 'Keep', style: 'cancel' },
                { text: 'Delete', style: 'destructive', onPress: () => action.mutate(async () => {
                  await listings.remove(listing.id);
                  navigation.goBack();
                }) },
              ])} />
          </Row>
        </View>
      ) : <Body muted>You can add photos after saving.</Body>}
    </Screen>
  );
}

const styles = StyleSheet.create({
  between: { justifyContent: 'space-between' },
  section: { gap: spacing.md },
  photos: { gap: spacing.sm },
  photoWrap: { gap: spacing.xs },
  photo: { width: 110, height: 110, borderRadius: 8, backgroundColor: '#eee' },
});
