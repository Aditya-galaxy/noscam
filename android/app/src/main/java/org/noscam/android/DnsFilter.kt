package org.noscam.android

enum class DnsAction {
    ALLOW,
    SINKHOLE
}

data class DnsVerdict(
    val action: DnsAction,
    val domain: String,
    val reason: String? = null
)

/**
 * On-device DNS security evaluator.
 *
 * Examines requested hostnames against NoScam link safety invariants before
 * any connection is made:
 *   - Raw numeric IP addresses
 *   - Punycode homograph attacks (xn--)
 *   - High-risk disposable / temporary scam TLDs
 *   - Remote access tools (AnyDesk, TeamViewer) pushed on phone calls
 *   - Brand impersonation across subdomains or lookalike domains
 */
object DnsFilter {

    private val SUSPICIOUS_TLDS = setOf(
        ".xyz", ".top", ".tk", ".cf", ".click", ".vip", ".loan", ".work", ".gq", ".ml", ".date"
    )

    private val REMOTE_ACCESS_DOMAINS = setOf(
        "anydesk.com", "teamviewer.com", "quicksupport.me", "ultraviewer.net",
        "rustdesk.com", "ammyy.com", "logmein.com"
    )

    private val BRAND_RULES = mapOf(
        "paypal" to listOf("paypal.com"),
        "chase" to listOf("chase.com"),
        "wells" to listOf("wellsfargo.com"),
        "sbi" to listOf("sbi.co.in", "onlinesbi.sbi", "onlinesbi.com"),
        "hdfc" to listOf("hdfcbank.com"),
        "paytm" to listOf("paytm.com"),
        "amazon" to listOf("amazon.com", "amazon.in", "amazon.co.uk"),
        "netflix" to listOf("netflix.com"),
        "microsoft" to listOf("microsoft.com", "live.com", "office.com"),
        "google" to listOf("google.com", "google.co.in", "youtube.com"),
        "apple" to listOf("apple.com", "icloud.com")
    )

    fun assess(rawDomain: String): DnsVerdict {
        val domain = rawDomain.trim().trimEnd('.').lowercase()
        if (domain.isEmpty()) {
            return DnsVerdict(DnsAction.ALLOW, domain)
        }

        // 1. Raw numeric IP addresses queried as hostname
        if (domain.matches(Regex("^\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}$"))) {
            return DnsVerdict(
                DnsAction.SINKHOLE,
                domain,
                "Numbered IP address used directly as website destination"
            )
        }

        // 2. Punycode lookalikes
        if (domain.contains("xn--")) {
            return DnsVerdict(
                DnsAction.SINKHOLE,
                domain,
                "Punycode domain disguised with foreign character lookalikes"
            )
        }

        // 3. Remote access tools (often pushed by support scammers on phone calls)
        for (rat in REMOTE_ACCESS_DOMAINS) {
            if (domain == rat || domain.endsWith(".$rat")) {
                return DnsVerdict(
                    DnsAction.SINKHOLE,
                    domain,
                    "Remote access software ($rat) pushed during phone calls"
                )
            }
        }

        // 4. Brand impersonation across subdomains or domain names
        for ((brand, legitimateHosts) in BRAND_RULES) {
            if (domain.contains(brand)) {
                val isLegitimate = legitimateHosts.any { domain == it || domain.endsWith(".$it") }
                if (!isLegitimate) {
                    return DnsVerdict(
                        DnsAction.SINKHOLE,
                        domain,
                        "Brand impersonation: claims to be $brand on an unverified domain"
                    )
                }
            }
        }

        // 5. High-risk disposable / temporary scam TLDs
        if (SUSPICIOUS_TLDS.any { domain.endsWith(it) }) {
            return DnsVerdict(
                DnsAction.SINKHOLE,
                domain,
                "Uncommon domain extension frequently associated with temporary scam portals"
            )
        }

        return DnsVerdict(DnsAction.ALLOW, domain)
    }
}
