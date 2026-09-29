package org.noscam.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class VishingDefenseTest {

    private val testSecret = "0123456789abcdef0123456789abcdef".let { VishingDefense.hexToBytes(it) }

    @Test
    fun `time code is deterministic within the same window`() {
        val t0 = 1700000000000L
        val code1 = VishingDefense.generateTimeCode(testSecret, t0, 120)
        val code2 = VishingDefense.generateTimeCode(testSecret, t0 + 30000, 120) // +30s, same window
        assertEquals(code1, code2)
        assertEquals("275 976", code1)
        assertEquals(7, code1.length) // "123 456"
        assertTrue(code1.contains(" "))
    }

    @Test
    fun `time code changes in a different window`() {
        val t0 = 1700000000000L
        val code1 = VishingDefense.generateTimeCode(testSecret, t0, 120)
        val code2 = VishingDefense.generateTimeCode(testSecret, t0 + 130000, 120) // +130s, next window
        assertNotEquals(code1, code2)
    }

    @Test
    fun `verifyTimeCode succeeds within drift window and rejects invalid codes`() {
        val t0 = 1700000000000L
        val code = VishingDefense.generateTimeCode(testSecret, t0, 120)

        // Exact match
        assertTrue(VishingDefense.verifyTimeCode(testSecret, code, t0, 120))
        // Unspaced candidate
        assertTrue(VishingDefense.verifyTimeCode(testSecret, code.replace(" ", ""), t0, 120))
        // 1 window ahead (+100s) within drift
        assertTrue(VishingDefense.verifyTimeCode(testSecret, code, t0 + 100000, 120, allowedDriftWindows = 1))

        // Wrong code
        assertFalse(VishingDefense.verifyTimeCode(testSecret, "999 999", t0, 120))
        // Malformed code
        assertFalse(VishingDefense.verifyTimeCode(testSecret, "abc", t0, 120))
    }

    @Test
    fun `computeChallengeResponse produces deterministic 3-digit response and verifies correctly`() {
        val challenge = "492"
        val response = VishingDefense.computeChallengeResponse(testSecret, challenge)
        assertEquals("958", response)
        assertEquals(3, response.length)
        assertTrue(response.all { it.isDigit() })

        assertTrue(VishingDefense.verifyChallengeResponse(testSecret, challenge, response))
        assertFalse(VishingDefense.verifyChallengeResponse(testSecret, challenge, "000"))
        assertFalse(VishingDefense.verifyChallengeResponse(testSecret, "493", response))
    }

    @Test
    fun `deriveSasFromSessionKey returns 6-digit formatted string`() {
        val sessionKey = ByteArray(32) { (it + 1).toByte() }
        val sas = VishingDefense.deriveSasFromSessionKey(sessionKey)
        assertEquals(7, sas.length)
        val digits = sas.replace(" ", "")
        assertEquals(6, digits.length)
        assertTrue(digits.all { it.isDigit() })
    }

    @Test
    fun `generateRandomSeedHex produces valid 32-char hex string`() {
        val hex = VishingDefense.generateRandomSeedHex()
        assertEquals(32, hex.length)
        val bytes = VishingDefense.hexToBytes(hex)
        assertEquals(16, bytes.size)
    }
}
