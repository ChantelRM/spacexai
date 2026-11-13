import { useQuery, useQueryClient } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import * as Location from 'expo-location';
import React, { useEffect, useState } from 'react';
import { StyleSheet, Switch, Text, View } from 'react-native';

import { buyers, farmers, locations } from '../api';
import { parseApiError } from '../api/errors';
import type { Province } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { BUSINESS_TYPES, PROVINCES } from '../constants';
import type { AppScreenProps } from '../navigation/types';
import { Body, Button, Card, Choice, Field, FormError, Loading, Screen, Subtitle } from '../ui/components';
import { colors, spacing } from '../ui/theme';

const optional404 = <T,>(fn: () => Promise<T>) => async () => {
  try {
    return await fn();
  } catch (e) {
    if (isAxiosError(e) && e.response?.status === 404) return null;
    throw e;
  }
};

/** Profile + location setup. Shown after registration and reachable from Profile to edit. */
export function OnboardingScreen({ navigation, route }: AppScreenProps<'Onboarding'>) {
  const { role } = useAuth();
  const isFarmer = role === 'FARMER';
  const queryClient = useQueryClient();
  const existingLocation = useQuery({ queryKey: ['location', 'edit'], queryFn: optional404(locations.mine) });
  const existingProfile = useQuery({
    queryKey: ['profile', role, 'edit'],
    queryFn: optional404<Record<string, unknown>>(isFarmer ? farmers.myProfile : buyers.myProfile),
  });

  const [name, setName] = useState('');
  const [businessType, setBusinessType] = useState<string>('RESTAURANT');
  const [produce, setProduce] = useState('');
  const [province, setProvince] = useState<Province | undefined>();
  const [municipality, setMunicipality] = useState('');
  const [town, setTown] = useState('');
  const [shareGps, setShareGps] = useState(false);
  const [coords, setCoords] = useState<{ latitude: number; longitude: number } | null>(null);
  const [gpsNote, setGpsNote] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const loc = existingLocation.data;
    if (loc) {
      setProvince(loc.province);
      setMunicipality(loc.municipality);
      setTown(loc.town);
      if (loc.latitude != null && loc.longitude != null) {
        setShareGps(true);
        setCoords({ latitude: Number(loc.latitude), longitude: Number(loc.longitude) });
      }
    }
    const p = existingProfile.data as Record<string, unknown> | null | undefined;
    if (p) {
      setName(String((isFarmer ? p.farm_name : p.business_name) ?? ''));
      if (!isFarmer && p.business_type) setBusinessType(String(p.business_type));
      const list = (isFarmer ? p.main_produce : p.produce_interests) as string[] | undefined;
      if (list) setProduce(list.join(', '));
    }
  }, [existingLocation.data, existingProfile.data, isFarmer]);

  async function toggleGps(on: boolean) {
    setGpsNote(null);
    if (!on) {
      setShareGps(false);
      setCoords(null);
      return;
    }
    const permission = await Location.requestForegroundPermissionsAsync();
    if (!permission.granted) {
      setGpsNote('Location permission was not given. You can still use the app without GPS.');
      return;
    }
    const position = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
    setCoords({ latitude: position.coords.latitude, longitude: position.coords.longitude });
    setShareGps(true);
  }

  async function save() {
    setErrors({});
    setFormError(null);
    const local: Record<string, string> = {};
    if (name.trim().length < 2) local.name = isFarmer ? 'Enter your farm name' : 'Enter your business name';
    if (!province) local.province = 'Choose your province';
    if (municipality.trim().length < 2) local.municipality = 'Enter your municipality';
    if (town.trim().length < 2) local.town = 'Enter your town or village';
    if (Object.keys(local).length) {
      setErrors(local);
      return;
    }
    setSaving(true);
    const list = produce.split(',').map((s) => s.trim()).filter(Boolean);
    try {
      await locations.save({
        province, municipality: municipality.trim(), town: town.trim(),
        latitude: shareGps && coords ? coords.latitude : null,
        longitude: shareGps && coords ? coords.longitude : null,
        share_precise_location: shareGps,
      });
      if (isFarmer) await farmers.saveProfile({ farm_name: name.trim(), main_produce: list });
      else await buyers.saveProfile({ business_name: name.trim(), business_type: businessType, produce_interests: list });
      await queryClient.invalidateQueries({ queryKey: ['location'] });
      await queryClient.invalidateQueries({ queryKey: ['profile'] });
      if (route.params?.editing) navigation.goBack();
    } catch (e) {
      const err = parseApiError(e);
      setErrors(err.fieldErrors);
      setFormError(err.message);
    } finally {
      setSaving(false);
    }
  }

  if (existingLocation.isPending || existingProfile.isPending) return <Loading />;

  return (
    <Screen>
      <Subtitle>{isFarmer ? 'Your farm' : 'Your business'}</Subtitle>
      <FormError message={formError} />
      <Field label={isFarmer ? 'Farm name' : 'Business name'} value={name} onChangeText={setName} error={errors.name} />
      {!isFarmer ? (
        <Choice label="Business type" options={[...BUSINESS_TYPES]} value={businessType} onChange={setBusinessType} />
      ) : null}
      <Field label={isFarmer ? 'What do you grow? (comma separated)' : 'What do you buy? (comma separated)'}
        value={produce} onChangeText={setProduce} placeholder="Tomatoes, Spinach" />

      <Subtitle>Where are you?</Subtitle>
      <Choice label="Province" options={PROVINCES} value={province} onChange={setProvince} error={errors.province} />
      <Field label="Municipality" value={municipality} onChangeText={setMunicipality}
        placeholder="e.g. City of Johannesburg" error={errors.municipality} />
      <Field label="Town, village or city" value={town} onChangeText={setTown} placeholder="e.g. Soweto"
        error={errors.town ?? errors.latitude} />

      <Card>
        <View style={styles.switchRow}>
          <Text style={styles.switchLabel}>Use my phone's GPS for distances</Text>
          <Switch value={shareGps} onValueChange={(v) => void toggleGps(v)} accessibilityLabel="Use GPS for distances"
            trackColor={{ true: colors.primary }} />
        </View>
        <Body muted>
          Optional. Your exact location is never shown to anyone. We only use it to work out approximate distances,
          like "≈ 12 km away". Without GPS we match you by town, municipality and province.
        </Body>
        {coords ? <Body muted>GPS location captured.</Body> : null}
        {gpsNote ? <Body muted>{gpsNote}</Body> : null}
      </Card>

      <Button title="Save and continue" onPress={() => void save()} loading={saving} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  switchRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  switchLabel: { flex: 1, fontWeight: '600', color: colors.text },
});
