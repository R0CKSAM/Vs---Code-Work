import { createAuthClient } from "better-auth/client";
import { twoFactorClient, adminClient } from "better-auth/client/plugins";

export const authClient = createAuthClient({
  baseURL: window.location.origin,
  plugins: [
    twoFactorClient({
      twoFactorPage: "/mfa/verify",
    }),
    adminClient(),
  ],
});

export const {
  signIn,
  signOut,
  signUp,
  useSession,
  getSession,
  twoFactor,
} = authClient;
