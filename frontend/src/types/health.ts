/**
 * Type definitions for Health/System data
 */

export interface HealthResponse {
  status: "healthy" | "unhealthy"
  timestamp: string
  version: string
  checks: Record<string, boolean>
}
