import { useAuth } from "@clerk/clerk-react";
import { useEffect, type ReactNode } from "react";
import { setApiTokenProvider, shouldAuthorizeApiUrl } from "@/auth/apiAuth";

function resolveFetchUrl(input: RequestInfo | URL) {
  if (typeof input === "string") return new URL(input, window.location.origin);
  if (input instanceof URL) return input;
  return new URL(input.url, window.location.origin);
}

export function AuthenticatedApiBridge({ children }: { children: ReactNode }) {
  const { getToken } = useAuth();

  useEffect(() => {
    setApiTokenProvider(() => getToken());

    const originalFetch = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      const url = resolveFetchUrl(input);
      if (!shouldAuthorizeApiUrl(url)) {
        return originalFetch(input, init);
      }

      const token = await getToken();
      if (!token) {
        return originalFetch(input, init);
      }

      const headers = new Headers(
        init?.headers ?? (input instanceof Request ? input.headers : undefined),
      );
      headers.set("Authorization", `Bearer ${token}`);

      return originalFetch(input, { ...init, headers });
    };

    return () => {
      setApiTokenProvider(null);
      window.fetch = originalFetch;
    };
  }, [getToken]);

  return children;
}
