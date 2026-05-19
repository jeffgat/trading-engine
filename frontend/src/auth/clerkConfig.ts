export interface OwnerAuthState {
  isLoaded: boolean;
  isSignedIn: boolean;
  isOwner: boolean;
  isUnauthorized: boolean;
}

export const CLERK_PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY?.trim() ?? "";
export const CLERK_ENABLED = CLERK_PUBLISHABLE_KEY.length > 0;
export const ALLOWED_AUTH_EMAIL = import.meta.env.VITE_ALLOWED_AUTH_EMAIL?.trim().toLowerCase() ?? "";

export const PUBLIC_AUTH_STATE: OwnerAuthState = {
  isLoaded: true,
  isSignedIn: false,
  isOwner: false,
  isUnauthorized: false,
};
