<script setup lang="ts">
import { computed } from 'vue'

interface BackupEntry {
  timestamp: string
  version_number?: number
  [key: string]: unknown
}

interface Props {
  backups: BackupEntry[]
  selectedDate?: string
}

interface DayCell {
  date: string | null
  count: number
  displayDate?: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  daySelected: [date: string]
  dayCleared: []
}>()

const HISTORY_DAYS = 365
const DAYS_PER_WEEK = 7

function formatLocalDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

// Group backups by date (YYYY-MM-DD in local timezone)
const backupsByDate = computed((): Map<string, number> => {
  const map = new Map<string, number>()

  for (const backup of props.backups) {
    // Parse ISO timestamp and convert to local date
    const date = new Date(backup.timestamp)
    // Get local date string (not UTC)
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, "0")
    const day = String(date.getDate()).padStart(2, "0")
    const dateStr = `${year}-${month}-${day}`

    map.set(dateStr, (map.get(dateStr) || 0) + 1)
  }

  return map
})

// Generate calendar grid for a fixed recent window (last 365 days)
const calendarWeeks = computed((): DayCell[][] => {
  const weeks: DayCell[][] = []
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  const earliestVisibleDate = new Date(today)
  earliestVisibleDate.setDate(earliestVisibleDate.getDate() - (HISTORY_DAYS - 1))

  // Pad to full weeks for a stable heatmap layout
  const gridStartDate = new Date(earliestVisibleDate)
  gridStartDate.setDate(gridStartDate.getDate() - gridStartDate.getDay())

  const gridEndDate = new Date(today)
  gridEndDate.setDate(gridEndDate.getDate() + (DAYS_PER_WEEK - 1 - gridEndDate.getDay()))

  // Build weeks
  let currentDate = new Date(gridStartDate)
  while (currentDate <= gridEndDate) {
    const week: DayCell[] = []

    // Build a week (Sunday to Saturday)
    for (let i = 0; i < DAYS_PER_WEEK; i++) {
      if (currentDate < earliestVisibleDate || currentDate > today) {
        week.push({ date: null, count: 0 })
      } else {
        const dateStr = formatLocalDate(currentDate)

        const count = backupsByDate.value.get(dateStr) || 0
        const displayDate = currentDate.toLocaleDateString("en-US", {
          weekday: "short",
          month: "short",
          day: "numeric",
        })

        week.push({
          date: dateStr,
          count,
          displayDate,
        })
      }

      currentDate = new Date(currentDate)
      currentDate.setDate(currentDate.getDate() + 1)
    }

    weeks.push(week)
  }

  return weeks
})

// Get month labels from rendered week columns
const monthLabels = computed((): Array<{ month: string; startWeekIndex: number; endWeekIndex: number }> => {
  const labels: Array<{ month: string; startWeekIndex: number; endWeekIndex: number }> = []
  let activeLabel: { key: string; month: string; startWeekIndex: number; endWeekIndex: number } | null = null

  calendarWeeks.value.forEach((week, weekIdx) => {
    const firstVisibleCell = week.find((cell) => cell.date !== null)
    if (!firstVisibleCell || !firstVisibleCell.date) {
      return
    }

    const weekDate = new Date(`${firstVisibleCell.date}T00:00:00`)
    const monthKey = `${weekDate.getFullYear()}-${weekDate.getMonth()}`
    const monthText = weekDate.toLocaleDateString("en-US", { month: "short" })

    if (!activeLabel) {
      activeLabel = {
        key: monthKey,
        month: monthText,
        startWeekIndex: weekIdx,
        endWeekIndex: weekIdx,
      }
      return
    }

    if (activeLabel.key === monthKey) {
      activeLabel.endWeekIndex = weekIdx
      return
    }

    labels.push({
      month: activeLabel.month,
      startWeekIndex: activeLabel.startWeekIndex,
      endWeekIndex: activeLabel.endWeekIndex,
    })
    activeLabel = {
      key: monthKey,
      month: monthText,
      startWeekIndex: weekIdx,
      endWeekIndex: weekIdx,
    }
  })

  if (activeLabel) {
    labels.push({
      month: activeLabel.month,
      startWeekIndex: activeLabel.startWeekIndex,
      endWeekIndex: activeLabel.endWeekIndex,
    })
  }

  return labels
})

