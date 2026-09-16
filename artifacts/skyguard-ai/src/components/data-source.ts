export type DataSource = 'SIMULATOR' | 'PHYSICAL_AWS';

const DEFAULT_DATA_SOURCE: DataSource = 'SIMULATOR';

export function getDataSource(): DataSource {
  const configured = import.meta.env.VITE_SKYGUARD_DATA_SOURCE;
  return configured === 'PHYSICAL_AWS' ? 'PHYSICAL_AWS' : DEFAULT_DATA_SOURCE;
}

export function getDataSourceLabel(source: DataSource = getDataSource()): string {
  return source === 'PHYSICAL_AWS' ? 'Physical AWS' : 'Simulator';
}
