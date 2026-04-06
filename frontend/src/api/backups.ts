import api from "./index"
import type { BackupTriggerResponse, BackupJobStatus, BackupJobsResponse } from "../types/backup"

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
    limit: number = 5000,
    offset: number = 0,
    jobId?: string,
  ): Promise<BackupJobsResponse> {
    const params: Record<string, string | number> = { limit, offset }
    if (deviceName) params.device_name = deviceName
    if (status) params.status = status
    if (jobId) params.job_id = jobId
    const response = await api.get<BackupJobsResponse>("/backups/jobs", { params })
    return response.data
  },

  async getJobStatus(jobId: string): Promise<BackupJobStatus> {
    const response = await api.get<BackupJobStatus>(`/backups/status/${jobId}`)
    return response.data
  },

  async getHistory(deviceName: string, limit?: number): Promise<Record<string, unknown>> {
    const params = limit === undefined ? undefined : { limit }
    const response = await api.get(`/backups/history/${deviceName}`, { params })
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

  async getLatestConfig(deviceName: string): Promise<Record<string, unknown>> {
    const response = await api.get(`/backups/latest/${deviceName}`)
    return response.data
  },

  async latestConfig(deviceName: string, commitHash?: string): Promise<Record<string, unknown>> {
    const params = commitHash ? { commit: commitHash } : undefined
    const response = await api.get(`/backups/latest/${deviceName}`, { params })
    return response.data
  },

  async flushDatabase(): Promise<Record<string, unknown>> {
    const response = await api.delete("/backups/flush")
    return response.data
  },
}
