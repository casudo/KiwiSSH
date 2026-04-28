import { defineStore } from "pinia"
import { ref, computed } from "vue"
import { backupApi } from "@/api/backups"
import type { BackupJobStatus, BackupJobRecord } from "@/types/backup"

interface JobsQueryState {
  deviceName?: string
  status?: string
  limit: number
  offset: number
  jobId?: string
  includeMetadata: boolean
}

export const useJobsStore = defineStore("jobs", () => {
  // State
  const jobs = ref<BackupJobStatus[]>([])
  const selectedJob = ref<BackupJobStatus | null>(null)
  const autoRefreshEnabled = ref(false)
  const autoRefreshInterval = ref(3) // Default 3 seconds
  const loading = ref(false)
  const error = ref<string | null>(null)
  const totalJobs = ref(0)
  const totalSuccessJobs = ref(0)
  const totalFailedJobs = ref(0)
  const totalInProgressJobs = ref(0)
  const totalNoChangesJobs = ref(0)
  const avgDurationSeconds = ref<number | null>(null)
  const queueDepth = ref<number | null>(null)
  const lastQuery = ref<JobsQueryState>({
    limit: 200,
    offset: 0,
    includeMetadata: false,
  })

  let refreshTimer: ReturnType<typeof setInterval> | null = null

  // Getters
  const inProgressJobs = computed(() =>
    jobs.value.filter(j => j.status === "pending" || j.status === "in_progress")
  )

  const inProgressCount = computed(() => totalInProgressJobs.value)

  const completedJobs = computed(() =>
    jobs.value.filter(j => j.status === "success" || j.status === "failed" || j.status === "no_changes")
  )

  const successCount = computed(() => totalSuccessJobs.value)

  const failureCount = computed(() => totalFailedJobs.value)

  const noChangesCount = computed(() => totalNoChangesJobs.value)

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

  // Map API job record to internal job status format
  function mapJobRecord(job: BackupJobRecord): BackupJobStatus {
    return {
      job_id: job.job_id,
      device_name: job.device_name,
      group: job.group,
      status: job.status,
      timestamp: new Date(job.timestamp).getTime(),
      message: job.error_message || getJobMessage(job.status, job.device_name),
      duration_seconds: job.duration_seconds ?? null,
      metadata_output: job.metadata_output ?? null,
      config_size_bytes: job.config_size_bytes ?? null,
    }
  }

  // Actions
  async function loadJobs(
    deviceName?: string,
    status?: string,
    limit: number = 200,
    offset: number = 0,
    jobId?: string,
    includeMetadata: boolean = false,
  ) {
    loading.value = true
    error.value = null
    lastQuery.value = {
      deviceName,
      status,
      limit,
      offset,
      jobId,
      includeMetadata,
    }

    try {
      const response = await backupApi.getJobs(deviceName, status, limit, offset, jobId, includeMetadata)
      const rawJobs = response.jobs || []
      totalJobs.value = typeof response.total_count === "number" ? response.total_count : rawJobs.length
      avgDurationSeconds.value = typeof response.avg_duration_seconds === "number"
        ? response.avg_duration_seconds
        : null
      queueDepth.value = typeof response.queue_depth === "number" ? response.queue_depth : null
      const statusTotals = response.status_totals
      if (statusTotals) {
        totalSuccessJobs.value = statusTotals.success || 0
        totalFailedJobs.value = statusTotals.failed || 0
        totalInProgressJobs.value = (statusTotals.pending || 0) + (statusTotals.in_progress || 0)
        totalNoChangesJobs.value = statusTotals.no_changes || 0
      } else {
        totalSuccessJobs.value = rawJobs.filter((job: BackupJobRecord) => job.status === "success").length
        totalFailedJobs.value = rawJobs.filter((job: BackupJobRecord) => job.status === "failed").length
        totalInProgressJobs.value = rawJobs.filter((job: BackupJobRecord) => job.status === "pending" || job.status === "in_progress").length
        totalNoChangesJobs.value = rawJobs.filter((job: BackupJobRecord) => job.status === "no_changes").length
      }

      jobs.value = rawJobs.map((job: BackupJobRecord) => mapJobRecord(job))
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Failed to load jobs"
      console.error("Error loading jobs:", e)
    } finally {
      loading.value = false
    }
  }

  // Load details for a specific job and update the store
  async function loadJobDetails(jobId: string): Promise<BackupJobStatus | null> {
    try {
      const response = await backupApi.getJobs(undefined, undefined, 1, 0, jobId, true)
      const rawJob = response.jobs?.[0]
      if (!rawJob) {
        return null
      }

      const detailedJob = mapJobRecord(rawJob)
      const existingIndex = jobs.value.findIndex((job) => job.job_id === detailedJob.job_id)
      if (existingIndex !== -1) {
        jobs.value[existingIndex] = detailedJob
      }
      selectedJob.value = detailedJob
      return detailedJob
    } catch (e) {
      console.error("Error loading job details:", e)
      return null
    }
  }


  function addJob(job: BackupJobStatus) {
    // Check if job already exists
    const existing = jobs.value.findIndex(j => j.job_id === job.job_id)
    if (existing !== -1) {
      jobs.value[existing] = job
    } else {
      jobs.value.unshift(job) // Add to beginning (newest first)
      totalJobs.value += 1
      if (job.status === "success") totalSuccessJobs.value += 1
      if (job.status === "failed") totalFailedJobs.value += 1
      if (job.status === "no_changes") totalNoChangesJobs.value += 1
      if (job.status === "pending" || job.status === "in_progress") totalInProgressJobs.value += 1
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
      // Stop any existing timer
      if (refreshTimer) {
        clearInterval(refreshTimer)
        refreshTimer = null
      }
      // Start fresh with the interval
      startAutoRefresh()
    } else {
      // Stop the timer and set enabled to false
      if (refreshTimer) {
        clearInterval(refreshTimer)
        refreshTimer = null
      }
    }
  }

  function toggleAutoRefresh() {
    setAutoRefresh(!autoRefreshEnabled.value)
  }

  function startAutoRefresh() {
    if (refreshTimer) return

    refreshTimer = setInterval(async () => {
      await loadJobs(
        lastQuery.value.deviceName,
        lastQuery.value.status,
        lastQuery.value.limit,
        lastQuery.value.offset,
        lastQuery.value.jobId,
        lastQuery.value.includeMetadata,
      )
    }, autoRefreshInterval.value * 1000) // Convert seconds to milliseconds
  }

  function stopAutoRefresh() {
    if (refreshTimer) {
      clearInterval(refreshTimer)
      refreshTimer = null
    }
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
    totalJobs.value = 0
    totalSuccessJobs.value = 0
    totalFailedJobs.value = 0
    totalInProgressJobs.value = 0
    totalNoChangesJobs.value = 0
    avgDurationSeconds.value = null
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
    totalJobs,
    totalSuccessJobs,
    totalFailedJobs,
    totalInProgressJobs,
    totalNoChangesJobs,
    avgDurationSeconds,
    queueDepth,
    // Getters
    inProgressJobs,
    inProgressCount,
    completedJobs,
    successCount,
    failureCount,
    noChangesCount,
    // Actions
    loadJobs,
    addJob,
    updateJob,
    setAutoRefresh,
    toggleAutoRefresh,
    startAutoRefresh,
    stopAutoRefresh,
    clearOldJobs,
    clearAllJobs,
    setSelectedJob,
    loadJobDetails,
    clearError,
  }
})
