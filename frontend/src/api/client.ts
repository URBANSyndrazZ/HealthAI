const RAW_API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

function trimTrailingSlash(value: string) {
  return value.replace(/\/+$/, '')
}

function withLeadingSlash(path: string) {
  return path.startsWith('/') ? path : `/${path}`
}

export function apiUrl(path: string) {
  const normalizedPath = withLeadingSlash(path)
  const base = trimTrailingSlash(RAW_API_BASE_URL)

  if (!base) {
    return normalizedPath
  }

  if (base.endsWith('/api/v1') && normalizedPath.startsWith('/api/v1')) {
    return `${base}${normalizedPath.slice('/api/v1'.length)}`
  }

  if (base.endsWith('/api') && normalizedPath.startsWith('/api/')) {
    return `${base}${normalizedPath.slice('/api'.length)}`
  }

  return `${base}${normalizedPath}`
}
