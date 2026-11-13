import { useNavigation } from '@react-navigation/native';
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import type { BuyerMatch, FarmerMatch, Order, PublicListing } from '../api/types';
import { label, ORDER_STATUS_LABEL, QUALITY, STATUS_TONE } from '../constants';
import { Badge, Body, Card, distanceText, money, qty, Row } from '../ui/components';
import { colors, spacing } from '../ui/theme';

function Reasons({ reasons, gaps }: { reasons: string[]; gaps?: string[] }) {
  return (
    <View style={styles.reasons}>
      {reasons.slice(0, 4).map((r) => <Text key={r} style={styles.reason}>✓ {r}</Text>)}
      {(gaps ?? []).map((g) => <Text key={g} style={styles.gap}>! {g}</Text>)}
    </View>
  );
}

export function FarmerMatchCard({ match, onCompareToggle, selected }: {
  match: FarmerMatch;
  onCompareToggle?: () => void;
  selected?: boolean;
}) {
  const navigation = useNavigation();
  return (
    <Card onPress={() => navigation.navigate('ListingDetail', { id: match.listing_id })}
      accessibilityLabel={`${match.farmer_display_name}, ${match.produce}, score ${match.score}`}>
      <Row style={styles.between}>
        <Text style={styles.name}>{match.farmer_display_name}{match.is_verified ? ' ✔' : ''}</Text>
        <Badge text={`${match.score}/100`} tone={match.score >= 70 ? 'good' : match.score >= 45 ? 'warn' : 'neutral'} />
      </Row>
      <Body>{match.produce} · {qty(match.available_quantity, match.unit)} · {money(match.price_per_unit)}/{match.unit.toLowerCase()}</Body>
      <Body muted>{label(QUALITY, match.quality_grade)} · {match.location?.town ?? ''} · {distanceText(match.location?.distance)}</Body>
      {match.shortfall ? <Badge text={match.shortfall} tone="warn" /> : null}
      {match.covers_multiple ? <Badge text="Can supply several of your items" tone="good" /> : null}
      <Reasons reasons={match.match_reasons} gaps={match.gaps.filter((g) => g !== match.shortfall)} />
      {onCompareToggle ? (
        <Text onPress={onCompareToggle} style={styles.link} accessibilityRole="checkbox"
          accessibilityState={{ checked: !!selected }}>
          {selected ? '☑ Selected to compare' : '☐ Compare'}
        </Text>
      ) : null}
    </Card>
  );
}

export function BuyerMatchCard({ match }: { match: BuyerMatch }) {
  return (
    <Card accessibilityLabel={`${match.buyer_display_name} needs ${match.produce}`}>
      <Row style={styles.between}>
        <Text style={styles.name}>{match.business_name ?? match.buyer_display_name}</Text>
        <Badge text={`${match.score}/100`} tone={match.score >= 70 ? 'good' : 'warn'} />
      </Row>
      <Body>Needs {qty(match.quantity, match.unit)} {match.produce} by {match.needed_by}</Body>
      <Body muted>
        {match.target_price_per_unit != null ? `Up to ${money(match.target_price_per_unit)}/${match.unit.toLowerCase()} · ` : ''}
        {match.location?.town ?? ''} · {distanceText(match.location?.distance)}
      </Body>
      <Reasons reasons={match.match_reasons} gaps={match.gaps} />
    </Card>
  );
}

export function ListingCard({ listing, onPress, right }: {
  listing: PublicListing;
  onPress?: () => void;
  right?: React.ReactNode;
}) {
  return (
    <Card onPress={onPress} accessibilityLabel={`${listing.produce_name} from ${listing.farmer.display_name}`}>
      <Row style={styles.between}>
        <Text style={styles.name}>{listing.produce_name}</Text>
        {right ?? <Text style={styles.price}>{money(listing.price_per_unit)}/{listing.unit.toLowerCase()}</Text>}
      </Row>
      <Body>{qty(listing.quantity_available, listing.unit)} · {label(QUALITY, listing.quality_grade)}</Body>
      <Body muted>
        {listing.farmer.display_name}{listing.farmer.is_verified ? ' ✔' : ''} · {listing.location?.town ?? ''} ·{' '}
        {distanceText(listing.location?.distance)}
      </Body>
    </Card>
  );
}

export function OrderRow({ order, onPress }: { order: Order; onPress: () => void }) {
  const items = order.items.map((i) => `${qty(i.quantity, i.unit)} ${i.produce_name}`).join(', ');
  return (
    <Card onPress={onPress} accessibilityLabel={`Order ${order.id}, ${ORDER_STATUS_LABEL[order.status]}`}>
      <Row style={styles.between}>
        <Text style={styles.name}>Order #{order.id}</Text>
        <Badge text={ORDER_STATUS_LABEL[order.status] ?? order.status} tone={STATUS_TONE[order.status]} />
      </Row>
      <Body>{items}</Body>
      <Body muted>{order.buyer.display_name} → {order.farmer.display_name} · {money(order.total_amount)}</Body>
    </Card>
  );
}

const styles = StyleSheet.create({
  between: { justifyContent: 'space-between' },
  name: { fontWeight: '700', fontSize: 16, color: colors.text, flexShrink: 1 },
  price: { fontWeight: '700', color: colors.primaryDark },
  reasons: { gap: 2, marginTop: spacing.xs },
  reason: { color: colors.primaryDark, fontSize: 13 },
  gap: { color: '#8D6E00', fontSize: 13 },
  link: { color: colors.info, fontWeight: '600', marginTop: spacing.xs },
});
