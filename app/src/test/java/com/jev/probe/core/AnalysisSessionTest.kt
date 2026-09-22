package com.jev.probe.core

import org.junit.Assert.*
import org.junit.Test

class AnalysisSessionTest {
    @Test fun switchRejectsOldResultsEvenWhenMessagesMatch() {
        val s = AnalysisSession()
        val a = s.observe("wechat/A", "hello")
        s.request()
        assertEquals(a, s.startNext())
        val b = s.observe("wechat/B", "hello")
        s.request()
        assertFalse(s.isCurrent(a))
        assertNull(s.startNext())
        s.finish(a)
        assertEquals(b, s.startNext())
    }

    @Test fun burstKeepsNewestPendingMessage() {
        val s = AnalysisSession()
        val first = s.observe("A", "1")
        s.request(); s.startNext()
        s.observe("A", "2"); s.request()
        val latest = s.observe("A", "3"); s.request()
        assertNull(s.startNext())
        s.finish(first)
        assertEquals(latest, s.startNext())
        s.finish(latest)
        assertNull(s.startNext())
    }

    @Test fun leaveAndReturnCannotReviveOldTicket() {
        val s = AnalysisSession()
        val old = s.observe("A", "same")
        s.request(); s.startNext()
        s.invalidate()
        val fresh = s.observe("A", "same")
        assertNotEquals(old, fresh)
        assertFalse(s.isCurrent(old))
        assertNull(s.startNext())
    }

    @Test fun ownMessageCancelsPendingAnalysis() {
        val s = AnalysisSession()
        val first = s.observe("A", "incoming")
        s.request(); s.startNext()
        s.observe("A", "new incoming"); s.request()
        s.observe("A", "my reply")
        s.finish(first)
        assertNull(s.startNext())
    }

    @Test fun idleObservationDoesNotCreateWorkAndManualRetryWorks() {
        val s = AnalysisSession()
        val ticket = s.observe("A", "1")
        assertEquals(ticket, s.observe("A", "1"))
        assertNull(s.startNext())
        s.request(); assertEquals(ticket, s.startNext())
        s.finish(ticket)
        s.request(); assertEquals(ticket, s.startNext())
    }
}
