import { API_URL } from '../config';
import { createApiClient } from './client';
import { secureTokenStore } from './tokens';
import type {
  ActionResult,
  AuthResponse,
  Booking,
  BulkPurchase,
  BuyerMatchList,
  ChatResponse,
  CompareResponse,
  DiscoveredFarmer,
  Equipment,
  Group,
  GroupDetail,
  InsuranceProducts,
  MultiItemRecommendation,
  MyBuyerProfile,
  MyFarmerProfile,
  MyListing,
  MyLocation,
  Notification,
  Order,
  Paginated,
  Post,
  ProduceCategory,
  PublicFarmer,
  PublicListing,
  QuoteRequests,
  Requirement,
  SecurityAlert,
  SharedService,
  Thread,
  ThreadMessage,
  TransportRequest,
  User,
} from './types';

type Listener = () => void;
const expiredListeners = new Set<Listener>();

/** Subscribe to "session expired" (refresh failed). Returns an unsubscribe function. */
export function onSessionExpired(listener: Listener) {
  expiredListeners.add(listener);
  return () => expiredListeners.delete(listener);
}

export const http = createApiClient({
  baseURL: API_URL,
  tokens: secureTokenStore,
  onSessionExpired: () => expiredListeners.forEach((fn) => fn()),
});

const get = <T>(url: string, params?: object) => http.get<T>(url, { params }).then((r) => r.data);
const post = <T>(url: string, body?: object) => http.post<T>(url, body).then((r) => r.data);
const patch = <T>(url: string, body?: object) => http.patch<T>(url, body).then((r) => r.data);
const put = <T>(url: string, body?: object) => http.put<T>(url, body).then((r) => r.data);
const del = (url: string) => http.delete(url).then(() => undefined);

export const auth = {
  login: (email: string, password: string) => post<AuthResponse>('/auth/login/', { email, password }),
  register: (body: { email: string; password: string; role: string; display_name: string; phone_number?: string }) =>
    post<AuthResponse>('/auth/register/', body),
  logout: (refresh: string) => post<void>('/auth/logout/', { refresh }),
  me: () => get<User>('/auth/me/'),
  updateMe: (body: Partial<Pick<User, 'display_name' | 'phone_number'>>) => patch<User>('/auth/me/', body),
};

export const locations = {
  mine: () => get<MyLocation>('/locations/me/'),
  save: (body: object) => put<MyLocation>('/locations/me/', body),
};

export const farmers = {
  myProfile: () => get<MyFarmerProfile>('/farmers/me/profile/'),
  saveProfile: (body: object) => put<MyFarmerProfile>('/farmers/me/profile/', body),
  publicProfile: (id: number) => get<PublicFarmer>(`/farmers/${id}/`),
  recommendedBuyers: () => get<BuyerMatchList>('/farmers/me/recommended-buyers/'),
};

export const listings = {
  categories: () => get<ProduceCategory[]>('/listings/categories/'),
  mine: (status?: string) => get<Paginated<MyListing>>('/listings/mine/', status ? { status } : undefined),
  get: (id: number) => get<MyListing>(`/listings/mine/${id}/`),
  create: (body: object) => post<MyListing>('/listings/mine/', body),
  update: (id: number, body: object) => patch<MyListing>(`/listings/mine/${id}/`, body),
  remove: (id: number) => del(`/listings/mine/${id}/`),
  pause: (id: number) => post<MyListing>(`/listings/mine/${id}/pause/`),
  resume: (id: number) => post<MyListing>(`/listings/mine/${id}/resume/`),
  addImage: (id: number, image: { uri: string; name: string; type: string }) => {
    const form = new FormData();
    // React Native's FormData accepts {uri, name, type} file descriptors.
    form.append('image', image as unknown as Blob);
    return http.post(`/listings/mine/${id}/images/`, form, { headers: { 'Content-Type': 'multipart/form-data' } })
      .then((r) => r.data);
  },
  removeImage: (id: number, imageId: number) => del(`/listings/mine/${id}/images/${imageId}/`),
};

export const marketplace = {
  search: (params: Record<string, string | number | undefined>) =>
    get<Paginated<PublicListing>>('/marketplace/listings/', params),
  listing: (id: number) => get<PublicListing>(`/marketplace/listings/${id}/`),
  compare: (ids: number[]) => get<CompareResponse>('/marketplace/compare/', { listing_ids: ids.join(',') }),
  farmers: (params: Record<string, string | undefined>) =>
    get<Paginated<DiscoveredFarmer>>('/marketplace/farmers/', params),
};

export const buyers = {
  myProfile: () => get<MyBuyerProfile>('/buyers/me/profile/'),
  saveProfile: (body: object) => put<MyBuyerProfile>('/buyers/me/profile/', body),
  recommendedFarmers: () => get<MultiItemRecommendation>('/buyers/me/recommended-farmers/'),
  requirements: (status?: string) =>
    get<Paginated<Requirement>>('/buyers/requirements/', status ? { status } : undefined),
  requirement: (id: number) => get<Requirement>(`/buyers/requirements/${id}/`),
  createRequirement: (body: object) => post<Requirement>('/buyers/requirements/', body),
  updateRequirement: (id: number, body: object) => patch<Requirement>(`/buyers/requirements/${id}/`, body),
  closeRequirement: (id: number) => del(`/buyers/requirements/${id}/`),
};

