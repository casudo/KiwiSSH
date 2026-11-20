import api from "./index"
import type {
  BackupTriggerResponse,
  BackupJobStatusResponse,
  DryRunResult,
  BackupJobsResponse,
  BackupHistoryResponse,
  BackupGraphResponse,
  BackupConfigResponse,
  ConfigCompareRequest,
  ConfigCompareResponse,
} from "../types/backup"

export const backupApi = {
  async triggerAll(params?: Record<string, string>): Promise<BackupTriggerResponse> {
    const response = await api.post<BackupTriggerResponse>("/backups/trigger", params)
    return response.data
  },

  async triggerDevice(deviceName: string): Promise<BackupTriggerResponse> {
    const response = await api.post<BackupTriggerResponse>(`/backups/trigger/${deviceName}`)
    return response.data
  },

  async getJobs(
    deviceName?: string,
    status?: string,
    limit: number = 200,
    offset: number = 0,
    jobId?: string,
    includeMetadata: boolean = false,
  ): Promise<BackupJobsResponse> {
    const params: Record<string, string | number> = { limit, offset }
    if (deviceName) params.device_name = deviceName
    if (status) params.status = status
    if (jobId) params.job_id = jobId
    if (includeMetadata) params.include_metadata = true
    const response = await api.get<BackupJobsResponse>("/backups/jobs", { params })
    return response.data
  },

  async getJobStatus(jobId: string): Promise<BackupJobStatusResponse> {
    const response = await api.get<BackupJobStatusResponse>(`/backups/status/${jobId}`)
    return response.data
  },

  async startDryRun(deviceName: string): Promise<DryRunResult> {
    const response = await api.post<DryRunResult>(`/backups/dry-run/${encodeURIComponent(deviceName)}`)
    return response.data
  },

  async getDryRun(dryRunId: string): Promise<DryRunResult> {
    const response = await api.get<DryRunResult>(`/backups/dry-run/status/${dryRunId}`)
    return response.data
  },

  async getHistory(
    deviceName: string,
    limit?: number,
    offset?: number,
    range?: { since?: string; until?: string },
  ): Promise<BackupHistoryResponse> {
    const params: Record<string, string | number> = {}
    if (limit !== undefined) params.limit = limit
    if (offset !== undefined) params.offset = offset
    if (range?.since) params.since = range.since
    if (range?.until) params.until = range.until
    const response = await api.get<BackupHistoryResponse>(`/backups/history/${deviceName}`, { params })
    return response.data
  },

  async getHistoryGraph(
    deviceName: string,
    days?: number,
    tzOffsetMinutes?: number,
  ): Promise<BackupGraphResponse> {
    const params: Record<string, number> = {}
    if (days !== undefined) params.days = days
    if (tzOffsetMinutes !== undefined) params.tz_offset_minutes = tzOffsetMinutes
    const response = await api.get<BackupGraphResponse>(`/backups/history/graph/${deviceName}`, { params })
    return response.data
  },

  async getDiff(
    deviceName: string,
    fromCommit: string,
    toCommit: string
  ): Promise<Record<string, unknown>> {
    const response = await api.get(`/backups/diff/${deviceName}`, {
      params: { from_commit: fromCommit, to_commit: toCommit }
    })
    return response.data
  },

  async compare(request: ConfigCompareRequest): Promise<ConfigCompareResponse> {
    const params: Record<string, string | boolean | string[]> = {
      left_device: request.leftDevice,
      right_device: request.rightDevice,
    }
    if (request.leftCommit) params.left_commit = request.leftCommit
    if (request.rightCommit) params.right_commit = request.rightCommit
    if (request.ignore?.length) params.ignore = request.ignore
    if (request.ignoreWhitespace) params.ignore_whitespace = true
    if (request.ignorePatterns?.length) params.ignore_pattern = request.ignorePatterns
    if (request.applyStripPatterns) params.apply_strip_patterns = true
    if (request.applyRedaction) params.apply_redaction = true
    const response = await api.get<ConfigCompareResponse>("/backups/compare", {
      params,
      // Repeat the key for every list value (ignore=a&ignore=b) instead of ignore[]=a, FastAPI reads that as a list
      paramsSerializer: { indexes: null },
    })
    return response.data
  },

  async getLatestConfig(deviceName: string): Promise<Record<string, unknown>> {
    const response = await api.get(`/backups/latest/${deviceName}`)
    return response.data
  },

  async latestConfig(deviceName: string, commitHash?: string): Promise<BackupConfigResponse> {
    const params = commitHash ? { commit: commitHash } : undefined
    const response = await api.get<BackupConfigResponse>(`/backups/latest/${deviceName}`, { params })
    return response.data
  },

  async flushDatabase(): Promise<Record<string, unknown>> {
    const response = await api.delete("/backups/flush")
    return response.data
  },
}
