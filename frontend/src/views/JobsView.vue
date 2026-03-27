<script setup lang="ts">
import { onMounted, computed, ref } from "vue"
import { useJobsStore } from "@/stores/jobs"
import { useDevicesStore } from "@/stores/devices"
import LoadingSpinner from "@/components/LoadingSpinner.vue"

const jobsStore = useJobsStore()
const devicesStore = useDevicesStore()
const showFilters = ref<boolean>(false)
const filterStatus = ref<string>("")
const filterDevice = ref<string>("")
const filterIP = ref<string>("")
const filterJobId = ref<string>("")
const filterDateFrom = ref<string>("")
const filterDateTo = ref<string>("")

onMounted(async () => {
  // Load jobs from database
  await jobsStore.loadJobs()

  // Load devices for IP lookup
  if (devicesStore.devices.length === 0) {
    await devicesStore.fetchDevices()
  }

  // Cleanup on unmount
  return () => {
    jobsStore.stopAutoRefresh()
  }
})

const filteredJobs = computed(() => {
  let result = jobsStore.jobs

  if (filterStatus.value) {
    result = result.filter(j => j.status === filterStatus.value)
  }

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

  if (filterJobId.value) {
    const search = filterJobId.value.toLowerCase()
    result = result.filter(j => j.job_id.toLowerCase().includes(search))
  }

  if (filterDateFrom.value) {
    const fromDate = new Date(filterDateFrom.value).getTime()
    result = result.filter(j => j.timestamp >= fromDate)
  }

  if (filterDateTo.value) {
    const toDate = new Date(filterDateTo.value).getTime()
    toDate.setHours(23, 59, 59, 999) // Include entire day
    result = result.filter(j => j.timestamp <= toDate)
  }

  return result
})

const uniqueStatuses = computed(() => {
  return Array.from(new Set(jobsStore.jobs.map(j => j.status)))
})

async function handleRefresh() {
  await jobsStore.loadJobs()
}

function clearFilters() {
  filterStatus.value = ""
  filterDevice.value = ""
  filterIP.value = ""
  filterJobId.value = ""
  filterDateFrom.value = ""
  filterDateTo.value = ""
}

function getDeviceInfo(deviceName: string) {
  return devicesStore.devices.find(d => d.device_name === deviceName)
}
</script>

