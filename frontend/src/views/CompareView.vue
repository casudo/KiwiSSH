<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue"
import { RouterLink, useRoute, useRouter } from "vue-router"
import type { LocationQuery, LocationQueryRaw, LocationQueryValue } from "vue-router"
import axios from "axios"
import { useDevicesStore } from "@/stores/devices"
import { backupApi } from "@/api/backups"
import type { BuiltinIgnoreRule, ConfigCompareResponse, ConfigCompareSide } from "@/types/backup"
import type { Device } from "@/types/device"
import CompareSidePicker from "@/components/CompareSidePicker.vue"
import DiffViewer from "@/components/DiffViewer.vue"
import LoadingSpinner from "@/components/LoadingSpinner.vue"

interface CompareOptions {
  ignore: BuiltinIgnoreRule[]
  ignoreWhitespace: boolean
  ignorePatterns: string[]
  applyStripPatterns: boolean
  applyRedaction: boolean
}

const BUILTIN_RULES: Array<{ value: BuiltinIgnoreRule; label: string }> = [
  { value: "hostname", label: "Hostname" },
  { value: "ipv4", label: "IPv4 addresses" },
  { value: "ipv6", label: "IPv6 addresses" },
  { value: "mac", label: "MAC addresses" },
]
const BUILTIN_RULE_VALUES = BUILTIN_RULES.map((rule) => rule.value)

// The obvious differences between devices are ignored unless turned off
const DEFAULT_OPTIONS: CompareOptions = {
  ignore: BUILTIN_RULE_VALUES,
  ignoreWhitespace: false,
  ignorePatterns: [],
  applyStripPatterns: false,
  applyRedaction: false,
}

// The ignore options are usually the same for every comparison, so they're remembered
const OPTIONS_STORAGE_KEY = "kiwissh-compare-options"

const route = useRoute()
const router = useRouter()
const devicesStore = useDevicesStore()

const form = reactive({
  leftDevice: "",
  leftCommit: "",
  rightDevice: "",
  rightCommit: "",
  ignore: [...DEFAULT_OPTIONS.ignore],
  ignoreWhitespace: DEFAULT_OPTIONS.ignoreWhitespace,
  ignorePatternsText: "",
  applyStripPatterns: DEFAULT_OPTIONS.applyStripPatterns,
  applyRedaction: DEFAULT_OPTIONS.applyRedaction,
})

const result = ref<ConfigCompareResponse | null>(null)
const compareLoading = ref(false)
const compareError = ref<string | null>(null)
let compareRequestId = 0

const leftDeviceName = computed(() => form.leftDevice.trim())
const rightDeviceName = computed(() => form.rightDevice.trim())

const sortedDevices = computed(() => (
  [...devicesStore.devices].sort((a, b) => a.device_name.localeCompare(b.device_name))
))

// Devices of the same group usually belong to the same customer, so they're listed first for the other side
function devicesWithGroupFirst(otherDeviceName: string): Device[] {
  const group = devicesStore.devices.find((device) => device.device_name === otherDeviceName)?.group
  if (!group) return sortedDevices.value
  return [
    ...sortedDevices.value.filter((device) => device.group === group),
    ...sortedDevices.value.filter((device) => device.group !== group),
  ]
}

const leftDeviceOptions = computed(() => devicesWithGroupFirst(rightDeviceName.value))
const rightDeviceOptions = computed(() => devicesWithGroupFirst(leftDeviceName.value))

const knownDeviceNames = computed(() => new Set(devicesStore.devices.map((device) => device.device_name)))
const canCompare = computed(() => (
  knownDeviceNames.value.has(leftDeviceName.value) && knownDeviceNames.value.has(rightDeviceName.value)
))

// One pattern per line, trailing spaces are almost always unintended
const ignorePatterns = computed(() => (
  form.ignorePatternsText
    .split("\n")
    .map((pattern) => pattern.trimEnd())
    .filter((pattern) => pattern.trim() !== "")
))

