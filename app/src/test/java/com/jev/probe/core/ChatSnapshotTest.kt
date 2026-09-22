package com.jev.probe.core

import org.junit.Assert.*
import org.junit.Test

class ChatSnapshotTest {
    @Test fun messageSeparatorsCannotCauseSignatureCollision() {
        val a = ChatSnapshot("A", listOf(Msg("other", "a|me:b")))
        val b = ChatSnapshot("A", listOf(Msg("other", "a"), Msg("me", "b")))
        assertNotEquals(a.signature(), b.signature())
    }
    @Test fun changesAnywhereInModelWindowInvalidateResults() {
        val messages = (1..10).map { Msg("other", "$it") }
        val original = ChatSnapshot("A", messages)
        val changed = original.copy(messages = listOf(Msg("other", "changed")) + messages.drop(1))
        assertNotEquals(original.signature(), changed.signature())
    }
}
