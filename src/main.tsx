import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@fontsource/ibm-plex-sans/400.css'
import '@fontsource/ibm-plex-sans/500.css'
import '@fontsource/ibm-plex-sans/600.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/literata/400.css'
import '@fontsource/literata/400-italic.css'
import './styles/fonts.css'
import './styles.css'
import App from './App'
import { RecoveryBoundary } from './components/RecoveryBoundary'

const client = new QueryClient({ defaultOptions: { queries: { staleTime: 10_000, retry: 1, refetchOnWindowFocus: false } } })
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><RecoveryBoundary><QueryClientProvider client={client}><App /></QueryClientProvider></RecoveryBoundary></React.StrictMode>)