function currentOptions(): CompareOptions {
  return {
    // Fixed order, so the same options always give the same URL
    ignore: BUILTIN_RULE_VALUES.filter((rule) => form.ignore.includes(rule)),
    ignoreWhitespace: form.ignoreWhitespace,
    ignorePatterns: ignorePatterns.value,
    applyStripPatterns: form.applyStripPatterns,
    applyRedaction: form.applyRedaction,
  }
}

function setOptions(options: CompareOptions) {
  form.ignore = [...options.ignore]
  form.ignoreWhitespace = options.ignoreWhitespace
  form.ignorePatternsText = options.ignorePatterns.join("\n")
  form.applyStripPatterns = options.applyStripPatterns
  form.applyRedaction = options.applyRedaction
}

const verdict = computed(() => {
  const comparison = result.value
  if (!comparison) return null

  const left = comparison.left.device_name
  const right = comparison.right.device_name
  if (comparison.identical) {
    return {
      tone: "success",
      title: "Identical configurations",
      detail: "Both configurations are exactly the same.",
    }
  }
  if (!comparison.has_differences) {
    return {
      tone: "success",
      title: "No differences with the ignore options applied",
      detail: "The configurations only differ in ignored text or whitespace.",
    }
  }
  return {
    tone: "warning",
    title: "Configurations differ",
    detail: `${comparison.lines_only_left} line(s) only in ${left} (red), ${comparison.lines_only_right} line(s) only in ${right} (green).`,
  }
})

const verdictClass = computed(() => (
  verdict.value?.tone === "success"
    ? "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200"
    : "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
))

// What the shown result ignored, a shared link may use other options than the remembered ones
const appliedOptions = computed((): string[] => {
  const comparison = result.value
  if (!comparison) return []

  const applied = BUILTIN_RULES.filter((rule) => comparison.ignore.includes(rule.value)).map((rule) => rule.label)
  if (comparison.ignore_whitespace) applied.push("whitespace")
  if (comparison.ignore_patterns.length) applied.push(`${comparison.ignore_patterns.length} custom pattern(s)`)
  if (comparison.apply_strip_patterns) applied.push("vendor strip patterns")
  if (comparison.apply_redaction) applied.push("vendor redaction patterns")
  return applied
})

const resultSides = computed(() => (
  result.value
    ? [
        { position: "Left", side: result.value.left },
        { position: "Right", side: result.value.right },
      ]
    : []
))

function vendorPatternLabel(count: number): string {
  return count > 0 ? `${count} applied` : "None defined by the vendor"
}

function sideRows(side: ConfigCompareSide): Array<{ label: string; value: string }> {
  const rows = [
    { label: "Group", value: side.group },
    { label: "Vendor", value: devicesStore.getVendorName(side.vendor) },
    { label: "Backup from", value: formatTimestamp(side.timestamp) },
    { label: "Lines", value: String(side.line_count) },
  ]
  if (result.value?.apply_strip_patterns) {
    rows.push({ label: "Strip patterns", value: vendorPatternLabel(side.strip_pattern_count) })
  }
  if (result.value?.apply_redaction) {
    rows.push({ label: "Redaction patterns", value: vendorPatternLabel(side.redaction_pattern_count) })
  }
  return rows
}

function queryValue(value: LocationQueryValue | LocationQueryValue[] | undefined): string {
  const first = Array.isArray(value) ? value[0] : value
  return first ?? ""
}

function queryList(value: LocationQueryValue | LocationQueryValue[] | undefined): string[] {
  const values = Array.isArray(value) ? value : [value]
  return values.filter((item): item is string => typeof item === "string" && item !== "")
}

function isBuiltinRule(value: unknown): value is BuiltinIgnoreRule {
  return typeof value === "string" && (BUILTIN_RULE_VALUES as string[]).includes(value)
}

