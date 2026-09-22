package com.jev.probe.core

import org.junit.Assert.*
import org.junit.Test

class ApiKeyRoutingTest {
    @Test fun sameProviderCanShareKey() {
        assertTrue(ApiKeyRouting.canInherit("https://openrouter.ai/api", "https://openrouter.ai/api/v1"))
        assertTrue(ApiKeyRouting.canInherit("https://openrouter.ai", "https://openrouter.ai:443/api"))
    }
    @Test fun differentProviderMustNotReceiveKey() {
        assertFalse(ApiKeyRouting.canInherit("https://api.typesafe.ai", "https://openrouter.ai/api/v1"))
        assertFalse(ApiKeyRouting.canInherit("https://openrouter.ai", "https://openrouter.ai.example.com"))
        assertFalse(ApiKeyRouting.canInherit("https://openrouter.ai", "https://openrouter.ai:8443"))
    }
    @Test fun insecureOrInvalidAddressMustNotInherit() {
        assertFalse(ApiKeyRouting.canInherit("https://openrouter.ai", "http://openrouter.ai"))
        assertFalse(ApiKeyRouting.canInherit("oops", "oops"))
        assertFalse(ApiKeyRouting.canInherit("https://openrouter.ai", "https://user@openrouter.ai"))
    }
}
