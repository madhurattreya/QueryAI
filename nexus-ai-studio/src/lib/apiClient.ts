/**
 * nexus-ai-studio/src/lib/apiClient.ts
 * ───────────────────────────────────────
 * Centralized API client for QueryIQ.
 * Eliminates hardcoded endpoint URLs by reading NEXT_PUBLIC_API_URL.
 * Provides custom HTTP error classification mapping backend errors to user-friendly messages.
 */

export type ErrorCode =
  | "NETWORK_OFFLINE"
  | "BACKEND_UNREACHABLE"
  | "HTTP_400"
  | "HTTP_401"
  | "HTTP_403"
  | "HTTP_404"
  | "HTTP_500"
  | "HTTP_503"
  | "DATASET_NOT_LOADED"
  | "COLUMN_NOT_FOUND"
  | "SQL_GENERATION_FAILED"
  | "PANDAS_EXECUTION_FAILED"
  | "LLM_TIMEOUT"
  | "LLM_UNAVAILABLE"
  | "VALIDATION_FAILED"
  | "SANDBOX_TIMEOUT"
  | "STREAM_PARSE_ERROR"
  | "UNKNOWN_ERROR";

export interface ErrorPayload {
  code: ErrorCode;
  userMessage: string;
  technicalDetail?: string;
  isRetryable: boolean;
}

let cachedBaseUrl: string | null = null;

export function getBaseUrl(): string {
  if (cachedBaseUrl) return cachedBaseUrl;
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  if (typeof window !== "undefined" && window.location.hostname) {
    return `http://${window.location.hostname}:8000`;
  }
  return "http://127.0.0.1:8000";
}

export class ApiClient {
  /**
   * Helper to build full URL with base path.
   */
  static getUrl(path: string): string {
    const cleanPath = path.startsWith("/") ? path : `/${path}`;
    return `${getBaseUrl()}${cleanPath}`;
  }

  static getToken(): string | null {
    if (typeof window !== "undefined") {
      return localStorage.getItem("queryiq_token") || localStorage.getItem("token");
    }
    return null;
  }

  static getHeaders(customHeaders: Record<string, string> = {}): Record<string, string> {
    const token = this.getToken();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...customHeaders,
    };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    return headers;
  }

  /**
   * Safe fetch wrapper with global error handling and auto 127.0.0.1 <-> localhost fallback.
   */
  static async request(path: string, options: RequestInit = {}): Promise<Response> {
    if (typeof navigator !== "undefined" && !navigator.onLine) {
      throw new Error("NETWORK_OFFLINE");
    }

    const primaryUrl = this.getUrl(path);
    const headers = this.getHeaders(options.headers as Record<string, string>);

    try {
      const response = await fetch(primaryUrl, {
        ...options,
        headers,
      });

      if (!response.ok) {
        // Try reading error payload from backend JSONResponse
        try {
          const errData = await response.json();
          if (errData && errData.error_code) {
            throw new Error(JSON.stringify(errData));
          }
        } catch (e) {
          if (e instanceof Error && e.message.startsWith("{")) throw e;
        }
        throw new Error(`HTTP_STATUS_${response.status}`);
      }

      return response;
    } catch (err: any) {
      if (err.message === "NETWORK_OFFLINE" || (typeof err.message === "string" && (err.message.startsWith("{") || err.message.startsWith("HTTP_STATUS_")))) {
        throw err;
      }

      // If connection failed (e.g. Failed to fetch), attempt fallback between 127.0.0.1 and localhost
      if (err.message.includes("Failed to fetch") || err.message.includes("TypeError") || err.name === "TypeError") {
        const fallbackUrl = primaryUrl.includes("127.0.0.1")
          ? primaryUrl.replace("127.0.0.1", "localhost")
          : primaryUrl.includes("localhost")
          ? primaryUrl.replace("localhost", "127.0.0.1")
          : null;

        if (fallbackUrl) {
          try {
            const fallbackResponse = await fetch(fallbackUrl, {
              ...options,
              headers,
            });

            if (fallbackResponse.ok) {
              if (fallbackUrl.includes("localhost")) {
                cachedBaseUrl = "http://localhost:8000";
              } else if (fallbackUrl.includes("127.0.0.1")) {
                cachedBaseUrl = "http://127.0.0.1:8000";
              }
              return fallbackResponse;
            }
          } catch (fallbackErr) {
            // Both endpoints failed
          }
        }

        throw new Error("BACKEND_UNREACHABLE");
      }
      throw err;
    }
  }

  /**
   * Maps raw javascript exceptions to detailed structured ErrorPayloads.
   */
  static classifyError(error: any): ErrorPayload {
    const msg = error?.message || String(error);

    // 1. Check network status
    if (msg === "NETWORK_OFFLINE") {
      return {
        code: "NETWORK_OFFLINE",
        userMessage: "You are offline. Please check your internet connection and try again.",
        isRetryable: true,
      };
    }
    if (msg === "BACKEND_UNREACHABLE") {
      return {
        code: "BACKEND_UNREACHABLE",
        userMessage: "Cannot connect to the backend server. Please verify the backend is running on port 8000.",
        technicalDetail: `Connection failed to base url: ${BASE_URL}`,
        isRetryable: true,
      };
    }

    // 2. Check structured backend exception JSONResponse
    if (msg.startsWith("{") && msg.endsWith("}")) {
      try {
        const data = JSON.parse(msg);
        if (data.error_code) {
          const code = data.error_code as ErrorCode;
          let userMsg = data.message || "An error occurred on the server.";
          
          if (code === "LLM_TIMEOUT") {
            userMsg = "The AI model took too long to respond. Please try again or switch to a faster model.";
          } else if (code === "LLM_UNAVAILABLE") {
            userMsg = "The LLM service is currently offline or unreachable. Please verify Ollama is running.";
          }

          return {
            code,
            userMessage: userMsg,
            technicalDetail: data.detail || undefined,
            isRetryable: code === "LLM_TIMEOUT" || code === "LLM_UNAVAILABLE",
          };
        }
      } catch (e) {}
    }

    // 3. Fallback standard HTTP status codes
    if (msg.startsWith("HTTP_STATUS_")) {
      const status = msg.replace("HTTP_STATUS_", "");
      if (status === "404") {
        return {
          code: "HTTP_404",
          userMessage: "The requested resource was not found on the server.",
          isRetryable: false,
        };
      }
      if (status === "503") {
        return {
          code: "HTTP_503",
          userMessage: "The backend server is temporarily overloaded or down for maintenance.",
          isRetryable: true,
        };
      }
      if (status.startsWith("5")) {
        return {
          code: "HTTP_500",
          userMessage: "An internal server error occurred while processing your request.",
          isRetryable: false,
        };
      }
      return {
        code: `HTTP_${status}` as ErrorCode,
        userMessage: `Server returned an HTTP error status code: ${status}`,
        isRetryable: false,
      };
    }

    // 4. Default generic fallback
    return {
      code: "UNKNOWN_ERROR",
      userMessage: "An unexpected error occurred during execution. Please try again.",
      technicalDetail: msg,
      isRetryable: false,
    };
  }
}
