package org.noscam.android

import android.app.Activity
import android.app.role.RoleManager
import android.content.ActivityNotFoundException
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
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

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)          // so onResume sees the link, not the launch
        handleIntent(intent)
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
            // Targeting API 35+ draws edge to edge; keep text clear of the bars.
            fitsSystemWindows = true
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

    private fun isDefaultLinkHandler(): Boolean {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val roles = getSystemService(RoleManager::class.java)
            return roles != null && roles.isRoleHeld(RoleManager.ROLE_BROWSER)
        }
        val probe = Intent(Intent.ACTION_VIEW, Uri.parse("https://example.com"))
        val resolved = packageManager.resolveActivity(probe, PackageManager.MATCH_DEFAULT_ONLY)
        return resolved?.activityInfo?.packageName == packageName
    }

    /** Since Android 12, a tapped link goes to the default browser and nowhere
     *  else, so checking every link means being chosen as the default. The
     *  system shows its own dialog; the person can undo it in Settings. */
    private fun requestDefaultLinkHandler() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val roles = getSystemService(RoleManager::class.java)
            if (roles != null && roles.isRoleAvailable(RoleManager.ROLE_BROWSER)) {
                @Suppress("DEPRECATION")
                startActivityForResult(roles.createRequestRoleIntent(RoleManager.ROLE_BROWSER), REQUEST_ROLE)
                return
            }
        }
        try {
            startActivity(Intent(Settings.ACTION_MANAGE_DEFAULT_APPS_SETTINGS))
        } catch (e: ActivityNotFoundException) {
            startActivity(Intent(Settings.ACTION_SETTINGS))
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == REQUEST_ROLE) showLauncherDashboard()
    }

    override fun onResume() {
        super.onResume()
        if (extractUrl(intent).isNullOrBlank()) showLauncherDashboard()
    }

    private fun showLauncherDashboard() {
        val active = isDefaultLinkHandler()

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(48, 64, 48, 64)
            setBackgroundColor(Color.WHITE)
            fitsSystemWindows = true
        }

        val title = TextView(this).apply {
            text = "NoScam"
            textSize = 24f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.BLACK)
        }
        layout.addView(title)

        val subtitle = TextView(this).apply {
            text = if (active) {
                "Checking every link you tap.\n\nWhen you tap a link in WhatsApp, SMS or email, " +
                    "NoScam looks at it first, then opens it in your usual browser."
            } else {
                "Not checking tapped links yet.\n\nAndroid sends every tapped link to one app, " +
                    "the default browser. To check links before they open, choose NoScam there. " +
                    "It hands every link on to your usual browser straight after.\n\n" +
                    "Until then, you can still check a link with Share → NoScam."
            }
            textSize = 16f
            setTextColor(Color.DKGRAY)
            gravity = Gravity.CENTER
            setPadding(0, 16, 0, 32)
        }
        layout.addView(subtitle)

        if (!active) {
            val btnEnable = Button(this).apply {
                text = "Check every link I tap"
                setBackgroundColor(Color.BLACK)
                setTextColor(Color.WHITE)
                setOnClickListener { requestDefaultLinkHandler() }
            }
            layout.addView(btnEnable)
        }

        val btnAbout = Button(this).apply {
            text = "How NoScam works"
            setBackgroundColor(Color.TRANSPARENT)
            setTextColor(Color.DKGRAY)
            setOnClickListener { openInBrowser("https://aditya-galaxy.github.io/noscam/") }
        }
        layout.addView(btnAbout)

        setContentView(layout)
    }

    /** Hand a link to a real browser — never back to ourselves. Once NoScam is
     *  the default browser, a plain ACTION_VIEW would come straight back here. */
    private fun openInBrowser(url: String) {
        val view = Intent(Intent.ACTION_VIEW, Uri.parse(url)).apply {
            addCategory(Intent.CATEGORY_BROWSABLE)
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }
        val target = chooseBrowser()
        if (target != null) {
            view.component = target
        } else if (isDefaultLinkHandler()) {
            // No other browser installed: there is nowhere safe to send it.
            return
        }
        try {
            startActivity(view)
        } catch (e: ActivityNotFoundException) {
            // nothing can open it
        }
    }

    private fun chooseBrowser(): ComponentName? {
        val probe = Intent(Intent.ACTION_VIEW, Uri.parse("https://example.com"))
            .addCategory(Intent.CATEGORY_BROWSABLE)
        val candidates = packageManager.queryIntentActivities(probe, PackageManager.MATCH_ALL)
            .map { it.activityInfo }
            .filter { it.packageName != packageName && it.exported }
        val preferred = PREFERRED_BROWSERS.firstNotNullOfOrNull { pkg ->
            candidates.firstOrNull { it.packageName == pkg }
        } ?: candidates.firstOrNull()
        return preferred?.let { ComponentName(it.packageName, it.name) }
    }

    companion object {
        private const val REQUEST_ROLE = 1
        private val PREFERRED_BROWSERS = listOf(
            "com.android.chrome", "com.sec.android.app.sbrowser", "org.mozilla.firefox",
            "com.microsoft.emmx", "com.brave.browser", "com.opera.browser",
        )
    }
}
