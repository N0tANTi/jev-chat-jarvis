package com.jev.probe.core

import java.net.URI

object ApiKeyRouting {
    /** Credentials can be inherited only by the same HTTPS origin. */
    fun canInherit(source: String, destination: String): Boolean = try {
        val a = URI(source)
        val b = URI(destination)
        a.scheme.equals("https", true) && b.scheme.equals("https", true) &&
            !a.host.isNullOrBlank() && a.host.equals(b.host, true) &&
            (if (a.port == -1) 443 else a.port) == (if (b.port == -1) 443 else b.port) &&
            a.userInfo == null && b.userInfo == null
    } catch (_: Exception) { false }
}