<template>
  <div>
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-900">Backup Jobs</h1>
      <p class="text-gray-500 mt-1">Monitor backup operations and job history</p>
    </div>

    <!-- Stats -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <div class="card">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Total Jobs</p>
            <p class="text-2xl font-bold text-gray-900">{{ jobsStore.jobs.length }}</p>
          </div>
          <div class="text-3xl text-gray-300">📊</div>
        </div>
      </div>
      <div class="card">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">In Progress</p>
            <p class="text-2xl font-bold text-blue-600">{{ jobsStore.inProgressJobs.length }}</p>
          </div>
          <div class="text-3xl text-blue-300">⏳</div>
        </div>
      </div>
      <div class="card">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Successful</p>
            <p class="text-2xl font-bold text-green-600">{{ jobsStore.successCount }}</p>
          </div>
          <div class="text-3xl text-green-300">✓</div>
        </div>
      </div>
      <div class="card">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-sm text-gray-500">Failed</p>
            <p class="text-2xl font-bold text-red-600">{{ jobsStore.failureCount }}</p>
          </div>
          <div class="text-3xl text-red-300">✕</div>
        </div>
      </div>
    </div>

    <!-- Controls -->
    <div class="card mb-6">
      <div class="space-y-4">
        <!-- Header with toggle button -->
        <div class="flex items-center justify-between mb-2">
          <h3 class="text-sm font-semibold text-gray-900">Filters</h3>
          <button
            @click="showFilters = !showFilters"
            class="text-sm text-downtown-600 hover:text-downtown-700 font-medium flex items-center gap-1"
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
                class="w-4 h-4 text-downtown-600 rounded border-gray-300"
              >
              <span class="text-sm text-gray-700">Auto-refresh (seconds)</span>
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
        <div v-show="showFilters" class="space-y-4 border-t border-gray-200 pt-4">
          <!-- Row 1: Status and Job ID -->
          <div class="flex flex-col md:flex-row gap-4">
            <div class="flex-1">
              <label class="label">Filter by Status</label>
              <select v-model="filterStatus" class="input">
                <option value="">All Status</option>
                <option value="pending">Pending</option>
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
      <svg xmlns="http://www.w3.org/2000/svg" class="h-16 w-16 mx-auto text-gray-300 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
      <p class="text-gray-500 text-lg">No backup jobs yet</p>
      <p class="text-gray-400 text-sm mt-2">Trigger a backup to see jobs appear here</p>
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
              <h3 class="font-semibold text-gray-900">
                {{ job.message || "<No job message provided!>" }}
              </h3>

              <!-- Status -->
              <span
                :class="[
                  'px-2 py-1 rounded-full text-xs font-medium',
                  job.status === 'success' ? 'bg-green-100 text-green-700' :
                  job.status === 'no_changes' ? 'bg-blue-100 text-blue-700' :
                  job.status === 'failed' ? 'bg-red-100 text-red-700' :
                  job.status === 'in_progress' ? 'bg-yellow-100 text-yellow-700' :
                  'bg-gray-100 text-gray-700'
                ]"
              >
                {{ job.status === "no_changes" ? "No Changes" : job.status }}
              </span>
            </div>

            <!-- Details -->
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <p class="text-gray-500 text-xs">Status</p>
                <p class="font-medium text-gray-900 capitalize">{{ job.status }}</p>
              </div>
              <div>
                <p class="text-gray-500 text-xs">Group</p>
                <p class="font-medium text-gray-900">{{ job.group }}</p>
              </div>
              <div>
                <p class="text-gray-500 text-xs">Device Name</p>
                <p class="font-medium text-gray-900">{{ job.device_name }}</p>
              </div>
              <div>
                <p class="text-gray-500 text-xs">Device IP</p>
                <p class="font-medium text-gray-900">{{ getDeviceInfo(job.device_name)?.ip_address || "N/A" }}</p>
              </div>
            </div>

            <!-- Timestamp -->
            <div class="mt-3 text-xs text-gray-500">
              <p>{{ new Date(job.timestamp).toLocaleString() }}</p>
              <!-- <p class="text-gray-400 text-xs mt-1">ⓘ Timezone converted for your local region</p> -->
            </div>

            <!-- Error message -->
            <div v-if="job.status === 'failed' && job.message" class="mt-3 p-3 bg-red-50 rounded text-sm text-red-700">
              {{ job.message }}
            </div>
          </div>

        </div>
      </div>
    </div>

    <!-- Detail modal -->
    <div
      v-if="jobsStore.selectedJob"
      @click="jobsStore.setSelectedJob(null)"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50"
    >
      <div
        @click.stop
        class="bg-white rounded-lg shadow-xl max-w-md w-full max-h-screen overflow-y-auto"
      >
        <div class="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <h2 class="text-xl font-semibold text-gray-900">Job Details</h2>
          <button
            @click="jobsStore.setSelectedJob(null)"
            class="text-gray-400 hover:text-gray-600"
          >
            ✕
          </button>
        </div>

        <div class="px-6 py-4 space-y-4">
          <div>
            <p class="text-sm text-gray-500 mb-1">Job ID</p>
            <p class="font-mono text-sm text-gray-900 break-all">{{ jobsStore.selectedJob.job_id }}</p>
          </div>

          <div>
            <p class="text-sm text-gray-500 mb-1">Status</p>
            <p class="font-medium text-gray-900 capitalize">{{ jobsStore.selectedJob.status }}</p>
          </div>

          <div>
            <p class="text-sm text-gray-500 mb-1">Group</p>
            <p class="font-medium text-gray-900">{{ jobsStore.selectedJob.group }}</p>
          </div>

          <div>
            <p class="text-sm text-gray-500 mb-1">Device Name</p>
            <p class="font-medium text-gray-900">{{ jobsStore.selectedJob.device_name }}</p>
          </div>

          <div>
            <p class="text-sm text-gray-500 mb-1">Device IP</p>
            <p class="font-medium text-gray-900">{{ getDeviceInfo(jobsStore.selectedJob.device_name)?.ip_address || 'N/A' }}</p>
          </div>

          <div>
            <p class="text-sm text-gray-500 mb-1">Timestamp</p>
            <p class="font-medium text-gray-900">{{ new Date(jobsStore.selectedJob.timestamp).toLocaleString() }}</p>
            <p class="text-xs text-gray-400 mt-1">ⓘ Timezone converted for your local region</p>
          </div>

          <div v-if="jobsStore.selectedJob.message">
            <p class="text-sm text-gray-500 mb-1">Message</p>
            <p class="text-sm text-gray-900">{{ jobsStore.selectedJob.message }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
