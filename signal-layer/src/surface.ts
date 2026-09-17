export type AppSurface = 'public' | 'private'

export function setAppSurface(surface: AppSurface) {
  document.documentElement.dataset.signalSurface = surface
}

export function getAppSurface(): AppSurface {
  return document.documentElement.dataset.signalSurface === 'public' ? 'public' : 'private'
}
