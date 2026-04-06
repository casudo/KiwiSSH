<script setup lang="ts">
import { onMounted, onBeforeUnmount, computed, ref, watch } from "vue"
import { useJobsStore } from "@/stores/jobs"
import { useDevicesStore } from "@/stores/devices"
import { backupApi } from "@/api/backups"
import LoadingSpinner from "@/components/LoadingSpinner.vue"

const jobsStore = useJobsStore()
const devicesStore = useDevicesStore()
const showFilters = ref<boolean>(false)
const showFlushDialog = ref<boolean>(false)
const flushConfirmation = ref<string>("")
const filterStatus = ref<string>("")
const filterDevice = ref<string>("")
const filterIP = ref<string>("")
const filterJobId = ref<string>("")
const filterDateFrom = ref<string>("")
const filterDateTo = ref<string>("")
const pageSize = ref<number>(50)
const currentPage = ref<number>(1)
const pageSizeOptions = [25, 50, 100, 200]
let jobIdSearchTimer: ReturnType<typeof setTimeout> | null = null
let deviceSearchTimer: ReturnType<typeof setTimeout> | null = null

onMounted(async () => {
  // Load jobs from database
  await loadJobsPage()

  // Load devices for IP lookup
  if (devicesStore.devices.length === 0) {
    await devicesStore.fetchDevices()
  }

})

onBeforeUnmount(() => {
  jobsStore.stopAutoRefresh()
  if (jobIdSearchTimer) {
    clearTimeout(jobIdSearchTimer)
    jobIdSearchTimer = null
  }
  if (deviceSearchTimer) {
    clearTimeout(deviceSearchTimer)
    deviceSearchTimer = null
  }
})

watch(filterJobId, (value) => {
  if (jobIdSearchTimer) {
    clearTimeout(jobIdSearchTimer)
  }

  jobIdSearchTimer = setTimeout(async () => {
    currentPage.value = 1
    await loadJobsPage(value.trim() || undefined)
  }, 250)
})

watch(filterDevice, (value) => {
  if (deviceSearchTimer) {
    clearTimeout(deviceSearchTimer)
  }

  deviceSearchTimer = setTimeout(async () => {
    currentPage.value = 1
    await loadJobsPage(undefined, value.trim() || undefined)
  }, 250)
})

const filteredJobs = computed(() => {
  let result = jobsStore.jobs

  if (filterDevice.value) {
    const search = filterDevice.value.toLowerCase()
    result = result.filter(j => j.device_name.toLowerCase().includes(search))
  }

  if (filterIP.value) {
    const search = filterIP.value.toLowerCase()
    result = result.filter(j => {
      const device = getDeviceInfo(j.device_name)
      return device && device.ip_address.toLowerCase().includes(search)
    })
  }

  if (filterDateFrom.value) {
    const fromDate = new Date(filterDateFrom.value).getTime()
    result = result.filter(j => j.timestamp >= fromDate)
  }

  if (filterDateTo.value) {
    const toDate = new Date(filterDateTo.value)
    toDate.setHours(23, 59, 59, 999) // Include entire day
    result = result.filter(j => j.timestamp <= toDate.getTime())
  }

  return result
})

const totalPages = computed(() => Math.max(1, Math.ceil(jobsStore.totalJobs / pageSize.value)))
const pageStart = computed(() => {
  if (jobsStore.totalJobs === 0) return 0
  return (currentPage.value - 1) * pageSize.value + 1
})
const pageEnd = computed(() => Math.min(currentPage.value * pageSize.value, jobsStore.totalJobs))

async function loadJobsPage(jobIdOverride?: string, deviceNameOverride?: string) {
  const status = filterStatus.value || undefined
  const jobId = (jobIdOverride ?? filterJobId.value.trim()) || undefined
  const deviceName = (deviceNameOverride ?? filterDevice.value.trim()) || undefined
  const offset = (currentPage.value - 1) * pageSize.value

  await jobsStore.loadJobs(deviceName, status, pageSize.value, offset, jobId)

  const maxPage = Math.max(1, Math.ceil(jobsStore.totalJobs / pageSize.value))
  if (currentPage.value > maxPage) {
    currentPage.value = maxPage
    const nextOffset = (currentPage.value - 1) * pageSize.value
    await jobsStore.loadJobs(deviceName, status, pageSize.value, nextOffset, jobId)
  }
}

