type TokenProvider = () => Promise<string | null>;

let tokenProvider: TokenProvider | null = null;

export function setApiTokenProvider(provider: TokenProvider | null) {
  tokenProvider = provider;
}

export async function getApiAuthToken() {
  return tokenProvider ? tokenProvider() : null;
}

export function shouldAuthorizeApiUrl(url: URL) {
  return (
    url.origin === window.location.origin &&
    (url.pathname.startsWith("/exec-api") || url.pathname.startsWith("/bt-api"))
  );
}
