export interface ThrottledFunction {
  (): void
  cancel(): void
}

/**
 * Run fn at most once per interval: the first call schedules a run after intervalMs,
 * further calls until then are merged into it (e.g. one reload for a burst of live updates).
 */
export function throttle(fn: () => void, intervalMs: number): ThrottledFunction {
  let timer: ReturnType<typeof setTimeout> | undefined

  const throttled = (() => {
    if (timer !== undefined) return
    timer = setTimeout(() => {
      timer = undefined
      fn()
    }, intervalMs)
  }) as ThrottledFunction

  throttled.cancel = () => {
    clearTimeout(timer)
    timer = undefined
  }

  return throttled
}
