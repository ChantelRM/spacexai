import type { UseQueryResult } from '@tanstack/react-query';
import React from 'react';

import { Empty, ErrorView, Loading, Screen } from './components';

/**
 * Standard screen around a react-query result: loading, error (with retry),
 * empty and pull-to-refresh states, then ``children(data)``.
 */
export function QueryScreen<T>({ query, isEmpty, emptyTitle, emptyHint, header, children }: {
  query: UseQueryResult<T>;
  isEmpty?: (data: T) => boolean;
  emptyTitle?: string;
  emptyHint?: string;
  header?: React.ReactNode;
  children: (data: T) => React.ReactNode;
}) {
  const { data, isPending, isError, error, refetch, isRefetching } = query;
  return (
    <Screen refreshing={isRefetching} onRefresh={() => void refetch()}>
      {header}
      {isPending ? (
        <Loading />
      ) : isError ? (
        <ErrorView error={error} onRetry={() => void refetch()} />
      ) : data !== undefined && isEmpty?.(data) ? (
        <Empty title={emptyTitle ?? 'Nothing here yet'} hint={emptyHint} />
      ) : data !== undefined ? (
        children(data)
      ) : null}
    </Screen>
  );
}
