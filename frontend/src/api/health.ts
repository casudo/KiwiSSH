import api from "./index"
import type { HealthResponse, ReadinessResponse } from "@/types/health"

export const healthApi = {
  async check(): Promise<HealthResponse> {
    const response = await api.get<HealthResponse>("/health")
    return response.data
  },

  async ready(): Promise<ReadinessResponse> {
    const response = await api.get<ReadinessResponse>("/health/ready")
    return response.data
  },
}