// Missing or invalid values fall back to the defaults, e.g. options saved by an older version
function loadStoredOptions(): CompareOptions {
  try {
    const stored = JSON.parse(localStorage.getItem(OPTIONS_STORAGE_KEY) ?? "null")
    if (stored && typeof stored === "object") {
      return {
        ignore: Array.isArray(stored.ignore) ? stored.ignore.filter(isBuiltinRule) : DEFAULT_OPTIONS.ignore,
        ignoreWhitespace: typeof stored.ignoreWhitespace === "boolean" ? stored.ignoreWhitespace : DEFAULT_OPTIONS.ignoreWhitespace,
        ignorePatterns: Array.isArray(stored.ignorePatterns)
          ? stored.ignorePatterns.filter((pattern: unknown) => typeof pattern === "string")
          : DEFAULT_OPTIONS.ignorePatterns,
        applyStripPatterns: stored.applyStripPatterns === true,
        applyRedaction: stored.applyRedaction === true,
      }
    }
  } catch (e) {
    console.error("[Compare] Failed to load the compare options from localStorage:", e)
  }
  return DEFAULT_OPTIONS
}

function storeOptions(options: CompareOptions) {
  try {
    localStorage.setItem(OPTIONS_STORAGE_KEY, JSON.stringify(options))
  } catch (e) {
    console.error("[Compare] Failed to save the compare options to localStorage:", e)
  }
}

// A link with both devices describes a complete comparison (shareable, back/forward work) and runs right away.
// Otherwise (e.g. "Compare" on a device page) only the given devices are filled in and the last used options are restored
function applyQuery(query: LocationQuery) {
  form.leftDevice = queryValue(query.left)
  form.leftCommit = queryValue(query.left_commit)
  form.rightDevice = queryValue(query.right)
  form.rightCommit = queryValue(query.right_commit)

  if (form.leftDevice && form.rightDevice) {
    setOptions({
      ignore: queryList(query.ignore).filter(isBuiltinRule),
      ignoreWhitespace: queryValue(query.ws) === "1",
      ignorePatterns: queryList(query.pattern),
      applyStripPatterns: queryValue(query.strip) === "1",
      applyRedaction: queryValue(query.redact) === "1",
    })
    void runCompare()
    return
  }

  setOptions(loadStoredOptions())
  compareRequestId += 1 // Drop a comparison that is still running
  compareLoading.value = false
  compareError.value = null
  result.value = null
}

watch(
  () => route.query,
  (query) => {
    // The watcher still fires once while navigating away from this page
    if (route.name !== "compare") return
    applyQuery(query)
  },
  { immediate: true },
)

onMounted(async () => {
  try {
    await Promise.all([
      devicesStore.fetchDevices(),
      devicesStore.vendors.length === 0 ? devicesStore.fetchVendors() : Promise.resolve(),
    ])
  } catch {
    // The store keeps the error, it's shown above the form
  }
})

function submitCompare() {
  if (!canCompare.value) return

  const options = currentOptions()
  storeOptions(options)

  const query: LocationQueryRaw = { left: leftDeviceName.value, right: rightDeviceName.value }
  if (form.leftCommit) query.left_commit = form.leftCommit
  if (form.rightCommit) query.right_commit = form.rightCommit
  if (options.ignore.length) query.ignore = options.ignore
  if (options.ignoreWhitespace) query.ws = "1"
  if (options.ignorePatterns.length) query.pattern = options.ignorePatterns
  if (options.applyStripPatterns) query.strip = "1"
  if (options.applyRedaction) query.redact = "1"

  // Navigating to the current URL doesn't change the query, so compare again directly (e.g. after a new backup)
  if (router.resolve({ name: "compare", query }).fullPath === route.fullPath) {
    void runCompare()
  } else {
    void router.push({ name: "compare", query })
  }
}

function swapSides() {
  const { leftDevice, leftCommit } = form
  form.leftDevice = form.rightDevice
  form.leftCommit = form.rightCommit
  form.rightDevice = leftDevice
  form.rightCommit = leftCommit

  if (result.value) submitCompare()
}

async function runCompare() {
  const requestId = ++compareRequestId
  const options = currentOptions()
  compareLoading.value = true
  compareError.value = null

  try {
    const response = await backupApi.compare({
      leftDevice: leftDeviceName.value,
      rightDevice: rightDeviceName.value,
      leftCommit: form.leftCommit || undefined,
      rightCommit: form.rightCommit || undefined,
      ...options,
    })
    if (requestId !== compareRequestId) return
    result.value = response
  } catch (e) {
    if (requestId !== compareRequestId) return
    result.value = null
    compareError.value = getErrorMessage(e)
  } finally {
    if (requestId === compareRequestId) {
      compareLoading.value = false
    }
  }
}

