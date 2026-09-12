import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { Auth0ProviderWithNavigate } from '@/components/Auth0ProviderWithNavigate'
import { KataCopilotPopup } from '@/components/KataCopilotPopup'
import { SessionGate } from '@/components/SessionGate'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { AppRouter } from '@/router'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
})

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={200}>
        <BrowserRouter>
          <Auth0ProviderWithNavigate>
            <SessionGate>
              <AppRouter />
              {/* W10: one bot for the whole app, mounted at the router root
                  rather than threaded into every screen. Inside SessionGate
                  so it never renders to a signed-out visitor. */}
              <KataCopilotPopup />
            </SessionGate>
          </Auth0ProviderWithNavigate>
        </BrowserRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  )
}

export default App
