import './assets/styles/index.scss'

import { ResizeObserver } from '@juggle/resize-observer'
import { ComposeContextProvider } from 'foxact/compose-context-provider'
import React from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router'
import { SWRConfig } from 'swr'
import { MihomoWebSocket } from 'tauri-plugin-mihomo-api'

import {
  assessRuntimeContract,
  getRuntimeInfo,
  isRuntimeInfo,
  persistRuntimeAssessment,
  vergeJson,
  type RuntimeContractAssessment,
  type RuntimeInfo,
} from '@root/browser/runtime'
import { BaseErrorBoundary } from './components/base'
import { router } from './pages/_routers'
import { AppDataProvider } from './providers/app-data-provider'
import { WindowProvider } from './providers/window'
import { FALLBACK_LANGUAGE, initializeLanguage } from './services/i18n'
import {
  preloadAppData,
  resolveThemeMode,
  getPreloadConfig,
} from './services/preload'
import { swrConfig } from './services/query-client'
import {
  LoadingCacheProvider,
  ThemeModeProvider,
  UpdateStateProvider,
} from './services/states'
import { disableWebViewShortcuts } from './utils/disable-webview-shortcuts'

if (!window.ResizeObserver) {
  window.ResizeObserver = ResizeObserver
}

const mainElementId = 'root'
const container = document.getElementById(mainElementId)

if (!container) {
  throw new Error(`No container '${mainElementId}' found to render application`)
}

disableWebViewShortcuts()

const RuntimeContractGate = ({
  assessment,
  children,
}: {
  assessment: RuntimeContractAssessment | null
  children: React.ReactNode
}) => {
  if (assessment?.status === 'blocked') {
    return (
      <div
        role="alert"
        style={{
          alignItems: 'center',
          background: '#181a1b',
          color: '#fff',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
          justifyContent: 'center',
          minHeight: '100vh',
          padding: '24px',
          textAlign: 'center',
        }}
      >
        <strong>Clash Verge WebPort 无法安全启动</strong>
        <span>{assessment.reason ?? '运行时契约校验失败。'}</span>
      </div>
    )
  }
  return children
}

const loadRuntimeAssessment = async (): Promise<RuntimeContractAssessment | null> => {
  if (!window.__LZCAPP_MIHOMO__) return null

  try {
    const configured = getRuntimeInfo()
    const actual = isRuntimeInfo(configured)
      ? configured
      : await vergeJson<RuntimeInfo>('/runtime-info')
    const assessment = assessRuntimeContract(actual)
    persistRuntimeAssessment(assessment)
    return assessment
  } catch (error) {
    console.error('[main.tsx] Runtime contract probe failed:', error)
    const assessment = assessRuntimeContract(null)
    persistRuntimeAssessment(assessment)
    return assessment
  }
}

const initializeApp = (
  initialThemeMode: 'light' | 'dark',
  runtimeAssessment: RuntimeContractAssessment | null,
) => {
  const contexts = [
    <ThemeModeProvider key="theme" initialState={initialThemeMode} />,
    <LoadingCacheProvider key="loading" />,
    <UpdateStateProvider key="update" />,
  ]

  const root = createRoot(container)
  root.render(
    <React.StrictMode>
      <ComposeContextProvider contexts={contexts}>
        <BaseErrorBoundary>
          <RuntimeContractGate assessment={runtimeAssessment}>
            <SWRConfig value={swrConfig}>
              <WindowProvider>
                <AppDataProvider>
                  <RouterProvider router={router} />
                </AppDataProvider>
              </WindowProvider>
            </SWRConfig>
          </RuntimeContractGate>
        </BaseErrorBoundary>
      </ComposeContextProvider>
    </React.StrictMode>,
  )
}

const bootstrap = async () => {
  const { initialThemeMode } = await preloadAppData()
  const runtimeAssessment = await loadRuntimeAssessment()
  initializeApp(initialThemeMode, runtimeAssessment)
}

bootstrap().catch((error) => {
  console.error(
    '[main.tsx] App bootstrap failed, falling back to default language:',
    error,
  )
  initializeLanguage(FALLBACK_LANGUAGE)
    .catch((fallbackError) => {
      console.error(
        '[main.tsx] Fallback language initialization failed:',
        fallbackError,
      )
    })
    .finally(() => {
      void loadRuntimeAssessment().then((runtimeAssessment) => {
        initializeApp(resolveThemeMode(getPreloadConfig()), runtimeAssessment)
      })
    })
})

// Error handling
window.addEventListener('error', (event) => {
  console.error('[main.tsx] Global error:', event.error)
})

window.addEventListener('unhandledrejection', (event) => {
  console.error('[main.tsx] Unhandled promise rejection:', event.reason)
})

// Page close/refresh events
window.addEventListener('beforeunload', () => {
  // Clean up all WebSocket instances to prevent memory leaks
  MihomoWebSocket.cleanupAll()
})

// Page loaded event
window.addEventListener('DOMContentLoaded', () => {
  // Clean up all WebSocket instances to prevent memory leaks
  MihomoWebSocket.cleanupAll()
})
