package org.noscam.android

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import java.net.URI
import java.util.regex.Pattern

class MainActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handleIntent(intent)
    }

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        intent?.let { handleIntent(it) }
    }

    private fun handleIntent(intent: Intent) {
        val url = extractUrl(intent)
        if (url.isNullOrBlank()) {
            showLauncherDashboard()
            return
        }

        val warnings = evaluateUrl(url)
        if (warnings.isEmpty()) {
            openInBrowser(url)
            finish()
        } else {
            showWarningDialog(url, warnings)
        }
    }

    private fun extractUrl(intent: Intent): String? {
        if (Intent.ACTION_VIEW == intent.action && intent.data != null) {
            return intent.data.toString()
        }
        if (Intent.ACTION_SEND == intent.action && "text/plain" == intent.type) {
            val sharedText = intent.getStringExtra(Intent.EXTRA_TEXT) ?: return null
            val matcher = Pattern.compile("https?://\\S+").matcher(sharedText)
            if (matcher.find()) {
                return matcher.group()
            }
        }
        return null
    }

    private fun evaluateUrl(urlString: String): List<String> {
        val warnings = mutableListOf<String>()
        try {
            val uri = URI(urlString)
            val host = uri.host?.lowercase() ?: ""
            val path = uri.path?.lowercase() ?: ""

            // 1. APK download check
            if (path.endsWith(".apk") || urlString.contains(".apk?")) {
                warnings.add("Downloads an app installer directly (.apk) — often used to install remote-access or fake banking apps.")
            }

            // 2. IP address check
            if (host.matches(Regex("^\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}\\.\\d{1,3}$"))) {
                warnings.add("Uses a numbered IP address instead of a recognized website name.")
            }

            // 3. Punycode lookalike check
            if (host.contains("xn--")) {
                warnings.add("Contains foreign character lookalikes (punycode) used to imitate legitimate brands.")
            }

            // 4. Suspicious TLD / Brand impersonation in subdomains
            val suspiciousTlds = listOf(".xyz", ".top", ".tk", ".cf", ".click", ".vip", ".loan")
            if (suspiciousTlds.any { host.endsWith(it) }) {
                warnings.add("Uses an uncommon domain extension frequently associated with temporary scam portals.")
            }
            val legitimateBrandDomains = mapOf(
                "paypal" to listOf("paypal.com"),
                "chase" to listOf("chase.com"),
                "wells" to listOf("wellsfargo.com"),
                "sbi" to listOf("sbi.co.in", "onlinesbi.sbi", "onlinesbi.com"),
                "hdfc" to listOf("hdfcbank.com"),
                "paytm" to listOf("paytm.com"),
                "amazon" to listOf("amazon.com", "amazon.in", "amazon.co.uk"),
                "netflix" to listOf("netflix.com")
            )
            for ((brand, validDomains) in legitimateBrandDomains) {
                if (host.contains(brand)) {
                    val isLegitimate = validDomains.any { host == it || host.endsWith(".$it") }
                    if (!isLegitimate) {
                        warnings.add("The name '$brand' appears in this address, but it is not an official $brand website.")
                        break
                    }
                }
            }

            // 5. UPI collect request link
            if (urlString.startsWith("upi:") || urlString.contains("upi://")) {
                val hasBlankAmount = !urlString.contains("am=") || urlString.contains("am=&") || urlString.endsWith("am=") || urlString.contains("am=0")
                if (hasBlankAmount) {
                    warnings.add("UPI request leaves the amount blank or asks for approval — approving UPI requests only sends money out, never receives it.")
                } else if (urlString.contains("tr=") || urlString.contains("mode=02") || urlString.contains("recur=")) {
                    warnings.add("UPI request asks for your approval or recurring mandate — receiving money never requires your PIN.")
                }
            }
        } catch (e: Exception) {
            warnings.add("Invalid or unreadable URL format.")
        }
        return warnings
    }

    private fun showWarningDialog(url: String, warnings: List<String>) {
        val root = ScrollView(this).apply {
            setBackgroundColor(Color.WHITE)
            isFillViewport = true
        }

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 80, 48, 64)
        }

        val tag = TextView(this).apply {
            text = "NoScam · Link Warning"
            textSize = 13f
            setTextColor(Color.DKGRAY)
        }
        layout.addView(tag)

        val title = TextView(this).apply {
            text = "Wait before opening this link"
            textSize = 22f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.BLACK)
            setPadding(0, 16, 0, 24)
        }
        layout.addView(title)

        val urlView = TextView(this).apply {
            text = url
            textSize = 14f
            setTextColor(Color.GRAY)
            setPadding(0, 0, 0, 24)
        }
        layout.addView(urlView)

        val reasonHeader = TextView(this).apply {
            text = "Why this was held:"
            textSize = 15f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.BLACK)
            setPadding(0, 0, 0, 12)
        }
        layout.addView(reasonHeader)

        for (warning in warnings) {
            val item = TextView(this).apply {
                text = "• $warning"
                textSize = 15f
                setTextColor(Color.DKGRAY)
                setPadding(0, 0, 0, 16)
            }
            layout.addView(item)
        }

        val btnCancel = Button(this).apply {
            text = "Cancel (Safe)"
            setBackgroundColor(Color.BLACK)
            setTextColor(Color.WHITE)
            setOnClickListener { finish() }
        }
        layout.addView(btnCancel)

        val btnOpen = Button(this).apply {
            text = "Open Anyway"
            setBackgroundColor(Color.TRANSPARENT)
            setTextColor(Color.DKGRAY)
            setOnClickListener {
                openInBrowser(url)
                finish()
            }
        }
        layout.addView(btnOpen)

        root.addView(layout)
        setContentView(root)
    }

    private fun showLauncherDashboard() {
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(48, 64, 48, 64)
            setBackgroundColor(Color.WHITE)
        }

        val title = TextView(this).apply {
            text = "NoScam Mobile"
            textSize = 24f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.BLACK)
        }
        layout.addView(title)

        val subtitle = TextView(this).apply {
            text = "Link interception is active.\nWhen a link is tapped in WhatsApp or SMS, NoScam checks it before opening."
            textSize = 15f
            setTextColor(Color.DKGRAY)
            gravity = Gravity.CENTER
            setPadding(0, 16, 0, 32)
        }
        layout.addView(subtitle)

        val btnDashboard = Button(this).apply {
            text = "Open Guardian Dashboard"
            setBackgroundColor(Color.BLACK)
            setTextColor(Color.WHITE)
            setOnClickListener {
                openInBrowser("https://aditya-galaxy.github.io/noscam/app/")
            }
        }
        layout.addView(btnDashboard)

        setContentView(layout)
    }

    private fun openInBrowser(url: String) {
        val browserIntent = Intent(Intent.ACTION_VIEW, Uri.parse(url)).apply {
            addCategory(Intent.CATEGORY_BROWSABLE)
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }
        startActivity(browserIntent)
    }
}
