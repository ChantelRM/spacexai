import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { useQuery } from '@tanstack/react-query';
import { isAxiosError } from 'axios';
import React from 'react';
import { Text } from 'react-native';

import { buyers, farmers, locations, notifications } from '../api';
import { useAuth } from '../auth/AuthContext';
import { POLL_INTERVAL_MS } from '../config';
import { ForgotPasswordScreen, LoginScreen, RegisterScreen, WelcomeScreen } from '../screens/auth';
import { BuyerDashboard, CompareScreen, MarketplaceScreen, PlaceOrderScreen, RequirementFormScreen,
  RequirementsScreen } from '../screens/buyer';
import { BulkDetailScreen, BulkListScreen, CoopHubScreen, EquipmentDetailScreen, EquipmentListScreen,
  GroupDetailScreen, GroupsScreen, InsuranceScreen, SecurityScreen, TransportDetailScreen,
  TransportListScreen } from '../screens/coop';
import { FarmerDashboard, ListingFormScreen, MyListingsScreen } from '../screens/farmer';
import { OnboardingScreen } from '../screens/onboarding';
import { AssistantScreen } from '../screens/assistant';
import { FarmerProfileScreen, ListingDetailScreen, MessagesScreen, NotificationsScreen, OrderDetailScreen,
  OrdersScreen, ProfileScreen, ThreadScreen } from '../screens/shared';
import { Loading } from '../ui/components';
import { colors } from '../ui/theme';
import type { AppStackParams, AuthStackParams, BuyerTabParams, FarmerTabParams } from './types';

const AuthStack = createNativeStackNavigator<AuthStackParams>();
const AppStack = createNativeStackNavigator<AppStackParams>();
const FarmerTabs = createBottomTabNavigator<FarmerTabParams>();
const BuyerTabs = createBottomTabNavigator<BuyerTabParams>();

function icon(glyph: string) {
  return ({ color }: { color: string }) => <Text style={{ color, fontSize: 18 }} accessibilityElementsHidden>{glyph}</Text>;
}

function useUnreadBadge() {
  const { data } = useQuery({ queryKey: ['notifications', 'unread'], queryFn: notifications.unreadCount,
    refetchInterval: POLL_INTERVAL_MS });
  return data?.unread ? data.unread : undefined;
}

const tabOptions = {
  tabBarActiveTintColor: colors.primary,
  headerTitleStyle: { fontWeight: '700' as const },
};

function FarmerTabsNavigator() {
  const unread = useUnreadBadge();
  return (
    <FarmerTabs.Navigator screenOptions={tabOptions}>
      <FarmerTabs.Screen name="Dashboard" component={FarmerDashboard}
        options={{ tabBarIcon: icon('⌂'), tabBarBadge: unread }} />
      <FarmerTabs.Screen name="MyListings" component={MyListingsScreen}
        options={{ title: 'My listings', tabBarIcon: icon('☰') }} />
      <FarmerTabs.Screen name="Orders" component={OrdersScreen} options={{ tabBarIcon: icon('▤') }} />
      <FarmerTabs.Screen name="Coop" component={CoopHubScreen} options={{ title: 'Co-op hub', tabBarIcon: icon('⚑') }} />
      <FarmerTabs.Screen name="Assistant" component={AssistantScreen} options={{ tabBarIcon: icon('✦') }} />
      <FarmerTabs.Screen name="Profile" component={ProfileScreen} options={{ tabBarIcon: icon('☺') }} />
    </FarmerTabs.Navigator>
  );
}

function BuyerTabsNavigator() {
  const unread = useUnreadBadge();
  return (
    <BuyerTabs.Navigator screenOptions={tabOptions}>
      <BuyerTabs.Screen name="Dashboard" component={BuyerDashboard}
        options={{ tabBarIcon: icon('⌂'), tabBarBadge: unread }} />
      <BuyerTabs.Screen name="Marketplace" component={MarketplaceScreen} options={{ tabBarIcon: icon('⌕') }} />
      <BuyerTabs.Screen name="Requirements" component={RequirementsScreen} options={{ tabBarIcon: icon('☰') }} />
      <BuyerTabs.Screen name="Orders" component={OrdersScreen} options={{ tabBarIcon: icon('▤') }} />
      <BuyerTabs.Screen name="Assistant" component={AssistantScreen} options={{ tabBarIcon: icon('✦') }} />
      <BuyerTabs.Screen name="Profile" component={ProfileScreen} options={{ tabBarIcon: icon('☺') }} />
    </BuyerTabs.Navigator>
  );
}

