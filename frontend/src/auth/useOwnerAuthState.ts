import { useUser } from "@clerk/clerk-react";
import { ALLOWED_AUTH_EMAIL, type OwnerAuthState } from "@/auth/clerkConfig";

export function useOwnerAuthState(): OwnerAuthState {
  const { isLoaded, isSignedIn, user } = useUser();
  const emailAddresses = user?.emailAddresses.map((email) => email.emailAddress.toLowerCase()) ?? [];
  const hasAllowlistedEmail = ALLOWED_AUTH_EMAIL.length > 0 && emailAddresses.includes(ALLOWED_AUTH_EMAIL);

  return {
    isLoaded,
    isSignedIn: isSignedIn === true,
    isOwner: isLoaded && isSignedIn === true && hasAllowlistedEmail,
    isUnauthorized: isLoaded && isSignedIn === true && ALLOWED_AUTH_EMAIL.length > 0 && !hasAllowlistedEmail,
  };
}