function handlePageSizeChange() {
  currentPage.value = 1
  void loadJobsPage()
}

function handleStatusFilterChange() {
  currentPage.value = 1
  void loadJobsPage()
}

function goToPreviousPage() {
  if (currentPage.value <= 1) return
  currentPage.value -= 1
  void loadJobsPage()
}

function goToNextPage() {
  if (currentPage.value >= totalPages.value) return
  currentPage.value += 1
  void loadJobsPage()
}

async function handleRefresh() {
  await loadJobsPage()
}

function clearFilters() {
  filterStatus.value = ""
  filterDevice.value = ""
  filterIP.value = ""
  filterJobId.value = ""
  filterDateFrom.value = ""
  filterDateTo.value = ""
  currentPage.value = 1
  void loadJobsPage()
}

function getDeviceInfo(deviceName: string) {
  return devicesStore.devices.find(d => d.device_name === deviceName)
}

function formatStatus(status: string): string {
  switch (status) {
    case "success":
      return "Success"
    case "failed":
      return "Failed"
    case "no_changes":
      return "No Changes"
    case "in_progress":
      return "In Progress"
    case "pending":
      return "Pending"
    default:
      return status.charAt(0).toUpperCase() + status.slice(1)
  }
}

async function handleFlushDatabase() {
  const confirmText = "Yes I am aware of all danger"
  if (flushConfirmation.value.toLowerCase() === confirmText.toLowerCase()) {
    try {
      // Call the API endpoint to flush the database
      await backupApi.flushDatabase()
      jobsStore.clearAllJobs()
      flushConfirmation.value = ""
      showFlushDialog.value = false
      console.log("Database flushed successfully")
    } catch (error) {
      console.error("Failed to flush database:", error)
    }
  }
}

</script>

