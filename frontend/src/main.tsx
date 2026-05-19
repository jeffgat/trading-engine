import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { ClerkProvider } from '@clerk/clerk-react'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { clerkAppearance } from './auth/clerkAppearance'
import { CLERK_ENABLED, CLERK_PUBLISHABLE_KEY } from './auth/clerkConfig'

const app = (
  <BrowserRouter>
    <App />
  </BrowserRouter>
)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {CLERK_ENABLED ? (
      <ClerkProvider publishableKey={CLERK_PUBLISHABLE_KEY} appearance={clerkAppearance}>
        {app}
      </ClerkProvider>
    ) : (
      app
    )}
  </StrictMode>,
)