// Calculate color intensity based on backup count
function getColorClass(count: number): string {
  if (count === 0) return 'bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700'
  if (count === 1) return 'bg-kiwissh-200 hover:bg-kiwissh-300 dark:bg-kiwissh-900/65 dark:hover:bg-kiwissh-800/75'
  if (count <= 3) return 'bg-kiwissh-400 hover:bg-kiwissh-500 dark:bg-kiwissh-700/80 dark:hover:bg-kiwissh-600/90'
  if (count <= 5) return 'bg-kiwissh-600 hover:bg-kiwissh-700 dark:bg-kiwissh-500/90 dark:hover:bg-kiwissh-400'
  return 'bg-kiwissh-800 hover:bg-kiwissh-900 dark:bg-kiwissh-300 dark:hover:bg-kiwissh-200'
}

function handleDayClick(cell: DayCell) {
  if (!cell.date) return
  if (props.selectedDate === cell.date) {
    emit('dayCleared')
  } else {
    emit('daySelected', cell.date)
  }
}

const dayLabels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
</script>

<template>
  <div class="card">
    <h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Backup Contribution Graph</h3>

    <div class="overflow-x-auto pb-4">
      <div class="inline-block min-w-max">
        <!-- Month labels row -->
        <div class="flex gap-px mb-2">
          <div class="w-10" /><!-- spacer for day labels -->
          <div v-for="label in monthLabels" :key="`${label.month}-${label.startWeekIndex}`" class="text-xs text-gray-600 dark:text-gray-400 font-medium" :style="{ width: `${(label.endWeekIndex - label.startWeekIndex + 1) * 13 - 1}px` }">
            {{ label.month }}
          </div>
        </div>

        <!-- Grid -->
        <div class="flex gap-px">
          <!-- Day labels (Y-axis) -->
          <div class="flex flex-col gap-px min-w-max">
            <div v-for="(label, idx) in dayLabels" :key="label" class="text-xs text-gray-600 dark:text-gray-400 font-medium text-right w-10 h-3 leading-3 flex items-center justify-end px-1">
              {{ label }}
            </div>
          </div>

          <!-- Weeks grid -->
          <div class="flex gap-px">
            <div v-for="(week, weekIdx) in calendarWeeks" :key="weekIdx" class="flex flex-col gap-px">
              <div
                v-for="(cell, dayIdx) in week"
                :key="`${weekIdx}-${dayIdx}`"
                :title="cell.displayDate ? `${cell.displayDate}: ${cell.count} backup${cell.count !== 1 ? 's' : ''}` : ''"
                @click="handleDayClick(cell)"
                class="w-3 h-3 rounded-sm cursor-pointer transition-colors border"
                :class="[
                  cell.date ? [getColorClass(cell.count), props.selectedDate === cell.date ? 'ring-2 ring-kiwissh-500 dark:ring-kiwissh-300 ring-offset-1 ring-offset-white dark:ring-offset-slate-900' : 'border-slate-200 dark:border-slate-700'] : 'bg-transparent border-transparent cursor-default',
                ]"
              />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Legend -->
    <div class="mt-4 pt-4 border-t border-gray-200 dark:border-slate-700">
      <div class="text-xs text-gray-600 dark:text-gray-400 mb-2">Backup frequency:</div>
      <div class="flex items-center gap-3 flex-wrap">
        <div class="flex items-center gap-2">
          <div class="w-3 h-3 rounded-sm bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700" />
          <span class="text-xs text-gray-600 dark:text-gray-400">None</span>
        </div>
        <div class="flex items-center gap-2">
          <div class="w-3 h-3 rounded-sm bg-kiwissh-200 dark:bg-kiwissh-900/50" />
          <span class="text-xs text-gray-600 dark:text-gray-400">1</span>
        </div>
        <div class="flex items-center gap-2">
          <div class="w-3 h-3 rounded-sm bg-kiwissh-400 dark:bg-kiwissh-700/70" />
          <span class="text-xs text-gray-600 dark:text-gray-400">2-3</span>
        </div>
        <div class="flex items-center gap-2">
          <div class="w-3 h-3 rounded-sm bg-kiwissh-600 dark:bg-kiwissh-500" />
          <span class="text-xs text-gray-600 dark:text-gray-400">4-5</span>
        </div>
        <div class="flex items-center gap-2">
          <div class="w-3 h-3 rounded-sm bg-kiwissh-800 dark:bg-kiwissh-300" />
          <span class="text-xs text-gray-600 dark:text-gray-400">6+</span>
        </div>
      </div>
    </div>

    <div v-if="selectedDate" class="mt-4 text-sm text-kiwissh-600 dark:text-kiwissh-400">
      <button @click="emit('dayCleared')" class="text-kiwissh-600 dark:text-kiwissh-400 hover:text-kiwissh-700 dark:hover:text-kiwissh-300 underline">
        ✕ Clear filter
      </button>
      <span class="ml-2 text-gray-600 dark:text-gray-400">Showing backups for {{ selectedDate }}</span>
    </div>
  </div>
</template>