<template>
  <div>
    <div class="mb-8 flex items-center justify-between">
      <div>
        <h1 class="text-3xl font-bold text-gray-900 dark:text-gray-100">Backup Jobs</h1>
        <p class="text-gray-500 dark:text-gray-400 mt-1">Monitor backup operations and job history</p>
      </div>
      <button
        @click="showFlushDialog = true"
        class="btn bg-red-600 text-white hover:bg-red-700"
      >
        Flush Database
      </button>
    </div>

    <!-- Stats -->
    <div class="grid grid-cols-1 md:grid-cols-5 gap-4 mb-6">
      <div class="card">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400">Total Jobs</p>
            <p class="text-2xl font-bold text-gray-900 dark:text-gray-100">{{ jobsStore.totalJobs }}</p>
          </div>
          <div class="text-3xl text-gray-300 dark:text-gray-500">📊</div>
        </div>
      </div>
      <div class="card">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400">In Progress</p>
            <p class="text-2xl font-bold text-blue-600">{{ jobsStore.inProgressCount }}</p>
          </div>
          <div class="text-3xl text-blue-300 dark:text-blue-500">⏳</div>
        </div>
      </div>
      <div class="card">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400">Successful</p>
            <p class="text-2xl font-bold text-green-600">{{ jobsStore.successCount }}</p>
          </div>
          <div class="text-3xl text-green-300 dark:text-green-500">✓</div>
        </div>
      </div>
      <div class="card">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400">No Changes</p>
            <p class="text-2xl font-bold text-yellow-600">{{ jobsStore.noChangesCount }}</p>
          </div>
          <div class="text-3xl text-yellow-300 dark:text-yellow-500">→</div>
        </div>
      </div>
      <div class="card">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400">Failed</p>
            <p class="text-2xl font-bold text-red-600">{{ jobsStore.failureCount }}</p>
          </div>
          <div class="text-3xl text-red-300 dark:text-red-500">✕</div>
        </div>
      </div>
    </div>

    <!-- Controls -->
    <div class="card mb-6">
      <div class="space-y-4">
        <!-- Header with toggle button -->
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100">Filters</h3>
          <button
            @click="showFilters = !showFilters"
            class="text-sm text-kiwissh-600 dark:text-kiwissh-400 hover:text-kiwissh-700 dark:hover:text-kiwissh-300 font-medium flex items-center gap-1"
          >
            {{ showFilters ? "▼ Hide" : "▶ Show" }} Filters
          </button>
        </div>

        <!-- Always visible: Device Name filter, Auto-refresh, and buttons -->
        <div class="flex flex-col md:flex-row gap-4 items-end">
          <div class="flex-1">
            <label class="label">Filter by Device Name</label>
            <input
              v-model="filterDevice"
              type="text"
              placeholder="e.g., device1, router..."
              class="input"
            />
          </div>

          <div class="flex-1">
            <label class="label">Filter by IP</label>
            <input
              v-model="filterIP"
              type="text"
              placeholder="e.g., 192.168.1..."
              class="input"
            />
          </div>

          <div class="space-y-2">
            <label class="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                :checked="jobsStore.autoRefreshEnabled"
                @change="jobsStore.toggleAutoRefresh()"
                class="w-4 h-4 text-kiwissh-600 rounded border-gray-300"
              >
              <span class="text-sm text-gray-700 dark:text-gray-300">Auto-refresh (sec)</span>
            </label>
            <input
              v-model.number="jobsStore.autoRefreshInterval"
              type="number"
              min="1"
              step="1"
              class="input text-sm"
              @change="jobsStore.setAutoRefresh(jobsStore.autoRefreshEnabled, jobsStore.autoRefreshInterval)"
            />
          </div>

          <div class="space-y-2">
            <label class="label">Entries per page</label>
            <select v-model.number="pageSize" @change="handlePageSizeChange" class="input text-sm">
              <option v-for="option in pageSizeOptions" :key="option" :value="option">
                {{ option }}
              </option>
            </select>
          </div>

          <div class="flex gap-2">
            <button
              @click="handleRefresh"
              :disabled="jobsStore.loading"
              class="btn btn-primary"
            >
              {{ jobsStore.loading ? "Refreshing..." : "Refresh" }}
            </button>
            <button
              @click="clearFilters"
              class="btn btn-secondary"
            >
              Clear
            </button>
          </div>
        </div>

        <!-- Collapsible: Additional filters -->
        <div v-show="showFilters" class="space-y-4 border-t border-gray-200 dark:border-gray-700 pt-4">
          <!-- Row 1: Status and Job ID -->
          <div class="flex flex-col md:flex-row gap-4">
            <div class="flex-1">
              <label class="label">Filter by Status</label>
              <select v-model="filterStatus" @change="handleStatusFilterChange" class="input">
                <option value="">All Status</option>
                <option value="in_progress">In Progress</option>
                <option value="success">Success</option>
                <option value="no_changes">No Changes</option>
                <option value="failed">Failed</option>
              </select>
            </div>

            <div class="flex-1">
              <label class="label">Filter by Job ID</label>
              <input
                v-model="filterJobId"
                type="text"
                placeholder="Job ID..."
                class="input"
              />
            </div>
          </div>

          <!-- Row 2: Date Range -->
          <div class="flex flex-col md:flex-row gap-4">
            <div class="flex-1">
              <label class="label">From Date</label>
              <input v-model="filterDateFrom" type="date" class="input" />
            </div>
            <div class="flex-1">
              <label class="label">To Date</label>
              <input v-model="filterDateTo" type="date" class="input" />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Jobs list -->
    <LoadingSpinner v-if="jobsStore.loading && jobsStore.jobs.length === 0" size="lg" class="py-12" />

    <div v-else-if="jobsStore.jobs.length === 0" class="card text-center py-12">
      <svg xmlns="http://www.w3.org/2000/svg" class="h-16 w-16 mx-auto text-gray-300 dark:text-gray-600 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
      <p class="text-gray-500 dark:text-gray-400 text-lg">No backup jobs yet</p>
      <p class="text-gray-400 dark:text-gray-500 text-sm mt-2">Trigger a backup to see jobs appear here</p>
    </div>

    <div v-else>
      <div v-if="filteredJobs.length === 0" class="card text-center py-8">
        <p class="text-gray-500 dark:text-gray-400 text-lg">No jobs match the current filters on this page</p>
        <p class="text-gray-400 dark:text-gray-500 text-sm mt-2">Try broadening filters or switch pages</p>
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="job in filteredJobs"
          :key="job.job_id"
          @click="jobsStore.setSelectedJob(job)"
          class="card-hover cursor-pointer p-4"
        >
          <div class="flex items-start justify-between gap-4">
            <!-- Main info -->
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-3 mb-2">
                <!-- Job message-->
                <h3 class="font-semibold text-gray-900 dark:text-gray-100">
                  {{ job.message || "<No job message provided!>" }}
                </h3>

                <!-- Status -->
                <span
                  :class="[
                    'px-2 py-1 rounded-full text-xs font-medium',
                    job.status === 'success' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/35 dark:text-emerald-300 dark:ring-1 dark:ring-emerald-800' :
                    job.status === 'no_changes' ? 'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/35 dark:text-cyan-300 dark:ring-1 dark:ring-cyan-800' :
                    job.status === 'failed' ? 'bg-rose-100 text-rose-700 dark:bg-rose-900/35 dark:text-rose-300 dark:ring-1 dark:ring-rose-800' :
                    job.status === 'in_progress' ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/35 dark:text-amber-300 dark:ring-1 dark:ring-amber-800' :
                    'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300 dark:ring-1 dark:ring-slate-600'
                  ]"
                >
                  {{ formatStatus(job.status) }}
                </span>
              </div>

              <!-- Details -->
              <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div>
                  <p class="text-gray-500 dark:text-gray-400 text-xs">Status</p>
                  <p class="font-medium text-gray-900 dark:text-gray-100">{{ job.status }}</p>
                </div>
                <div>
                  <p class="text-gray-500 dark:text-gray-400 text-xs">Group</p>
                  <p class="font-medium text-gray-900 dark:text-gray-100">{{ job.group }}</p>
                </div>
                <div>
                  <p class="text-gray-500 dark:text-gray-400 text-xs">Device Name</p>
                  <p class="font-medium text-gray-900 dark:text-gray-100">{{ job.device_name }}</p>
                </div>
                <div>
                  <p class="text-gray-500 dark:text-gray-400 text-xs">Device IP</p>
                  <p class="font-medium text-gray-900 dark:text-gray-100">{{ getDeviceInfo(job.device_name)?.ip_address || "N/A" }}</p>
                </div>
              </div>

              <!-- Timestamp -->
              <div class="mt-3 text-xs text-gray-500 dark:text-gray-400">
                <p>{{ new Date(job.timestamp).toLocaleString() }}</p>
                <!-- <p class="text-gray-400 text-xs mt-1">ⓘ Timezone converted for your local region</p> -->
              </div>

              <!-- Error message -->
              <div v-if="job.status === 'failed' && job.message" class="mt-3 p-3 bg-red-50 dark:bg-red-900/20 rounded text-sm text-red-700 dark:text-red-300">
                {{ job.message }}
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>

    <div v-if="jobsStore.totalJobs > 0" class="mt-4 flex items-center justify-between">
      <span class="text-sm text-gray-600 dark:text-gray-400">
        Page {{ currentPage }} of {{ totalPages }} ({{ pageStart }}-{{ pageEnd }} of {{ jobsStore.totalJobs }} total)
      </span>
      <div class="flex gap-2">
        <button
          @click="goToPreviousPage"
          :disabled="currentPage === 1"
          class="btn btn-secondary py-1 px-3 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
        >
          ← Previous
        </button>
        <button
          @click="goToNextPage"
          :disabled="currentPage >= totalPages"
          class="btn btn-secondary py-1 px-3 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Next →
        </button>
      </div>
    </div>

    <!-- Detail modal -->
    <div
      v-if="jobsStore.selectedJob"
      @click="jobsStore.setSelectedJob(null)"
      class="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50"
    >
      <div
        @click.stop
        class="bg-white dark:bg-slate-800 rounded-lg shadow-xl dark:shadow-black/50 max-w-md w-full max-h-screen overflow-y-auto"
      >
        <div class="sticky top-0 bg-white dark:bg-slate-800 border-b border-gray-200 dark:border-slate-700 px-6 py-4 flex items-center justify-between">
          <h2 class="text-xl font-semibold text-gray-900 dark:text-gray-100">Job Details</h2>
          <button
            @click="jobsStore.setSelectedJob(null)"
            class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
          >
            ✕
          </button>
        </div>

        <div class="px-6 py-4 space-y-4">
          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">Job ID</p>
            <p class="font-mono text-sm text-gray-900 dark:text-gray-100 break-all">{{ jobsStore.selectedJob.job_id }}</p>
          </div>

          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">Status</p>
            <p class="font-medium text-gray-900 dark:text-gray-100">{{ jobsStore.selectedJob.status }}</p>
          </div>

          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">Group</p>
            <p class="font-medium text-gray-900 dark:text-gray-100">{{ jobsStore.selectedJob.group }}</p>
          </div>

          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">Device Name</p>
            <p class="font-medium text-gray-900 dark:text-gray-100">{{ jobsStore.selectedJob.device_name }}</p>
          </div>

          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">Device IP</p>
            <p class="font-medium text-gray-900 dark:text-gray-100">{{ getDeviceInfo(jobsStore.selectedJob.device_name)?.ip_address || 'N/A' }}</p>
          </div>

          <div>
            <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">Timestamp</p>
            <p class="font-medium text-gray-900 dark:text-gray-100">{{ new Date(jobsStore.selectedJob.timestamp).toLocaleString() }}</p>
            <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">ⓘ Timezone converted for your local region</p>
          </div>

          <div v-if="jobsStore.selectedJob.message">
            <p class="text-sm text-gray-500 dark:text-gray-400 mb-1">Message</p>
            <p class="text-sm text-gray-900 dark:text-gray-100">{{ jobsStore.selectedJob.message }}</p>
          </div>
        </div>
      </div>
    </div>

    <!-- Flush Database Confirmation Dialog -->
    <div
      v-if="showFlushDialog"
      @click="showFlushDialog = false"
      class="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50"
    >
      <div
        @click.stop
        class="bg-white dark:bg-slate-800 rounded-lg shadow-xl dark:shadow-black/50 max-w-md w-full"
      >
        <div class="px-6 py-4 border-b border-gray-200 dark:border-slate-700">
          <h2 class="text-xl font-semibold text-gray-900 dark:text-gray-100">Flush Database</h2>
        </div>

        <div class="px-6 py-4">
          <p class="text-sm text-gray-700 dark:text-gray-300 mb-4">
            ⚠️ This action will delete ALL backup job records from the database. This cannot be undone.
          </p>
          <p class="text-sm text-gray-700 dark:text-gray-300 mb-4">
            To confirm, type the following text:
          </p>
          <p class="text-sm font-mono bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100 px-3 py-2 rounded mb-4">
            Yes I am aware of all danger
          </p>
          <input
            v-model="flushConfirmation"
            type="text"
            placeholder="Type confirmation text..."
            class="input mb-4 w-full"
          />
        </div>

        <div class="px-6 py-4 bg-gray-50 dark:bg-slate-900 border-t border-gray-200 dark:border-slate-700 flex gap-2 justify-end">
          <button
            @click="showFlushDialog = false"
            class="btn btn-secondary"
          >
            Cancel
          </button>
          <button
            @click="handleFlushDatabase"
            :disabled="flushConfirmation.toLowerCase() !== 'yes i am aware of all danger'"
            class="btn bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Flush Database
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
