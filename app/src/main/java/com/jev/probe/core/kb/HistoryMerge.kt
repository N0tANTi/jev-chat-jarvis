package com.jev.probe.core.kb

/** Number of leading screen entries already recorded; no timestamp is available. */
object HistoryMerge {
    fun skipCount(log: List<String>, screen: List<String>): Int {
        if (screen.isEmpty()) return 0
        // An exact historical sequence is an old screen, even if away from the tail.
        if (screen.size <= log.size && (0..log.size - screen.size).any { start ->
                screen.indices.all { log[start + it] == screen[it] }
            }) return screen.size
        for (n in minOf(log.size, screen.size) downTo 1) {
            if ((0 until n).all { log[log.size - n + it] == screen[it] }) return n
        }
        // A disjoint screen can be NEW messages received while the app was away.
        // Without message IDs/timestamps we must not silently discard all of it.
        return 0
    }
}
