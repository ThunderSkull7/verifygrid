/**
 * API client module for VerifyGrid
 * Centralizes request handling, token injection, error extraction, and endpoint calls.
 */

import type {
  DiscrepancyListResponse,
  FileProfileSummary,
  MultiSourceKeyRecommendRequest,
  MultiSourceKeyRecommendResponse,
  MultiSourceVerificationRequest,
  MultiSourceVerificationResponse,
  PreprocessingConfig,
  PreprocessingResult,
  Project,
  ProjectCreate,
  QuarantineListResponse,
  QuarantineResolutionRequest,
  QuarantineResolutionResponse,
  RulePreviewRequest,
  RulePreviewResponse,
  RuleValidateRequest,
  RuleValidateResponse,
  SourceFile,
  TemplateApplyRequest,
  TemplateApplyResponse,
  TemplateConfigurationV1,
  TokenResponse,
  User,
  VerificationRequest,
  VerificationResponse,
  VerificationRun,
  VerificationRunListResponse,
  VerificationTemplate,
} from '../types';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

class ApiClient {
  private token: string | null = null;

  constructor() {
    this.token = localStorage.getItem('verifygrid_token');
  }

  public setToken(token: string | null) {
    this.token = token;
    if (token) {
      localStorage.setItem('verifygrid_token', token);
    } else {
      localStorage.removeItem('verifygrid_token');
    }
  }

