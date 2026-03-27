/**
 * Type definitions for Device data structures
 */

export type DeviceStatus =
  | "unknown"
  | "backup_success"
  | "backup_failed"
  | "backup_in_progress"
  | "backup_no_changes"

export interface Device {
  device_name: string
  ip_address: string
  vendor: string
  group: string
  ssh_profile: string
  enabled: boolean
  status: DeviceStatus
  last_backup: string | null
  last_backup_success: string | null
  last_error?: string | null
}

export interface DeviceGroup {
  group: string
  count: number
}
