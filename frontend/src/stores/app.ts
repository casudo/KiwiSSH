import { defineStore } from "pinia"
import { ref } from "vue"
import { healthApi } from "@/api/health"
import type { HealthResponse, ReadinessResponse } from "@/types/health"
import { APP_VERSION } from "@/main"

const GITHUB_RELEASES_URL = "https://api.github.com/repos/casudo/KiwiSSH/releases/latest"
const DISMISSED_KEY = "kiwissh-dismissed-update"

export const useAppStore = defineStore("app", () => {
  // State
  const health = ref<HealthResponse | null>(null)
  const ready = ref(false)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const latestVersion = ref<string | null>(null)
  const updateAvailable = ref(false)
  const updateDismissed = ref(false)

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

  async function checkForUpdates(): Promise<void> {
    try {
      // Fetch latest release
      const response = await fetch(GITHUB_RELEASES_URL, {
        headers: { Accept: "application/vnd.github+json" },
      })
      if (!response.ok) return

      const data = await response.json() as { tag_name?: string }
      const tag = data.tag_name
      if (!tag) return
      // GitHub tags include a leading "v" (e.g. "v2.3.0"), strip it before comparing
      const remote = tag.replace(/^v/, "")
      latestVersion.value = remote
      updateAvailable.value = remote !== APP_VERSION
      // Suppress banner only when the user already dismissed this exact version
      updateDismissed.value = localStorage.getItem(DISMISSED_KEY) === remote
    } catch {
      // Silently ignore – update checks are best-effort
    }
  }

  function dismissUpdate() {
    if (latestVersion.value) {
      localStorage.setItem(DISMISSED_KEY, latestVersion.value)
    }
    updateDismissed.value = true
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
    latestVersion,
    updateAvailable,
    updateDismissed,
    // Actions
    checkHealth,
    checkReady,
    checkForUpdates,
    dismissUpdate,
    clearError,
  }
})