export const orders = {
  list: (status?: string) => get<Paginated<Order>>('/orders/', status ? { status } : undefined),
  get: (id: number) => get<Order>(`/orders/${id}/`),
  create: (body: { items: { listing_id: number; quantity: string }[]; delivery_date?: string; delivery_notes?: string }) =>
    post<Order>('/orders/', body),
  act: (id: number, action: 'accept' | 'reject' | 'dispatch' | 'confirm-receipt' | 'complete' | 'cancel',
    reason?: string) => post<Order>(`/orders/${id}/${action}/`, reason ? { reason } : {}),
  setPayment: (id: number, payment_status: string) => post<Order>(`/orders/${id}/payment-status/`, { payment_status }),
};

export const messaging = {
  threads: () => get<Paginated<Thread>>('/messaging/conversations/'),
  start: (other_user_id: number, message?: string, order_id?: number) =>
    post<Thread>('/messaging/conversations/', { other_user_id, message, order_id }),
  messages: (id: number) => get<Paginated<ThreadMessage>>(`/messaging/conversations/${id}/messages/`,
    { page_size: 100 }),
  send: (id: number, body: string) => post<ThreadMessage>(`/messaging/conversations/${id}/messages/`, { body }),
  markRead: (id: number) => post(`/messaging/conversations/${id}/read/`),
};

export const notifications = {
  list: () => get<Paginated<Notification>>('/notifications/'),
  unreadCount: () => get<{ unread: number }>('/notifications/unread-count/'),
  read: (id: number) => post<Notification>(`/notifications/${id}/read/`),
  readAll: () => post('/notifications/read-all/'),
};

export const ai = {
  chat: (message: string, conversation_id?: string) =>
    post<ChatResponse>('/ai/chat/', { message, conversation_id }),
  confirm: (id: string) => post<ActionResult>(`/ai/actions/${id}/confirm/`),
  cancel: (id: string) => post<ActionResult>(`/ai/actions/${id}/cancel/`),
};

export const groups = {
  list: (params?: Record<string, string | undefined>) => get<Paginated<Group>>('/groups/', params),
  get: (id: number) => get<GroupDetail>(`/groups/${id}/`),
  create: (body: object) => post<Group>('/groups/', body),
  join: (id: number) => post(`/groups/${id}/join/`),
  leave: (id: number) => post(`/groups/${id}/leave/`),
  respondInvite: (id: number, accept: boolean) => post(`/groups/${id}/invitation/`, { accept }),
  decide: (id: number, farmer_id: number, accept: boolean) =>
    post(`/groups/${id}/requests/decide/`, { farmer_id, accept }),
  posts: (id: number) => get<Paginated<Post>>(`/groups/${id}/posts/`),
  addPost: (id: number, body: string, is_announcement = false) =>
    post<Post>(`/groups/${id}/posts/`, { body, is_announcement }),
};

export const bulk = {
  list: (params?: Record<string, string | undefined>) => get<Paginated<BulkPurchase>>('/bulk-purchases/', params),
  get: (id: number) => get<BulkPurchase>(`/bulk-purchases/${id}/`),
  join: (id: number, quantity: string) => post<BulkPurchase>(`/bulk-purchases/${id}/join/`, { quantity }),
  leave: (id: number) => post(`/bulk-purchases/${id}/leave/`),
  confirm: (id: number) => post<BulkPurchase>(`/bulk-purchases/${id}/confirm/`),
  setStatus: (id: number, status: string) => post<BulkPurchase>(`/bulk-purchases/${id}/status/`, { status }),
};

export const transport = {
  list: (params?: Record<string, string | undefined>) => get<Paginated<TransportRequest>>('/transport/', params),
  get: (id: number) => get<TransportRequest>(`/transport/${id}/`),
  join: (id: number, load: object) => post<TransportRequest>(`/transport/${id}/join/`, load),
  leave: (id: number) => post<TransportRequest>(`/transport/${id}/leave/`),
  confirm: (id: number) => post<TransportRequest>(`/transport/${id}/confirm/`),
};

export const services = {
  security: () => get<Paginated<SharedService>>('/services/security/'),
  joinSecurity: (id: number) => post<SharedService>(`/services/security/${id}/join/`, {}),
  confirmSecurity: (id: number) => post<SharedService>(`/services/security/${id}/confirm/`),
  alerts: () => get<Paginated<SecurityAlert>>('/services/security-alerts/'),
  postAlert: (body: object) => post<SecurityAlert>('/services/security-alerts/', body),
  insuranceProducts: () => get<InsuranceProducts>('/services/insurance/products/'),
  quoteRequests: () => get<QuoteRequests>('/services/insurance/quote-requests/'),
  requestQuote: (body: { category: string; details: string; product?: number }) =>
    post('/services/insurance/quote-requests/', body),
};

export const equipment = {
  list: (params?: Record<string, string | undefined>) => get<Paginated<Equipment>>('/equipment/items/', params),
  get: (id: number) => get<Equipment>(`/equipment/items/${id}/`),
  book: (id: number, body: { start: string; end: string; quantity?: string; notes?: string }) =>
    post<Booking>(`/equipment/items/${id}/book/`, body),
  bookings: (role: 'requester' | 'owner') => get<Paginated<Booking>>('/equipment/bookings/', { role }),
  decide: (id: number, approve: boolean) => post<Booking>(`/equipment/bookings/${id}/decision/`, { approve }),
};