// Show the backend's reason (unknown device, invalid pattern, ...) instead of "Request failed with status code 404"
function getErrorMessage(e: unknown): string {
  if (axios.isAxiosError(e)) {
    const detail = e.response?.data?.detail
    if (typeof detail === "string") return detail
  }
  return e instanceof Error ? e.message : "Failed to compare the configurations"
}

function formatTimestamp(timestamp: string | null): string {
  if (!timestamp) return "Unknown"
  const date = new Date(timestamp)
  return Number.isNaN(date.getTime()) ? timestamp : date.toLocaleString()
}
</script>

<template>
  <div>
    <div class="mb-8">
      <h1 class="text-3xl font-bold text-gray-900 dark:text-white">Compare</h1>
      <p class="text-gray-500 dark:text-gray-400 mt-1">
        Compare the configurations of two devices to find missing config snippets
      </p>
    </div>

    <div v-if="devicesStore.error" class="card mb-6 text-sm text-red-600 dark:text-red-400">
      Failed to load the device list: {{ devicesStore.error }}
    </div>

    <!-- relative z-10 keeps the device dropdowns above the result card -->
    <form class="card mb-6 relative z-10" @submit.prevent="submitCompare">
      <div class="grid grid-cols-1 lg:grid-cols-[1fr_auto_1fr] gap-4">
        <CompareSidePicker
          v-model:device="form.leftDevice"
          v-model:commit="form.leftCommit"
          label="Left device"
          input-id="compare-left"
          :devices="leftDeviceOptions"
        />

        <div class="flex items-center justify-center">
          <button
            type="button"
            class="btn btn-secondary px-3"
            title="Swap left and right"
            aria-label="Swap left and right"
            :disabled="!form.leftDevice && !form.rightDevice"
            @click="swapSides"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 rotate-90 lg:rotate-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
            </svg>
          </button>
        </div>

        <CompareSidePicker
          v-model:device="form.rightDevice"
          v-model:commit="form.rightCommit"
          label="Right device"
          input-id="compare-right"
          :devices="rightDeviceOptions"
        />
      </div>

      <div class="mt-6 space-y-5">
        <fieldset>
          <legend class="label">Ignore</legend>
          <div class="flex flex-wrap gap-x-6 gap-y-2">
            <label
              v-for="rule in BUILTIN_RULES"
              :key="rule.value"
              class="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer"
            >
              <input v-model="form.ignore" :value="rule.value" type="checkbox" class="h-4 w-4 rounded accent-kiwissh-600" />
              {{ rule.label }}
            </label>
            <label class="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
              <input v-model="form.ignoreWhitespace" type="checkbox" class="h-4 w-4 rounded accent-kiwissh-600" />
              Whitespace changes and blank lines
            </label>
          </div>
          <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Hostname covers hostname statements (<code class="font-mono">hostname</code>, <code class="font-mono">host-name</code>,
            <code class="font-mono">sysname</code>, ...) and the device's own name. Netmasks and wildcard masks stay visible.
            Ignored text is shown as <code class="font-mono">&lt;hostname&gt;</code>, <code class="font-mono">&lt;ipv4&gt;</code>,
            <code class="font-mono">&lt;ipv6&gt;</code> or <code class="font-mono">&lt;mac&gt;</code>.
          </p>
        </fieldset>

        <fieldset>
          <legend class="label">Vendor processing rules</legend>
          <div class="flex flex-wrap gap-x-6 gap-y-2">
            <label class="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
              <input v-model="form.applyStripPatterns" type="checkbox" class="h-4 w-4 rounded accent-kiwissh-600" />
              Apply strip patterns
            </label>
            <label class="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
              <input v-model="form.applyRedaction" type="checkbox" class="h-4 w-4 rounded accent-kiwissh-600" />
              Apply redaction patterns
            </label>
          </div>
          <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Uses <code class="font-mono">processing.strip_patterns</code> and <code class="font-mono">processing.redaction.patterns</code>
            from the vendor YAML file of each device. Strip patterns remove noisy lines like a backup does (e.g. in backups made
            before a pattern was added). Redaction hides secrets such as password hashes, which differ per device, even if
            redaction is disabled for the device.
          </p>
        </fieldset>

        <div>
          <label class="label" for="compare-ignore-patterns">Also ignore text matching (one regular expression per line)</label>
          <textarea
            id="compare-ignore-patterns"
            v-model="form.ignorePatternsText"
            rows="3"
            class="input font-mono text-sm"
            spellcheck="false"
            :placeholder="'ENC \\S+\n^snmp-server location .*'"
          />
          <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Matching text is replaced with <code class="font-mono">&lt;ignored&gt;</code> in both configurations before they are
            compared. Python regex syntax, e.g. <code class="font-mono">ENC \S+</code> for FortiOS secrets.
          </p>
        </div>
      </div>

      <div class="mt-6 flex justify-end">
        <button
          type="submit"
          class="btn btn-primary disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="!canCompare || compareLoading"
        >
          {{ compareLoading ? "Comparing..." : "Compare" }}
        </button>
      </div>
    </form>

    <!-- Keep the previous result in place while comparing again, so the page doesn't jump -->
    <LoadingSpinner v-if="compareLoading && !result" size="md" class="py-8" />

    <div v-else-if="compareError" class="card text-sm text-red-600 dark:text-red-400">
      {{ compareError }}
    </div>

    <div v-else-if="result && verdict" class="card transition-opacity" :class="{ 'opacity-50': compareLoading }">
      <div class="rounded-lg border px-4 py-3 mb-6" :class="verdictClass">
        <p class="font-semibold">{{ verdict.title }}</p>
        <p class="text-sm mt-0.5">{{ verdict.detail }}</p>
        <p v-if="!result.identical" class="text-xs mt-1 opacity-80">
          Ignored: {{ appliedOptions.length ? appliedOptions.join(", ") : "nothing" }}
        </p>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div
          v-for="{ position, side } in resultSides"
          :key="position"
          class="rounded-lg border border-gray-200 dark:border-slate-700 p-4"
        >
          <p class="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">{{ position }}</p>
          <RouterLink
            :to="{ name: 'device-detail', params: { name: side.device_name } }"
            class="text-lg font-semibold text-kiwissh-700 dark:text-kiwissh-300 hover:underline"
          >
            {{ side.device_name }}
          </RouterLink>
          <dl class="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
            <dt class="text-gray-500 dark:text-gray-400">Version</dt>
            <dd class="text-gray-900 dark:text-gray-100">
              v{{ side.version_number ?? "?" }}
              <code class="ml-1 text-xs font-mono bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 rounded">{{ side.commit.slice(0, 7) }}</code>
            </dd>
            <template v-for="row in sideRows(side)" :key="row.label">
              <dt class="text-gray-500 dark:text-gray-400">{{ row.label }}</dt>
              <dd class="text-gray-900 dark:text-gray-100">{{ row.value }}</dd>
            </template>
          </dl>
        </div>
      </div>

      <DiffViewer
        v-if="result.has_differences"
        :diff-content="result.diff"
        :lines-added="result.lines_only_right"
        :lines-removed="result.lines_only_left"
        :left-label="`${result.left.device_name} (only here in red)`"
        :right-label="`${result.right.device_name} (only here in green)`"
        :added-label="`only in ${result.right.device_name}`"
        :removed-label="`only in ${result.left.device_name}`"
      />
    </div>

    <div v-else class="card text-center py-12">
      <svg xmlns="http://www.w3.org/2000/svg" class="h-12 w-12 mx-auto mb-4 text-gray-300 dark:text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
        <path stroke-linecap="round" stroke-linejoin="round" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
      </svg>
      <p class="text-gray-500 dark:text-gray-400">Pick two devices and click "Compare"</p>
      <p class="text-sm text-gray-400 dark:text-gray-500 mt-1">
        The latest backups are compared unless you pick an older version
      </p>
    </div>
  </div>
</template>
