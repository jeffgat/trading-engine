import { SignInButton, SignedIn, SignedOut, UserButton } from "@clerk/clerk-react";
import { LogIn } from "lucide-react";
import { clerkAppearance } from "@/auth/clerkAppearance";
import type { OwnerAuthState } from "@/auth/clerkConfig";

interface AuthControlsProps {
  enabled: boolean;
  showFallback: boolean;
  state: OwnerAuthState;
}

export function AuthControls({ enabled, showFallback, state }: AuthControlsProps) {
  if (!enabled) {
    if (!showFallback) return null;
    return (
      <span
        className="rounded-md border border-border bg-bg-primary/70 px-3 py-2 font-mono text-xs lowercase text-text-muted"
        title="Set VITE_CLERK_PUBLISHABLE_KEY in frontend/.env to enable Clerk auth"
      >
        auth unavailable
      </span>
    );
  }

  return <ClerkAuthControls state={state} />;
}

function ClerkAuthControls({ state }: { state: OwnerAuthState }) {
  return (
    <div className="flex items-center gap-3">
      {state.isUnauthorized && (
        <span className="hidden font-mono text-xs lowercase text-loss sm:inline">
          unauthorized email
        </span>
      )}

      <SignedOut>
        <SignInButton mode="modal" appearance={clerkAppearance}>
          <button className="inline-flex min-h-9 items-center gap-2 rounded-md border border-profit/30 bg-bg-primary/80 px-3 font-mono text-sm font-semibold lowercase text-profit transition-colors hover:bg-profit/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-profit/40">
            <LogIn className="h-4 w-4" aria-hidden="true" />
            authenticate
          </button>
        </SignInButton>
      </SignedOut>

      <SignedIn>
        <UserButton
          appearance={{
            elements: {
              avatarBox: "h-9 w-9 border border-profit/30 shadow-[0_0_18px_rgba(114,242,95,0.12)]",
            },
          }}
        />
      </SignedIn>
    </div>
  );
}
