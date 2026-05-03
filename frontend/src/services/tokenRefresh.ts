/**
 * Token refresh interceptor — STUB (W3c).
 *
 * Auth was removed in W3. These helpers retain their original signatures so
 * `services/api.ts` interceptors keep compiling, but no refresh ever happens
 * and no Authorization header is added.
 */

import type { InternalAxiosRequestConfig } from "axios";

export async function performTokenRefresh(): Promise<string | null> {
  return null;
}

export async function refreshTokenIfNeeded(
  config: InternalAxiosRequestConfig,
): Promise<InternalAxiosRequestConfig> {
  return config;
}

export async function retryWithRefreshToken(): Promise<string | null> {
  return null;
}
