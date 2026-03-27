import { defineStore } from "pinia"
import { ref, computed } from "vue"
import { backupApi } from "@/api/backups"
import type { BackupJobStatus } from "@/types/backup"

export const useJobsStore = defineStore("jobs", () => {
  // State
  const jobs = ref<BackupJobStatus[]>([])
  const selectedJob = ref<BackupJobStatus | null>(null)
  const autoRefreshEnabled = ref(false)
  const autoRefreshInterval = ref(3000) // Default 3 seconds
  const loading = ref(false)
  const error = ref<string | null>(null)

  let refreshTimer: ReturnType<typeof setInterval> | null = null

  // Getters
  const inProgressJobs = computed(() =>
    jobs.value.filter(j => j.status === "pending" || j.status === "in_progress")
  )

  const completedJobs = computed(() =>
    jobs.value.filter(j => j.status === "success" || j.status === "failed" || j.status === "no_changes")
  )

  const successCount = computed(() =>
    jobs.value.filter(j => j.status === "success").length
  )

  const failureCount = computed(() =>
    jobs.value.filter(j => j.status === "failed").length
  )

  // Helper function to format job messages
  function getJobMessage(status: string, deviceName: string): string {
    switch (status) {
      case "success":
        return `Successful backup for ${deviceName}`
      case "no_changes":
        return `No configuration changes for ${deviceName}`
      case "failed":
        return `Failed backup for ${deviceName}`
      default:
        return `Backup for ${deviceName}`
    }
  }

  // Actions
  async function loadJobs(deviceName?: string, status?: string, limit: number = 50) {
    loading.value = true
    error.value = null

    try {
      const response = await backupApi.getJobs(deviceName, status, limit)
      const rawJobs = response.jobs || []

      // Convert database records to BackupJobStatus format
      jobs.value = rawJobs.map((job: any) => ({
        job_id: job.job_id,
        device_name: job.device_name,
        group: job.group,
        status: job.status, // "success", "failed", or "no_changes"
        timestamp: new Date(job.timestamp).getTime(),
        message: job.error_message || getJobMessage(job.status, job.device_name),
      }))
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Failed to load jobs"
      console.error("Error loading jobs:", e)
    } finally {
      loading.value = false
    }
  }

  async function refreshAllJobs() {
    if (jobs.value.length === 0) await loadJobs()

    loading.value = true
    error.value = null

    try {
      for (const job of jobs.value) {
        if (job.status === "pending" || job.status === "in_progress") {
          try {
            const status = await backupApi.getJobStatus(job.job_id)
            const index = jobs.value.findIndex(j => j.job_id === job.job_id)
            if (index !== -1) {
              jobs.value[index] = { ...jobs.value[index], ...status }
            }
          } catch (e) {
            console.error(`Failed to refresh job ${job.job_id}:`, e)
          }
        }
      }
    } finally {
      loading.value = false
    }
  }

  function addJob(job: BackupJobStatus) {
    // Check if job already exists
    const existing = jobs.value.findIndex(j => j.job_id === job.job_id)
    if (existing !== -1) {
      jobs.value[existing] = job
    } else {
      jobs.value.unshift(job) // Add to beginning (newest first)
    }

    // Keep max 100 jobs
    if (jobs.value.length > 100) {
      jobs.value.pop()
    }
  }

  function updateJob(jobId: string, update: Partial<BackupJobStatus>) {
    const index = jobs.value.findIndex(j => j.job_id === jobId)
    if (index !== -1) {
      jobs.value[index] = { ...jobs.value[index], ...update }
    }
  }

  function setAutoRefresh(enabled: boolean, interval?: number) {
    autoRefreshEnabled.value = enabled

    if (interval !== undefined && interval > 0) {
      autoRefreshInterval.value = interval
    }

    if (enabled) {
      startAutoRefresh()
    } else {
      stopAutoRefresh()
    }
  }

  function toggleAutoRefresh() {
    setAutoRefresh(!autoRefreshEnabled.value)
  }

  function startAutoRefresh() {
    if (refreshTimer) return

    refreshTimer = setInterval(async () => {
      await refreshAllJobs()

      // Stop polling if no in-progress jobs
      if (inProgressJobs.value.length === 0) {
        stopAutoRefresh()
      }
    }, autoRefreshInterval.value)
  }

  function stopAutoRefresh() {
    if (refreshTimer) {
      clearInterval(refreshTimer)
      refreshTimer = null
    }
    autoRefreshEnabled.value = false
  }

  function clearOldJobs(hoursOld: number = 24) {
    const cutoffTime = new Date(Date.now() - hoursOld * 60 * 60 * 1000)
    jobs.value = jobs.value.filter(job => {
      const jobTime = new Date(job.message) // Note: This is a simplified approach
      return jobTime > cutoffTime
    })
  }

  function clearAllJobs() {
    jobs.value = []
    selectedJob.value = null
  }

  function setSelectedJob(job: BackupJobStatus | null) {
    selectedJob.value = job
  }

  function clearError() {
    error.value = null
  }

  return {
    // State
    jobs,
    selectedJob,
    autoRefreshEnabled,
    autoRefreshInterval,
    loading,
    error,
    // Getters
    inProgressJobs,
    completedJobs,
    successCount,
    failureCount,
    // Actions
    loadJobs,
    refreshAllJobs,
    addJob,
    updateJob,
    setAutoRefresh,
    toggleAutoRefresh,
    startAutoRefresh,
    stopAutoRefresh,
    clearOldJobs,
    clearAllJobs,
    setSelectedJob,
    clearError,
  }
})
