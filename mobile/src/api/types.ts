/**
 * Friendly names for the generated OpenAPI types (src/api/schema.d.ts).
 * Regenerate with `npm run gen:api` whenever the backend changes.
 */
import type { components } from './schema';

type S = components['schemas'];

export type User = S['User'];
export type Role = S['UserRoleEnum'];
export type AuthResponse = S['AuthResponse'];
export type Province = S['ProvinceEnum'];
export type MyLocation = S['MyLocation'];
export type PublicLocation = S['PublicLocation'];
export type Distance = S['Distance'];
export type MyFarmerProfile = S['MyFarmerProfile'];
export type MyBuyerProfile = S['MyBuyerProfile'];
export type PublicFarmer = S['PublicFarmer'];
export type ProduceCategory = S['ProduceCategory'];
export type MyListing = S['MyListing'];
export type PublicListing = S['PublicListing'];
export type CompareResponse = S['CompareResponse'];
export type DiscoveredFarmer = S['DiscoveredFarmer'];
export type Requirement = S['Requirement'];
export type FarmerMatch = S['FarmerMatch'];
export type BuyerMatch = S['BuyerMatch'];
export type BuyerMatchList = S['BuyerMatchList'];
export type MultiItemRecommendation = S['MultiItemRecommendation'];
export type Order = S['Order'];
export type OrderStatus = S['OrderStatusEnum'];
export type Notification = S['Notification'];
export type Thread = S['Thread'];
export type ThreadMessage = S['ThreadMessage'];
export type ChatResponse = S['ChatResponse'];
export type PendingActionBrief = S['PendingActionBrief'];
export type ActionResult = S['ActionResult'];
export type Group = S['Group'];
export type GroupDetail = S['GroupDetail'];
export type Post = S['Post'];
export type BulkPurchase = S['BulkPurchase'];
export type TransportRequest = S['TransportRequest'];
export type SharedService = S['SharedService'];
export type SecurityAlert = S['SecurityAlert'];
export type InsuranceProducts = S['InsuranceProducts'];
export type QuoteRequests = S['QuoteRequests'];
export type Equipment = S['Equipment'];
export type Booking = S['Booking'];
export type Unit = S['UnitEnum'];
export type QualityGrade = S['QualityGradeEnum'];

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