const is404 = (e: unknown) => isAxiosError(e) && e.response?.status === 404;

/** Signed in: onboarding until location + profile exist, then tabs and detail screens. */
function AppNavigator() {
  const { role } = useAuth();
  const location = useQuery({ queryKey: ['location'], queryFn: locations.mine, retry: (n, e) => !is404(e) && n < 2 });
  const profile = useQuery({
    queryKey: ['profile', role],
    queryFn: role === 'FARMER' ? farmers.myProfile : buyers.myProfile,
    retry: (n, e) => !is404(e) && n < 2,
  });
  if (location.isPending || profile.isPending) return <Loading label="Getting your account ready…" />;
  const needsOnboarding = is404(location.error) || is404(profile.error);
  const Tabs = role === 'FARMER' ? FarmerTabsNavigator : BuyerTabsNavigator;

  return (
    <AppStack.Navigator screenOptions={{ headerBackTitle: 'Back' }}>
      {needsOnboarding ? (
        <AppStack.Screen name="Onboarding" component={OnboardingScreen} options={{ title: 'Set up your account' }} />
      ) : (
        <>
          <AppStack.Screen name="Tabs" component={Tabs} options={{ headerShown: false }} />
          <AppStack.Screen name="Onboarding" component={OnboardingScreen} options={{ title: 'Profile & location' }} />
          <AppStack.Screen name="ListingForm" component={ListingFormScreen} options={{ title: 'Listing' }} />
          <AppStack.Screen name="ListingDetail" component={ListingDetailScreen} options={{ title: 'Listing' }} />
          <AppStack.Screen name="FarmerProfile" component={FarmerProfileScreen} options={{ title: 'Farmer' }} />
          <AppStack.Screen name="Compare" component={CompareScreen} options={{ title: 'Compare' }} />
          <AppStack.Screen name="PlaceOrder" component={PlaceOrderScreen} options={{ title: 'Place order' }} />
          <AppStack.Screen name="RequirementForm" component={RequirementFormScreen} options={{ title: 'Requirement' }} />
          <AppStack.Screen name="OrderDetail" component={OrderDetailScreen} options={{ title: 'Order' }} />
          <AppStack.Screen name="Messages" component={MessagesScreen} />
          <AppStack.Screen name="Thread" component={ThreadScreen} options={({ route }) => ({ title: route.params.title })} />
          <AppStack.Screen name="Notifications" component={NotificationsScreen} />
          <AppStack.Screen name="Groups" component={GroupsScreen} options={{ title: 'Farmer groups' }} />
          <AppStack.Screen name="GroupDetail" component={GroupDetailScreen} options={{ title: 'Group' }} />
          <AppStack.Screen name="BulkList" component={BulkListScreen} options={{ title: 'Bulk buying' }} />
          <AppStack.Screen name="BulkDetail" component={BulkDetailScreen} options={{ title: 'Bulk purchase' }} />
          <AppStack.Screen name="TransportList" component={TransportListScreen} options={{ title: 'Shared transport' }} />
          <AppStack.Screen name="TransportDetail" component={TransportDetailScreen} options={{ title: 'Trip' }} />
          <AppStack.Screen name="Security" component={SecurityScreen} options={{ title: 'Security' }} />
          <AppStack.Screen name="Insurance" component={InsuranceScreen} options={{ title: 'Insurance info' }} />
          <AppStack.Screen name="EquipmentList" component={EquipmentListScreen} options={{ title: 'Equipment & storage' }} />
          <AppStack.Screen name="EquipmentDetail" component={EquipmentDetailScreen} options={{ title: 'Equipment' }} />
        </>
      )}
    </AppStack.Navigator>
  );
}

export function RootNavigator() {
  const { status } = useAuth();
  if (status === 'loading') return <Loading label="Starting…" />;
  if (status === 'signedIn') return <AppNavigator />;
  return (
    <AuthStack.Navigator>
      <AuthStack.Screen name="Welcome" component={WelcomeScreen} options={{ headerShown: false }} />
      <AuthStack.Screen name="Login" component={LoginScreen} options={{ title: 'Log in' }} />
      <AuthStack.Screen name="Register" component={RegisterScreen} options={{ title: 'Create account' }} />
      <AuthStack.Screen name="ForgotPassword" component={ForgotPasswordScreen} options={{ title: 'Forgot password' }} />
    </AuthStack.Navigator>
  );
}
