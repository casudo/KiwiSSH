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

// Group backups by date (YYYY-MM-DD in local timezone)
const backupsByDate = computed((): Map<string, number> => {
  const map = new Map<string, number>()

  for (const backup of props.backups) {
    // Parse ISO timestamp and convert to local date
    const date = new Date(backup.timestamp)
    // Get local date string (not UTC)
    const year = date.getFullYear()
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    const dateStr = `${year}-${month}-${day}`

    map.set(dateStr, (map.get(dateStr) || 0) + 1)
  }

  return map
})

// Generate calendar grid showing last 12 months
const calendarWeeks = computed((): DayCell[][] => {
  const weeks: DayCell[][] = []
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  // Go back 12 months (approximately)
  const startDate = new Date(today)
  startDate.setMonth(startDate.getMonth() - 11)
  startDate.setDate(1) // Start from first day of month

  // Adjust to the Sunday of the week containing the 1st
  const dayOfWeek = startDate.getDay()
  startDate.setDate(startDate.getDate() - dayOfWeek)

  // Build weeks
  let currentDate = new Date(startDate)
  while (currentDate <= today) {
    const week: DayCell[] = []

    // Build a week (Sunday to Saturday)
    for (let i = 0; i < 7; i++) {
      if (currentDate > today) {
        week.push({ date: null, count: 0 })
      } else if (currentDate < startDate) {
        week.push({ date: null, count: 0 })
      } else {
        // Format date as YYYY-MM-DD
        const year = currentDate.getFullYear()
        const month = String(currentDate.getMonth() + 1).padStart(2, '0')
        const day = String(currentDate.getDate()).padStart(2, '0')
        const dateStr = `${year}-${month}-${day}`

        const count = backupsByDate.value.get(dateStr) || 0
        const displayDate = currentDate.toLocaleDateString('en-US', {
          weekday: 'short',
          month: 'short',
          day: 'numeric',
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

// Get month labels with proper positioning
const monthLabels = computed((): Array<{ month: string; startWeekIndex: number; endWeekIndex: number }> => {
  const labels: Array<{ month: string; startWeekIndex: number; endWeekIndex: number }> = []
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  const startDate = new Date(today)
  startDate.setMonth(startDate.getMonth() - 11)
  startDate.setDate(1)

  const dayOfWeek = startDate.getDay()
  startDate.setDate(startDate.getDate() - dayOfWeek)

  let currentDate = new Date(startDate)
  let weekIndex = 0
  let lastMonth = -1
  let monthStartWeekIndex = 0

  while (currentDate <= today) {
    const month = currentDate.getMonth()
    const year = currentDate.getFullYear()

    if (month !== lastMonth && lastMonth !== -1) {
      // Month changed, record the previous month
      labels.push({
        month: new Date(year, lastMonth).toLocaleDateString('en-US', { month: 'short' }),
        startWeekIndex: monthStartWeekIndex,
        endWeekIndex: weekIndex - 1,
      })
      monthStartWeekIndex = weekIndex
    } else if (lastMonth === -1) {
      monthStartWeekIndex = 0
    }

    lastMonth = month
    weekIndex++
    currentDate.setDate(currentDate.getDate() + 7)
  }

  // Add the last month
  if (lastMonth !== -1) {
    labels.push({
      month: new Date(currentDate.getFullYear(), lastMonth).toLocaleDateString('en-US', { month: 'short' }),
      startWeekIndex: monthStartWeekIndex,
      endWeekIndex: weekIndex - 1,
    })
  }

  return labels
})

// Calculate color intensity based on backup count
function getColorClass(count: number): string {
  if (count === 0) return 'bg-gray-100 hover:bg-gray-200'
  if (count === 1) return 'bg-downtown-200 hover:bg-downtown-300'
  if (count <= 3) return 'bg-downtown-400 hover:bg-downtown-500'
  if (count <= 5) return 'bg-downtown-600 hover:bg-downtown-700'
  return 'bg-downtown-800 hover:bg-downtown-900'
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
    <h3 class="text-lg font-semibold text-gray-900 mb-4">Backup Contribution Graph</h3>

    <div class="overflow-x-auto pb-4">
      <div class="inline-block min-w-max">
        <!-- Month labels row -->
        <div class="flex gap-px mb-2">
          <div class="w-10" /><!-- spacer for day labels -->
          <div v-for="label in monthLabels" :key="`${label.month}-${label.startWeekIndex}`" class="text-xs text-gray-600 font-medium" :style="{ width: `${(label.endWeekIndex - label.startWeekIndex + 1) * 13 - 1}px` }">
            {{ label.month }}
          </div>
        </div>

        <!-- Grid -->
        <div class="flex gap-px">
          <!-- Day labels (Y-axis) -->
          <div class="flex flex-col gap-px min-w-max">
            <div v-for="(label, idx) in dayLabels" :key="label" class="text-xs text-gray-600 font-medium text-right w-10 h-3 leading-3 flex items-center justify-end px-1">
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
                  cell.date ? [getColorClass(cell.count), props.selectedDate === cell.date ? 'ring-2 ring-gray-400 ring-offset-1' : 'border-gray-200'] : 'bg-transparent border-transparent cursor-default',
                ]"
              />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Legend -->
    <div class="mt-4 pt-4 border-t border-gray-200">
      <div class="text-xs text-gray-600 mb-2">Backup frequency:</div>
      <div class="flex items-center gap-3 flex-wrap">
        <div class="flex items-center gap-2">
          <div class="w-3 h-3 rounded-sm bg-gray-100 border border-gray-200" />
          <span class="text-xs text-gray-600">None</span>
        </div>
        <div class="flex items-center gap-2">
          <div class="w-3 h-3 rounded-sm bg-downtown-200" />
          <span class="text-xs text-gray-600">1</span>
        </div>
        <div class="flex items-center gap-2">
          <div class="w-3 h-3 rounded-sm bg-downtown-400" />
          <span class="text-xs text-gray-600">2-3</span>
        </div>
        <div class="flex items-center gap-2">
          <div class="w-3 h-3 rounded-sm bg-downtown-600" />
          <span class="text-xs text-gray-600">4-5</span>
        </div>
        <div class="flex items-center gap-2">
          <div class="w-3 h-3 rounded-sm bg-downtown-800" />
          <span class="text-xs text-gray-600">6+</span>
        </div>
      </div>
    </div>

    <div v-if="selectedDate" class="mt-4 text-sm text-downtown-600">
      <button @click="emit('dayCleared')" class="text-downtown-600 hover:text-downtown-700 underline">
        ✕ Clear filter
      </button>
      <span class="ml-2 text-gray-600">Showing backups for {{ selectedDate }}</span>
    </div>
  </div>
</template>
