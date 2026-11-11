import api from "./index"
import type { HealthResponse } from "@/types/health"

export const healthApi = {
  async check(): Promise<HealthResponse> {
    // Allow response code 200 (healthy) and 503 (unhealthy)
    const response = await api.get<HealthResponse>("/health", {
      validateStatus: (status) => status === 200 || status === 503,
    })
    return response.data
  },
}
