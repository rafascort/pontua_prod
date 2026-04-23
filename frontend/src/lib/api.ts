// frontend/src/lib/api.ts
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

class ApiClient {
  private getToken(): string | null {
    return localStorage.getItem("access_token");
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const token = this.getToken();
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    };

    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    // Only set Content-Type for non-FormData requests
    if (!(options.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers,
    });

    if (response.status === 401) {
      localStorage.removeItem("access_token");
      window.location.href = "/login";
      throw new Error("Sessão expirada. Faça login novamente.");
    }

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ msg: "Erro desconhecido" }));
      throw new Error(errorData.msg || `Erro ${response.status}`);
    }

    // Handle file downloads
    const contentType = response.headers.get("content-type");
    if (contentType && !contentType.includes("application/json")) {
      return response.blob() as unknown as T;
    }

    return response.json();
  }

  // Auth
  async login(email: string, password: string): Promise<{ access_token: string }> {
    const data = await this.request<{ access_token: string }>("/api/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    localStorage.setItem("access_token", data.access_token);
    return data;
  }

  async register(
    email: string,
    password: string,
    refCode?: string | null,
    name?: string,
  ): Promise<{ msg: string }> {
    return this.request("/api/register", {
      method: "POST",
      body: JSON.stringify({
        email,
        password,
        ...(name ? { name } : {}),
        ...(refCode ? { ref_code: refCode } : {}),
      }),
    });
  }

  // User
  async getUserDetails(): Promise<{
    id: number;
    email: string;
    role: string;
    is_active: boolean;
    page_count: number;
    plan_status: string;
    stripe_customer_id: string | null;
    referral_code: string | null;
    discount_credits: number;
  }> {
    return this.request("/api/user/me");
  }

  // Processing
  async processDirectPDF(file: File, pages: string): Promise<{ task_id: string }> {
    const formData = new FormData();
    formData.append("pdf_file", file);
    formData.append("pages", pages);
    return this.request("/api/process-direct", {
      method: "POST",
      body: formData,
    });
  }

  async downloadResult(taskId: string): Promise<Blob> {
    return this.request<Blob>(`/api/download/${taskId}`);
  }

  // Stripe checkout
  async createCheckoutSession(priceId: string): Promise<{ url: string }> {
    return this.request("/api/create-checkout-session", {
      method: "POST",
      body: JSON.stringify({ priceId }),
    });
  }

  // Admin
  async getAdminUsers(): Promise<Array<{
    id: number;
    email: string;
    role: string;
    is_active: boolean;
    page_count: number;
    plan_status: string;
  }>> {
    return this.request("/api/admin/users");
  }

  async updateUser(userId: number, data: Record<string, unknown>): Promise<{ msg: string }> {
    return this.request(`/api/admin/users/${userId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  logout() {
    localStorage.removeItem("access_token");
    window.location.href = "/login";
  }

  isAuthenticated(): boolean {
    return !!this.getToken();
  }
}

export const api = new ApiClient();
