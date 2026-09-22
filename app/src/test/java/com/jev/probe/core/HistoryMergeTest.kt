package com.jev.probe.core

import com.jev.probe.core.kb.HistoryMerge
import org.junit.Assert.*
import org.junit.Test

class HistoryMergeTest {
    @Test fun disjointNewMessagesAreNotLost() {
        assertEquals(0, HistoryMerge.skipCount(listOf("old1", "old2"), listOf("new1", "new2")))
    }
    @Test fun scrollBackToKnownSequenceDoesNotAppend() {
        assertEquals(2, HistoryMerge.skipCount(listOf("a", "b", "c", "d"), listOf("a", "b")))
    }
    @Test fun overlappingScreenAppendsOnlyNewTail() {
        assertEquals(2, HistoryMerge.skipCount(listOf("a", "b", "c"), listOf("b", "c", "d")))
    }
    @Test fun repeatedShortMessagesKeepTheirPositions() {
        assertEquals(2, HistoryMerge.skipCount(listOf("ok", "ok"), listOf("ok", "ok", "new")))
    }
    @Test fun emptyLogAcceptsEverything() {
        assertEquals(0, HistoryMerge.skipCount(emptyList(), listOf("a")))
        assertEquals(0, HistoryMerge.skipCount(listOf("a"), emptyList()))
    }
}
