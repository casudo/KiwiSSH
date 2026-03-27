import { defineStore } from "pinia"
import { ref } from "vue"
import { healthApi } from "@/api/health"
import type { HealthResponse, ReadinessResponse } from "@/types/health"

export const useAppStore = defineStore("app", () => {
  // State
  const health = ref<HealthResponse | null>(null)
  const ready = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // Actions
  async function checkHealth() {
    loading.value = true
    error.value = null

    try {
      health.value = await healthApi.check()
    } catch (e: unknown) {
      const errMsg = e instanceof Error ? e.message : "Failed to check health"
      error.value = errMsg
      throw e
    } finally {
      loading.value = false
    }
  }

  async function checkReady(): Promise<ReadinessResponse> {
    try {
      const response = await healthApi.ready()
      ready.value = response.ready
      return response
    } catch (e) {
      ready.value = false
      return { ready: false, checks: {} }
    }
  }

  function clearError() {
    error.value = null
  }

  return {
    // State
    health,
    ready,
    loading,
    error,
    // Actions
    checkHealth,
    checkReady,
    clearError,
  }
})
