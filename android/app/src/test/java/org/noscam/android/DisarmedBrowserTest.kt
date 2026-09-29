package org.noscam.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class DisarmedBrowserTest {

    @Test
    fun `cleanUrl strips Google and Facebook click tracking IDs`() {
        val raw = "https://example.com/login?fbclid=123456789&user=alice&gclid=987654321"
        val cleaned = DisarmedBrowserActivity.cleanUrl(raw)
        assertEquals("https://example.com/login?user=alice", cleaned)
        assertFalse(cleaned.contains("fbclid"))
        assertFalse(cleaned.contains("gclid"))
    }

    @Test
    fun `cleanUrl strips all UTM campaign parameters`() {
        val raw = "https://banking-portal.test/auth?utm_source=phish&utm_medium=sms&utm_campaign=urgent&acc=9988"
        val cleaned = DisarmedBrowserActivity.cleanUrl(raw)
        assertEquals("https://banking-portal.test/auth?acc=9988", cleaned)
    }

    @Test
    fun `cleanUrl preserves URLs without query parameters`() {
        val raw = "https://example.com/article/123#section"
        val cleaned = DisarmedBrowserActivity.cleanUrl(raw)
        assertEquals(raw, cleaned)
    }

    @Test
    fun `cleanUrl handles empty query gracefully`() {
        val raw = "https://example.com/search?fbclid=bad"
        val cleaned = DisarmedBrowserActivity.cleanUrl(raw)
        assertEquals("https://example.com/search", cleaned)
    }
}
