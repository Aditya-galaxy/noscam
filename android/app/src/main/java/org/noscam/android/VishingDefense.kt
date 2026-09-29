package org.noscam.android

import java.nio.ByteBuffer
import java.security.SecureRandom
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * Ephemeral mutual challenge-response and Short Authentication String (SAS)
 * engine to defeat voice cloning (AI deepfake vishing) and caller-ID spoofing.
 *
 * Attack Scenario:
 * An attacker uses AI voice synthesis or caller ID spoofing to impersonate an
 * executive ("urgent wire transfer"), an IT administrator ("give me your OTP"),
 * or a family member ("emergency bail money").
 *
 * Defense Invariant:
 * Human vocal timbre and caller ID can be synthetically replicated; shared
 * ephemeral cryptographic state cannot.
 *
 * This engine provides two cooperative verification modes:
 * 1. Synchronous Ephemeral Code (SAS): A time-stepped 6-digit rolling code (120s window)
 *    derived via HMAC-SHA256 from an enrolled team or family seed. Both parties see
 *    the identical code simultaneously.
 * 2. Verbal Challenge-Response: The receiver gives a 3-digit challenge over the call;
 *    the caller's NoScam app derives the matching 3-digit cryptographic response.
 */
object VishingDefense {

    private const val HMAC_ALGORITHM = "HmacSHA256"
    const val DEFAULT_WINDOW_SECONDS = 120L

    /**
     * Generates a 6-digit time-stepped mutual code for the current window.
     * Format: "123 456"
     */
    fun generateTimeCode(
        secret: ByteArray,
        timeMs: Long = System.currentTimeMillis(),
        windowSeconds: Long = DEFAULT_WINDOW_SECONDS
    ): String {
        val window = timeMs / 1000L / windowSeconds
        val mac = Mac.getInstance(HMAC_ALGORITHM)
        mac.init(SecretKeySpec(secret, HMAC_ALGORITHM))

        val buffer = ByteBuffer.allocate(8).putLong(window).array()
        val hash = mac.doFinal(buffer)

        // Dynamic truncation (RFC 6238 / RFC 4226 style)
        val offset = (hash[hash.size - 1].toInt() and 0x0F)
        val binary = ((hash[offset].toInt() and 0x7F) shl 24) or
            ((hash[offset + 1].toInt() and 0xFF) shl 16) or
            ((hash[offset + 2].toInt() and 0xFF) shl 8) or
            (hash[offset + 3].toInt() and 0xFF)

        val codeInt = (binary % 1_000_000).toInt()
        val codeStr = String.format("%06d", codeInt)
        return "${codeStr.substring(0, 3)} ${codeStr.substring(3)}"
    }

    /**
     * Verifies a candidate code against the secret, allowing a configurable drift
     * window (default ±1 window = ±120s) to account for clock skew.
     */
    fun verifyTimeCode(
        secret: ByteArray,
        candidateCode: String,
        timeMs: Long = System.currentTimeMillis(),
        windowSeconds: Long = DEFAULT_WINDOW_SECONDS,
        allowedDriftWindows: Int = 1
    ): Boolean {
        val normalizedCandidate = candidateCode.replace("\\s".toRegex(), "")
        if (normalizedCandidate.length != 6 || !normalizedCandidate.all { it.isDigit() }) {
            return false
        }

        val currentWindow = timeMs / 1000L / windowSeconds
        for (offset in -allowedDriftWindows..allowedDriftWindows) {
            val windowTimeMs = (currentWindow + offset) * windowSeconds * 1000L
            val expectedFormatted = generateTimeCode(secret, windowTimeMs, windowSeconds)
            val expectedNormalized = expectedFormatted.replace(" ", "")
            if (constantTimeEquals(normalizedCandidate, expectedNormalized)) {
                return true
            }
        }
        return false
    }

    /**
     * Verbal Challenge-Response:
     * When receiving a call, Person A gives a 3-digit challenge (e.g. "842").
     * Person B types "842" into NoScam; Person B's app computes a 3-digit response
     * (e.g. "197"). Person B reads "197". Person A confirms.
     */
    fun computeChallengeResponse(
        secret: ByteArray,
        challenge: String
    ): String {
        val cleanChallenge = challenge.trim()
        val mac = Mac.getInstance(HMAC_ALGORITHM)
        mac.init(SecretKeySpec(secret, HMAC_ALGORITHM))
        val hash = mac.doFinal(cleanChallenge.toByteArray(Charsets.UTF_8))

        val binary = ((hash[0].toInt() and 0x7F) shl 16) or
            ((hash[1].toInt() and 0xFF) shl 8) or
            (hash[2].toInt() and 0xFF)

        val respInt = binary % 1000
        return String.format("%03d", respInt)
    }

    /**
     * Verifies that the spoken response matches the expected cryptographic response
     * for the given challenge.
     */
    fun verifyChallengeResponse(
        secret: ByteArray,
        challenge: String,
        response: String
    ): Boolean {
        val expected = computeChallengeResponse(secret, challenge)
        return constantTimeEquals(response.trim(), expected)
    }

    /**
     * Derives a Short Authentication String (SAS) directly from an established
     * E2EE session key or ratchet state.
     */
    fun deriveSasFromSessionKey(sessionKey: ByteArray): String {
        val mac = Mac.getInstance(HMAC_ALGORITHM)
        mac.init(SecretKeySpec(sessionKey, HMAC_ALGORITHM))
        val hash = mac.doFinal("noscam_sas_vishing_guard".toByteArray(Charsets.UTF_8))

        val offset = (hash[hash.size - 1].toInt() and 0x0F)
        val binary = ((hash[offset].toInt() and 0x7F) shl 24) or
            ((hash[offset + 1].toInt() and 0xFF) shl 16) or
            ((hash[offset + 2].toInt() and 0xFF) shl 8) or
            (hash[offset + 3].toInt() and 0xFF)

        val codeInt = (binary % 1_000_000).toInt()
        val codeStr = String.format("%06d", codeInt)
        return "${codeStr.substring(0, 3)} ${codeStr.substring(3)}"
    }

    /**
     * Constant-time string equality to prevent timing side channels.
     */
    private fun constantTimeEquals(a: String, b: String): Boolean {
        if (a.length != b.length) return false
        var result = 0
        for (i in a.indices) {
            result = result or (a[i].code xor b[i].code)
        }
        return result == 0
    }

    /**
     * Generates a cryptographically random seed (16 bytes) in hexadecimal format.
     */
    fun generateRandomSeedHex(): String {
        val bytes = ByteArray(16)
        SecureRandom().nextBytes(bytes)
        val hexChars = "0123456789abcdef"
        val sb = StringBuilder(32)
        for (b in bytes) {
            val v = b.toInt() and 0xFF
            sb.append(hexChars[v shr 4])
            sb.append(hexChars[v and 0x0F])
        }
        return sb.toString()
    }

    fun hexToBytes(hex: String): ByteArray {
        val clean = hex.trim().lowercase()
        require(clean.length % 2 == 0) { "Hex string must have an even length" }
        val result = ByteArray(clean.length / 2)
        for (i in result.indices) {
            val hi = Character.digit(clean[i * 2], 16)
            val lo = Character.digit(clean[i * 2 + 1], 16)
            require(hi != -1 && lo != -1) { "Invalid hex character" }
            result[i] = ((hi shl 4) or lo).toByte()
        }
        return result
    }
}
