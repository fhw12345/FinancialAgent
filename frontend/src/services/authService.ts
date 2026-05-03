/**
 * Authentication service — STUB (W3c).
 *
 * The W3 sweep removed real authentication. This stub keeps the public surface
 * (`authStorage`, `User`, `refreshAccessToken`, `*` flow helpers) so existing
 * consumers compile, but every operation returns a fixed local user with a
 * placeholder "local" token. Real network calls are gone.
 */

const LOCAL_TOKEN = "local";
const LOCAL_USER: User = {
  user_id: "local",
  email: null,
  phone_number: null,
  wechat_openid: null,
  username: "local",
  is_admin: true,
  created_at: new Date(0).toISOString(),
  last_login: null,
};

export interface User {
  user_id: string;
  email: string | null;
  phone_number: string | null;
  wechat_openid: string | null;
  username: string;
  is_admin: boolean;
  created_at: string;
  last_login: string | null;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  refresh_expires_in: number;
  user: User;
}

export interface SendCodeResponse {
  message: string;
  code?: string;
}

function fakeLoginResponse(): LoginResponse {
  return {
    access_token: LOCAL_TOKEN,
    refresh_token: LOCAL_TOKEN,
    token_type: "bearer",
    expires_in: 60 * 60 * 24 * 365,
    refresh_expires_in: 60 * 60 * 24 * 365,
    user: LOCAL_USER,
  };
}

// ===== Stub auth flow functions (kept for source compatibility) =====

export async function sendVerificationCode(
  _email: string,
): Promise<SendCodeResponse> {
  return { message: "(stub) auth removed", code: undefined };
}

export async function verifyCodeAndLogin(
  _email: string,
  _code: string,
): Promise<LoginResponse> {
  return fakeLoginResponse();
}

export async function registerUser(
  _email: string,
  _code: string,
  _username: string,
  _password: string,
): Promise<LoginResponse> {
  return fakeLoginResponse();
}

export async function loginWithPassword(
  _username: string,
  _password: string,
): Promise<LoginResponse> {
  return fakeLoginResponse();
}

export async function resetPassword(
  _email: string,
  _code: string,
  _newPassword: string,
): Promise<LoginResponse> {
  return fakeLoginResponse();
}

export async function getCurrentUser(_token: string): Promise<User> {
  return LOCAL_USER;
}

export async function refreshAccessToken(
  _refreshToken: string,
): Promise<LoginResponse> {
  return fakeLoginResponse();
}

export async function logout(_refreshToken: string): Promise<void> {
  return;
}

export async function logoutAll(_accessToken: string): Promise<void> {
  return;
}

/**
 * authStorage — local-only no-op storage. Returns the fixed local user/token
 * so callers (FeedbackDetailView, PortfolioDashboard, HealthPage,
 * CronController, feedbackApi) keep working without real auth.
 */
export const authStorage = {
  getAccessToken(): string | null {
    return LOCAL_TOKEN;
  },
  setAccessToken(_token: string): void {},
  removeAccessToken(): void {},

  getRefreshToken(): string | null {
    return LOCAL_TOKEN;
  },
  setRefreshToken(_token: string): void {},
  removeRefreshToken(): void {},

  getAccessTokenExpiry(): number | null {
    return Date.now() + 60 * 60 * 1000;
  },
  setAccessTokenExpiry(_expiresIn: number): void {},
  isAccessTokenExpiringSoon(): boolean {
    return false;
  },

  getUser(): User | null {
    return LOCAL_USER;
  },
  setUser(_user: User): void {},
  removeUser(): void {},

  saveLoginResponse(_response: LoginResponse): void {},
  clear(): void {},

  // Backward-compat aliases
  getToken(): string | null {
    return LOCAL_TOKEN;
  },
  setToken(_token: string): void {},
  removeToken(): void {},
};
