package org.noscam.android

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import java.net.URI

/**
 * Isolated, disarmed container activity for viewing inbound or suspicious links.
 *
 * Primary browser profiles hold session cookies, banking credentials, and run full
 * V8/WebKit JIT compilers vulnerable to 1-click zero-days (e.g. BLASTPASS, Pegasus,
 * Predator lures).
 *
 * This activity disarms that attack surface:
 * 1. JavaScript disabled by default (no JIT, no WebAssembly, no prototype pollution).
 * 2. Zero device permissions granted (camera, mic, location, storage denied unconditionally).
 * 3. Ephemeral isolation (no DOM storage, no cookies preserved, cache cleared on exit).
 * 4. Tracking and fingerprinting parameters stripped from the URL.
 * 5. DNS and lookalike domain verification via [DnsFilter] before loading.
 */
class DisarmedBrowserActivity : Activity() {

    private lateinit var webView: WebView
    private lateinit var urlView: TextView
    private lateinit var statusView: TextView
    private lateinit var btnToggleJs: Button
    private var isJsEnabled = false
    private var currentUrl: String = ""

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val rawUrl = intent.getStringExtra(EXTRA_URL) ?: intent.dataString ?: ""
        if (rawUrl.isBlank()) {
            finish()
            return
        }

        currentUrl = cleanUrl(rawUrl)

