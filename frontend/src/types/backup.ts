/**
 * Type definitions for Backup data structures
 */

export type BackupStatus = "pending" | "in_progress" | "success" | "failed" | "no_changes"

export interface BackupRecord {
  id: string
  device_name: string
  timestamp: string
  status: BackupStatus
  git_commit?: string | null
  error_message?: string | null
  config_size_bytes?: number | null
}

export interface BackupDiff {
  device_name: string
  from_commit: string
  to_commit: string
  from_timestamp?: string | null
  to_timestamp?: string | null
  diff_content: string
  lines_added: number
  lines_removed: number
}

export interface BackupTriggerRequest {
  group?: string | null
}

export interface BackupTriggerResponse {
  message: string
  devices_queued: string[]
  job_id?: string | null
}

export interface BackupJobStatus {
  job_id: string
  device_name: string
  group: string
  status: string
  timestamp: number
  message: string
}

export interface BackupJobRecord {
  job_id: string
  device_name: string
  group: string
  status: string
  timestamp: string
  error_message?: string | null
  config_size_bytes?: number | null
}

export interface BackupJobsResponse {
  count: number
  total_count: number
  limit: number
  offset: number
  status_totals?: {
    pending: number
    in_progress: number
    success: number
    failed: number
    no_changes: number
  }
  error?: string
  jobs: BackupJobRecord[]
}
