/**
 * Type definitions for Health/System data
 */

export interface HealthResponse {
  status: string
  timestamp: string
  version: string
  config_loaded: boolean
}

export interface ReadinessResponse {
  ready: boolean
  checks: Record<string, boolean>
}