        val rootLayout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.WHITE)
            fitsSystemWindows = true
        }

        // Header / Security Banner
        val headerLayout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 32, 32, 20)
            setBackgroundColor(Color.parseColor("#1A1A1A"))
        }

        val bannerTitle = TextView(this).apply {
            text = "🛡️ NoScam Disarmed Safe Preview"
            textSize = 15f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.WHITE)
        }
        headerLayout.addView(bannerTitle)

        statusView = TextView(this).apply {
            text = "JS: OFF · Zero Permissions · Isolated Sandbox"
            textSize = 12f
            setTextColor(Color.parseColor("#81C784"))
            setPadding(0, 4, 0, 8)
        }
        headerLayout.addView(statusView)

        urlView = TextView(this).apply {
            text = currentUrl
            textSize = 13f
            setTextColor(Color.LTGRAY)
            maxLines = 2
        }
        headerLayout.addView(urlView)

        rootLayout.addView(headerLayout)

        // Pre-check DNS & Host reputation
        val host = try {
            URI(currentUrl).host?.lowercase() ?: ""
        } catch (e: Exception) {
            ""
        }

        val dnsCheck = DnsFilter.assess(host)
        if (dnsCheck.action == DnsAction.SINKHOLE) {
            renderBlockedScreen(rootLayout, dnsCheck.reason ?: "Suspicious or malicious destination")
            setContentView(rootLayout)
            return
        }

        // Hardened WebView
        webView = WebView(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                0,
                1.0f
            )
        }

        configureHardenedSettings(webView.settings)

        webView.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest?) {
                request?.deny()
            }
        }

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean {
                val nextUrl = request?.url?.toString() ?: return false
                val nextHost = try { URI(nextUrl).host?.lowercase() ?: "" } catch (e: Exception) { "" }
                val nextDnsCheck = DnsFilter.assess(nextHost)
                if (nextDnsCheck.action == DnsAction.SINKHOLE) {
                    renderBlockedScreen(rootLayout, nextDnsCheck.reason ?: "Target domain is blocked")
                    return true
                }
                currentUrl = cleanUrl(nextUrl)
                urlView.text = currentUrl
                return false
            }
        }

        rootLayout.addView(webView)

        // Action Toolbar
        val toolbarLayout = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(24, 16, 24, 24)
            setBackgroundColor(Color.parseColor("#F5F5F5"))
            gravity = Gravity.CENTER_VERTICAL
        }

        val btnClose = Button(this).apply {
            text = "Close"
            setBackgroundColor(Color.LTGRAY)
            setTextColor(Color.BLACK)
            setOnClickListener { finish() }
        }
        toolbarLayout.addView(btnClose)

        btnToggleJs = Button(this).apply {
            text = "Enable JS"
            setBackgroundColor(Color.TRANSPARENT)
            setTextColor(Color.DKGRAY)
            setOnClickListener { toggleJavaScript() }
        }
        toolbarLayout.addView(btnToggleJs)

        val btnSystemBrowser = Button(this).apply {
            text = "Open in Browser"
            setBackgroundColor(Color.TRANSPARENT)
            setTextColor(Color.DKGRAY)
            setOnClickListener {
                val intent = Intent(Intent.ACTION_VIEW, Uri.parse(currentUrl)).apply {
                    addCategory(Intent.CATEGORY_BROWSABLE)
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                startActivity(intent)
                finish()
            }
        }
        toolbarLayout.addView(btnSystemBrowser)

        rootLayout.addView(toolbarLayout)
        setContentView(rootLayout)

        webView.loadUrl(currentUrl)
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun configureHardenedSettings(settings: WebSettings) {
        settings.javaScriptEnabled = false
        settings.domStorageEnabled = false
        settings.databaseEnabled = false
        settings.allowFileAccess = false
        settings.allowContentAccess = false
        settings.setGeolocationEnabled(false)
        settings.mediaPlaybackRequiresUserGesture = true
        settings.cacheMode = WebSettings.LOAD_NO_CACHE
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            settings.safeBrowsingEnabled = true
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun toggleJavaScript() {
        isJsEnabled = !isJsEnabled
        webView.settings.javaScriptEnabled = isJsEnabled
        if (isJsEnabled) {
            btnToggleJs.text = "Disable JS"
            statusView.text = "JS: ON (Restricted) · Zero Permissions · Isolated Sandbox"
            statusView.setTextColor(Color.parseColor("#FFB74D"))
        } else {
            btnToggleJs.text = "Enable JS"
            statusView.text = "JS: OFF · Zero Permissions · Isolated Sandbox"
            statusView.setTextColor(Color.parseColor("#81C784"))
        }
        webView.reload()
    }

    private fun renderBlockedScreen(rootLayout: LinearLayout, reason: String) {
        val scroll = ScrollView(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
            setBackgroundColor(Color.WHITE)
            isFillViewport = true
        }
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 80, 48, 64)
            gravity = Gravity.CENTER_HORIZONTAL
        }

        val warningBadge = TextView(this).apply {
            text = "🛑 ACCESS BLOCKED"
            textSize = 20f
            setTypeface(null, Typeface.BOLD)
            setTextColor(Color.RED)
            setPadding(0, 0, 0, 16)
        }
        layout.addView(warningBadge)

        val reasonText = TextView(this).apply {
            text = "NoScam DNS Guardian intercepted this connection:\n\n$reason\n\nThis domain has been sinkholed to prevent remote access exploitation or credential theft."
            textSize = 15f
            setTextColor(Color.DKGRAY)
            setPadding(0, 0, 0, 32)
        }
        layout.addView(reasonText)

        val btnExit = Button(this).apply {
            text = "Close Safely"
            setBackgroundColor(Color.BLACK)
            setTextColor(Color.WHITE)
            setOnClickListener { finish() }
        }
        layout.addView(btnExit)

        scroll.addView(layout)
        rootLayout.addView(scroll)
    }

    override fun onDestroy() {
        if (::webView.isInitialized) {
            webView.clearCache(true)
            webView.clearHistory()
            try {
                CookieManager.getInstance().removeAllCookies(null)
            } catch (e: Exception) {
                // Ignore if cookie manager unavailable
            }
        }
        super.onDestroy()
    }

    companion object {
        const val EXTRA_URL = "extra_url"

        private val TRACKING_PARAMS = setOf(
            "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "fbclid", "gclid", "msclkid", "mc_eid", "dclid", "ref", "source", "campaign"
        )

        /**
         * Pure function to strip invasive click identifiers and tracking query params
         * from inbound links.
         */
        fun cleanUrl(rawUrl: String): String {
            return try {
                val uri = URI(rawUrl)
                val query = uri.rawQuery ?: return rawUrl
                val filteredQuery = query.split("&")
                    .map { it.split("=", limit = 2) }
                    .filter { parts ->
                        val key = parts[0].lowercase()
                        key !in TRACKING_PARAMS && !key.startsWith("utm_")
                    }
                    .joinToString("&") { parts ->
                        if (parts.size == 2) "${parts[0]}=${parts[1]}" else parts[0]
                    }

                URI(
                    uri.scheme,
                    uri.authority,
                    uri.path,
                    if (filteredQuery.isEmpty()) null else filteredQuery,
                    uri.fragment
                ).toString()
            } catch (e: Exception) {
                rawUrl
            }
        }
    }
}
