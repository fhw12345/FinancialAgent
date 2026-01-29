/**
 * Authentication service for email-based login.
 * Handles verification code sending, verification, and JWT token management.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || "";

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
  code?: string; // Only in dev mode
}

/**
 * Send verification code to email
 */
export async function sendVerificationCode(
  email: string,
): Promise<SendCodeResponse> {
  const response = await fetch(`${API_BASE_URL}/api/auth/send-code`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      auth_type: "email",
      identifier: email,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to send verification code");
  }

  return response.json();
}

/**
 * Verify code and login
 */
export async function verifyCodeAndLogin(
  email: string,
  code: string,
): Promise<LoginResponse> {
  const response = await fetch(`${API_BASE_URL}/api/auth/verify-code`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      auth_type: "email",
      identifier: email,
      code: code,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Failed to verify code");
  }

  return response.json();
}

/**
 * Register a new user with email verification
 */
export async function registerUser(
  email: string,
  code: string,
  username: string,
  password: string,
): Promise<LoginResponse> {
  const response = await fetch(`${API_BASE_URL}/api/auth/register`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      email,
      code,
      username,
      password,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Registration failed");
  }

  return response.json();
}

/**
 * Login with username and password
 */
export async function loginWithPassword(
  username: string,
  password: string,
): Promise<LoginResponse> {
  const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      username,
      password,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Login failed");
  }

  return response.json();
}

/**
 * Reset password using email verification
 */
export async function resetPassword(
  email: string,
  code: string,
  newPassword: string,
): Promise<LoginResponse> {
  const response = await fetch(`${API_BASE_URL}/api/auth/reset-password`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      email,
      code,
      new_password: newPassword,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Password reset failed");
  }

  return response.json();
}

/**
 * Get current user from token
 */
export async function getCurrentUser(token: string): Promise<User> {
  const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error("Invalid or expired token");
  }

  return response.json();
}

/**
 * Refresh access token using refresh token
 */
export async function refreshAccessToken(
  refreshToken: string,
): Promise<LoginResponse> {
  const response = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      refresh_token: refreshToken,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Token refresh failed");
  }

  return response.json();
}

/**
 * Logout by revoking refresh token
 */
export async function logout(refreshToken: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/auth/logout`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      refresh_token: refreshToken,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Logout failed");
  }
}

/**
 * Logout from all devices
 */
export async function logoutAll(accessToken: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/auth/logout-all`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || "Logout all failed");
  }
}

/**
 * Auth token storage in localStorage with dual-token support
 */
export const authStorage = {
  // Access token (short-lived, 30 min)
  getAccessToken(): string | null {
    return localStorage.getItem("access_token");
  },

  setAccessToken(token: string): void {
    localStorage.setItem("access_token", token);
  },

  removeAccessToken(): void {
    localStorage.removeItem("access_token");
  },

  // Refresh token (long-lived, 7 days)
  getRefreshToken(): string | null {
    return localStorage.getItem("refresh_token");
  },

  setRefreshToken(token: string): void {
    localStorage.setItem("refresh_token", token);
  },

  removeRefreshToken(): void {
    localStorage.removeItem("refresh_token");
  },

  // Token expiration tracking
  getAccessTokenExpiry(): number | null {
    const expiry = localStorage.getItem("access_token_expiry");
    return expiry ? parseInt(expiry, 10) : null;
  },

  setAccessTokenExpiry(expiresIn: number): void {
    const expiryTime = Date.now() + expiresIn * 1000;
    localStorage.setItem("access_token_expiry", expiryTime.toString());
  },

  isAccessTokenExpiringSoon(): boolean {
    const expiry = this.getAccessTokenExpiry();
    if (!expiry) return true;
    // Consider token expiring if less than 5 minutes remaining
    return Date.now() > expiry - 5 * 60 * 1000;
  },

  // User data
  getUser(): User | null {
    const userStr = localStorage.getItem("auth_user");
    if (!userStr) return null;
    try {
      return JSON.parse(userStr);
    } catch {
      localStorage.removeItem("auth_user");
      return null;
    }
  },

  setUser(user: User): void {
    localStorage.setItem("auth_user", JSON.stringify(user));
  },

  removeUser(): void {
    localStorage.removeItem("auth_user");
  },

  // Store full login response
  saveLoginResponse(response: LoginResponse): void {
    this.setAccessToken(response.access_token);
    this.setRefreshToken(response.refresh_token);
    this.setAccessTokenExpiry(response.expires_in);
    this.setUser(response.user);
  },

  // Clear all auth data
  clear(): void {
    this.removeAccessToken();
    this.removeRefreshToken();
    localStorage.removeItem("access_token_expiry");
    this.removeUser();
  },

  // Backward compatibility (for old code using "auth_token")
  getToken(): string | null {
    return this.getAccessToken();
  },

  setToken(token: string): void {
    this.setAccessToken(token);
  },

  removeToken(): void {
    this.removeAccessToken();
  },
};
