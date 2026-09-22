package com.jev.probe.core

/** Main-thread state machine: one in-flight analysis, newest pending screen wins. */
class AnalysisSession {
    data class Ticket(val revision: Long, val conversation: String, val signature: String)

    private var revision = 0L
    var current: Ticket? = null
        private set
    private var pending: Ticket? = null
    private var running: Ticket? = null

    fun observe(conversation: String, signature: String): Ticket {
        val old = current
        if (old != null && old.conversation == conversation && old.signature == signature) return old
        return Ticket(++revision, conversation, signature).also {
            current = it
            pending = null
        }
    }

    fun invalidate() {
        revision++
        current = null
        pending = null
        // Keep the running slot occupied until BOTH network branches complete.
    }

    fun request() { pending = current }

    fun startNext(): Ticket? {
        if (running != null) return null
        val next = pending ?: return null
        pending = null
        running = next
        return next
    }

    fun isCurrent(ticket: Ticket): Boolean = current == ticket

    fun finish(ticket: Ticket) {
        if (running == ticket) running = null
    }
}
