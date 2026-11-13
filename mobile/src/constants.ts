import type { Province, QualityGrade, Unit } from './api/types';

export const PROVINCES: { value: Province; label: string }[] = [
  { value: 'EASTERN_CAPE', label: 'Eastern Cape' },
  { value: 'FREE_STATE', label: 'Free State' },
  { value: 'GAUTENG', label: 'Gauteng' },
  { value: 'KWAZULU_NATAL', label: 'KwaZulu-Natal' },
  { value: 'LIMPOPO', label: 'Limpopo' },
  { value: 'MPUMALANGA', label: 'Mpumalanga' },
  { value: 'NORTHERN_CAPE', label: 'Northern Cape' },
  { value: 'NORTH_WEST', label: 'North West' },
  { value: 'WESTERN_CAPE', label: 'Western Cape' },
];

export const UNITS: { value: Unit; label: string }[] = [
  { value: 'KG', label: 'kg' }, { value: 'TONNE', label: 'tonne' }, { value: 'BAG', label: 'bag' },
  { value: 'CRATE', label: 'crate' }, { value: 'BOX', label: 'box' }, { value: 'DOZEN', label: 'dozen' },
  { value: 'LITRE', label: 'litre' }, { value: 'UNIT', label: 'unit' },
];

export const QUALITY: { value: QualityGrade; label: string }[] = [
  { value: 'PREMIUM', label: 'Premium' }, { value: 'ORGANIC', label: 'Organic' }, { value: 'GRADE_A', label: 'Grade A' },
  { value: 'GRADE_B', label: 'Grade B' }, { value: 'STANDARD', label: 'Standard' },
];

export const BUSINESS_TYPES = [
  { value: 'RESTAURANT', label: 'Restaurant' }, { value: 'SUPERMARKET', label: 'Supermarket' },
  { value: 'GROCERY', label: 'Grocery' }, { value: 'DISTRIBUTOR', label: 'Distributor' },
  { value: 'PROCESSOR', label: 'Processor' }, { value: 'WHOLESALER', label: 'Wholesaler' },
  { value: 'OTHER', label: 'Other' },
] as const;

export const ORDER_STATUS_LABEL: Record<string, string> = {
  PENDING: 'Waiting for farmer', ACCEPTED: 'Accepted', REJECTED: 'Declined', DISPATCHED: 'On its way',
  DELIVERED: 'Delivered', COMPLETED: 'Completed', CANCELLED: 'Cancelled',
};

export const STATUS_TONE: Record<string, 'neutral' | 'good' | 'warn' | 'bad'> = {
  PENDING: 'warn', ACCEPTED: 'good', DISPATCHED: 'good', DELIVERED: 'good', COMPLETED: 'good',
  REJECTED: 'bad', CANCELLED: 'bad', ACTIVE: 'good', PAUSED: 'warn', SOLD_OUT: 'bad', OPEN: 'good',
  LOCKED: 'warn', FULL: 'warn', CONFIRMED: 'good', REQUESTED: 'warn', APPROVED: 'good', DECLINED: 'bad',
};

export const label = (options: readonly { value: string; label: string }[], value?: string | null) =>
  options.find((o) => o.value === value)?.label ?? value ?? '';