  public getToken(): string | null {
    return this.token;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${BASE_URL}${endpoint}`;
    const headers = new Headers(options.headers || {});

    if (this.token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${this.token}`);
    }

    if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
      headers.set('Content-Type', 'application/json');
    }

    const config: RequestInit = {
      ...options,
      headers,
    };

    let response: Response;
    try {
      response = await fetch(url, config);
    } catch (err: any) {
      throw new Error(`Network error connecting to VerifyGrid API: ${err.message || err}`);
    }

    if (response.status === 401) {
      // Token expired or invalid
      this.setToken(null);
      window.dispatchEvent(new CustomEvent('auth:unauthorized'));
    }

    if (!response.ok) {
      let errorMessage = `HTTP ${response.status} ${response.statusText}`;
      let errorDetail: unknown = null;
      try {
        const errorJson = await response.json();
        errorDetail = errorJson?.detail ?? null;
        if (errorJson.detail) {
          if (typeof errorJson.detail === 'string') {
            errorMessage = errorJson.detail;
          } else if (Array.isArray(errorJson.detail)) {
            // FastAPI pydantic validation errors
            errorMessage = errorJson.detail
              .map((d: any) => `${d.loc?.join('.')} : ${d.msg}`)
              .join(', ');
          } else if (typeof errorJson.detail === 'object') {
            // Structured backend detail (e.g. template apply validation report)
            errorMessage = errorJson.detail.message || JSON.stringify(errorJson.detail);
          }
        }
      } catch {
        // Response was not JSON
      }
      const err = new Error(errorMessage) as Error & { detail?: unknown };
      err.detail = errorDetail;
      throw err;
    }

    // Check for empty body / 204
    if (response.status === 204) {
      return {} as T;
    }

    return response.json();
  }

  // --- Auth Endpoints ---
  async register(payload: { email: string; password: string; full_name?: string }): Promise<TokenResponse> {
    const res = await this.request<TokenResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    this.setToken(res.access_token);
    return res;
  }

  async login(payload: { email: string; password: string }): Promise<TokenResponse> {
    const res = await this.request<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    this.setToken(res.access_token);
    return res;
  }

  async getMe(): Promise<User> {
    return this.request<User>('/auth/me');
  }

  // --- Health Endpoints ---
  async checkHealth(): Promise<{ status: string; service: string }> {
    return this.request<{ status: string; service: string }>('/health');
  }

  async checkDbHealth(): Promise<{ status: string; database: string }> {
    return this.request<{ status: string; database: string }>('/health/db');
  }

  // --- Projects Endpoints ---
  async listProjects(skip = 0, limit = 100): Promise<Project[]> {
    return this.request<Project[]>(`/projects?skip=${skip}&limit=${limit}`);
  }

  async createProject(payload: ProjectCreate): Promise<Project> {
    return this.request<Project>('/projects', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // --- File Uploads ---
  async uploadSourceFile(projectId: string, file: File): Promise<SourceFile> {
    const formData = new FormData();
    formData.append('file', file);

    return this.request<SourceFile>(`/projects/${projectId}/files`, {
      method: 'POST',
      body: formData,
    });
  }

  // --- Preprocessing & Profiling Endpoints ---
  async preprocessFile(
    projectId: string,
    fileId: string,
    config?: PreprocessingConfig
  ): Promise<PreprocessingResult> {
    return this.request<PreprocessingResult>(
      `/projects/${projectId}/files/${fileId}/preprocess`,
      {
        method: 'POST',
        body: config ? JSON.stringify(config) : JSON.stringify({}),
      }
    );
  }

  async getFileProfile(
    projectId: string,
    fileId: string,
    worksheet?: string | null
  ): Promise<FileProfileSummary> {
    const ws = worksheet ? `?worksheet=${encodeURIComponent(worksheet)}` : '';
    return this.request<FileProfileSummary>(
      `/projects/${projectId}/files/${fileId}/profile${ws}`
    );
  }

  async getFileQuarantine(
    projectId: string,
    fileId: string,
    worksheet?: string | null
  ): Promise<QuarantineListResponse> {
    const ws = worksheet ? `?worksheet=${encodeURIComponent(worksheet)}` : '';
    return this.request<QuarantineListResponse>(
      `/projects/${projectId}/files/${fileId}/quarantine${ws}`
    );
  }

  async resolveQuarantine(
    projectId: string,
    fileId: string,
    payload: QuarantineResolutionRequest,
    worksheet?: string | null
  ): Promise<QuarantineResolutionResponse> {
    const ws = worksheet ? `?worksheet=${encodeURIComponent(worksheet)}` : '';
    return this.request<QuarantineResolutionResponse>(
      `/projects/${projectId}/files/${fileId}/quarantine/resolve${ws}`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  }

  // --- Template Endpoints (Batch 11, personal-only) ---
  async listTemplates(mode?: 'organization'): Promise<VerificationTemplate[]> {
    const q = mode ? `?mode=${encodeURIComponent(mode)}` : '';
    return this.request<VerificationTemplate[]>(`/templates${q}`);
  }

  async createTemplate(payload: {
    name: string;
    description?: string | null;
    mode: 'organization';
    visibility?: 'personal';
    configuration: TemplateConfigurationV1;
  }): Promise<VerificationTemplate> {
    return this.request<VerificationTemplate>('/templates', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async getTemplate(templateId: string): Promise<VerificationTemplate> {
    return this.request<VerificationTemplate>(`/templates/${templateId}`);
  }

  async updateTemplate(
    templateId: string,
    payload: { name?: string; description?: string | null; visibility?: 'personal'; configuration?: TemplateConfigurationV1 }
  ): Promise<VerificationTemplate> {
    return this.request<VerificationTemplate>(`/templates/${templateId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  }

  async deleteTemplate(templateId: string): Promise<void> {
    await this.request<void>(`/templates/${templateId}`, { method: 'DELETE' });
  }

  async applyTemplate(
    templateId: string,
    payload: TemplateApplyRequest
  ): Promise<TemplateApplyResponse> {
    return this.request<TemplateApplyResponse>(`/templates/${templateId}/apply`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // --- Verification Endpoints ---
  async verifyProjectFiles(
    projectId: string,
    payload: VerificationRequest
  ): Promise<VerificationResponse> {
    return this.request<VerificationResponse>(`/projects/${projectId}/verify`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async createVerificationRun(
    projectId: string,
    payload: VerificationRequest
  ): Promise<VerificationRun> {
    return this.request<VerificationRun>(`/projects/${projectId}/runs`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // --- Multi-Source Endpoints ---
  async recommendCandidateKeys(
    projectId: string,
    payload: MultiSourceKeyRecommendRequest
  ): Promise<MultiSourceKeyRecommendResponse> {
    return this.request<MultiSourceKeyRecommendResponse>(
      `/projects/${projectId}/keys/recommend`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  }

  async verifyMultiSourceFiles(
    projectId: string,
    payload: MultiSourceVerificationRequest
  ): Promise<MultiSourceVerificationResponse> {
    return this.request<MultiSourceVerificationResponse>(
      `/projects/${projectId}/verify/multi-source`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  }

  async createMultiSourceVerificationRun(
    projectId: string,
    payload: MultiSourceVerificationRequest
  ): Promise<VerificationRun> {
    return this.request<VerificationRun>(
      `/projects/${projectId}/runs/multi-source`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  }

  // --- Batch 4: Rule Engine & Aggregation Endpoints ---
  async validateRules(
    projectId: string,
    payload: RuleValidateRequest
  ): Promise<RuleValidateResponse> {
    return this.request<RuleValidateResponse>(
      `/projects/${projectId}/rules/validate`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  }

  async previewRules(
    projectId: string,
    payload: RulePreviewRequest
  ): Promise<RulePreviewResponse> {
    return this.request<RulePreviewResponse>(
      `/projects/${projectId}/rules/preview`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      }
    );
  }

  async listVerificationRuns(
    projectId: string,
    skip = 0,
    limit = 20,
    statusFilter?: string
  ): Promise<VerificationRunListResponse> {
    let url = `/projects/${projectId}/runs?skip=${skip}&limit=${limit}`;
    if (statusFilter) {
      url += `&status=${encodeURIComponent(statusFilter)}`;
    }
    return this.request<VerificationRunListResponse>(url);
  }

  async getVerificationRun(
    projectId: string,
    runId: string
  ): Promise<VerificationRun> {
    return this.request<VerificationRun>(`/projects/${projectId}/runs/${runId}`);
  }

  async listRunDiscrepancies(
    projectId: string,
    runId: string,
    options: {
      skip?: number;
      limit?: number;
      discrepancy_category?: string;
      match_status?: string;
      sort_by?: string;
      sort_order?: 'asc' | 'desc';
    } = {}
  ): Promise<DiscrepancyListResponse> {
    const params = new URLSearchParams();
    if (options.skip !== undefined) params.set('skip', String(options.skip));
    if (options.limit !== undefined) params.set('limit', String(options.limit));
    if (options.discrepancy_category) params.set('discrepancy_category', options.discrepancy_category);
    if (options.match_status) params.set('match_status', options.match_status);
    if (options.sort_by) params.set('sort_by', options.sort_by);
    if (options.sort_order) params.set('sort_order', options.sort_order);

    return this.request<DiscrepancyListResponse>(
      `/projects/${projectId}/runs/${runId}/results?${params.toString()}`
    );
  }

  async getRunSummary(
    projectId: string,
    runId: string
  ): Promise<Record<string, any>> {
    return this.request<Record<string, any>>(
      `/projects/${projectId}/runs/${runId}/summary`
    );
  }

  // --- Export Endpoints ---
  getExportUrl(
    projectId: string,
    runId: string,
    format: 'csv' | 'json' | 'xlsx' = 'csv',
    discrepancyCategory?: string,
    matchStatus?: string
  ): string {
    const params = new URLSearchParams({ format });
    if (discrepancyCategory) params.set('discrepancy_category', discrepancyCategory);
    if (matchStatus) params.set('match_status', matchStatus);
    return `${BASE_URL}/projects/${projectId}/runs/${runId}/export?${params.toString()}`;
  }

  async downloadExport(
    projectId: string,
    runId: string,
    format: 'csv' | 'json' | 'xlsx' = 'csv',
    discrepancyCategory?: string,
    matchStatus?: string
  ): Promise<void> {
    const url = this.getExportUrl(projectId, runId, format, discrepancyCategory, matchStatus);
    const headers: Record<string, string> = {};
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const response = await fetch(url, { headers });
    if (!response.ok) {
      throw new Error(`Failed to download report: HTTP ${response.status}`);
    }

    const blob = await response.blob();
    const disposition = response.headers.get('Content-Disposition');
    let filename = `verification_report_${runId}.${format}`;
    if (disposition && disposition.includes('filename=')) {
      const match = disposition.match(/filename="?([^"]+)"?/);
      if (match && match[1]) {
        filename = match[1];
      }
    }

    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(downloadUrl);
    a.remove();
  }
}

export const api = new ApiClient();
