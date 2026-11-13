import type { NativeStackScreenProps } from '@react-navigation/native-stack';

export type AuthStackParams = {
  Welcome: undefined;
  Login: undefined;
  Register: { role?: 'FARMER' | 'WHOLESALE_BUYER' } | undefined;
  ForgotPassword: undefined;
};

/** Root stack once signed in: the role tabs plus every detail screen. */
export type AppStackParams = {
  Tabs: undefined;
  Onboarding: { editing?: boolean } | undefined;
  ListingForm: { id?: number } | undefined;
  ListingDetail: { id: number };
  FarmerProfile: { id: number };
  Compare: { ids: number[] };
  PlaceOrder: { listingId: number };
  RequirementForm: { id?: number } | undefined;
  OrderDetail: { id: number };
  Messages: undefined;
  Thread: { id: number; title: string };
  Notifications: undefined;
  Groups: undefined;
  GroupDetail: { id: number };
  BulkList: undefined;
  BulkDetail: { id: number };
  TransportList: undefined;
  TransportDetail: { id: number };
  Security: undefined;
  Insurance: undefined;
  EquipmentList: undefined;
  EquipmentDetail: { id: number };
};

export type FarmerTabParams = {
  Dashboard: undefined;
  MyListings: undefined;
  Orders: undefined;
  Coop: undefined;
  Assistant: undefined;
  Profile: undefined;
};

export type BuyerTabParams = {
  Dashboard: undefined;
  Marketplace: undefined;
  Requirements: undefined;
  Orders: undefined;
  Assistant: undefined;
  Profile: undefined;
};

export type AppScreenProps<K extends keyof AppStackParams> = NativeStackScreenProps<AppStackParams, K>;
export type AuthScreenProps<K extends keyof AuthStackParams> = NativeStackScreenProps<AuthStackParams, K>;

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace ReactNavigation {
    // eslint-disable-next-line @typescript-eslint/no-empty-object-type
    interface RootParamList extends AppStackParams {}
  }
}
