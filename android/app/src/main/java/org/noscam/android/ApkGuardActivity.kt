package org.noscam.android

import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Typeface
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.OpenableColumns
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import java.io.File

/**
 * Stands in front of the package installer.
 *
 * Spy and banking-trojan APKs mostly arrive as *files* in a chat — "Posting
 * list.pdf.apk", "Army welfare app", "Traffic challan", "Wedding invitation" —
 * not as links. When one is tapped, the messenger asks Android to open an
 * `application/vnd.android.package-archive`, and Android offers every app that
 * says it can: the system installer and, because of the intent filter in the
 * manifest, NoScam. Chosen as the default ("Always"), NoScam is what opens.
 *
 * It then says who sent the file and what the app would be able to do, and it
 * does not pass the file on. This is a refusal, not a hold, for the same reason
 * the desktop gate refuses remote-control installers: there is no version of
 * "someone sent me an app in a chat" that a second opinion makes safe, and an
 * "install anyway" button is the one the caller will tell the person to press.
 * The honest way through is the app store, and the screen says so.
 *
 * What it cannot do: stop an install started some other way — from a file
 * manager, or by a person who picks the system installer in the chooser. The
 * installed-app check ([AuditActivity]) is the second line for exactly that.
 */
class ApkGuardActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val uri = intent?.data
        val sender = callerPackage()
        val name = uri?.let { displayName(it) }
        render(name, sender, reasons = null)
        if (uri != null) {
            // Reading the APK can take a moment for a large file; do it off the
            // main thread and redraw with what it asks for.
            Thread {
                val reasons = inspect(uri, name, sender)
                runOnUiThread { if (!isFinishing) render(name, sender, reasons) }
            }.start()
        }
    }

    /** The app that asked Android to open this file. */
    private fun callerPackage(): String? {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP_MR1) {
            val ref = referrer
            if (ref != null && ref.scheme == "android-app") return ref.host
        }
        return callingPackage
    }

    private fun displayName(uri: Uri): String? = try {
        contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) c.getString(0) else null
        } ?: uri.lastPathSegment
    } catch (e: Exception) {
        uri.lastPathSegment
    }

    /** Copy the APK to private cache just long enough to read its manifest. */
    private fun inspect(uri: Uri, name: String?, sender: String?): List<String> {
        val tmp = File(cacheDir, "inspect.apk")
        try {
            contentResolver.openInputStream(uri)?.use { input ->
                tmp.outputStream().use { output ->
                    val buffer = ByteArray(64 * 1024)
                    var total = 0L
                    while (true) {
                        val read = input.read(buffer)
                        if (read < 0) break
                        total += read
                        if (total > MAX_APK_BYTES) break       // judge what we have
                        output.write(buffer, 0, read)
                    }
                }
            }
            @Suppress("DEPRECATION")
            val info = packageManager.getPackageArchiveInfo(
                tmp.path,
                PackageManager.GET_PERMISSIONS or PackageManager.GET_SERVICES or PackageManager.GET_RECEIVERS,
            )
            val requested = info?.requestedPermissions?.toSet() ?: emptySet()
            val services = info?.services ?: emptyArray()
            val receivers = info?.receivers ?: emptyArray()
            appLabel = info?.applicationInfo?.let { ai ->
                ai.sourceDir = tmp.path
                ai.publicSourceDir = tmp.path
                ai.loadLabel(packageManager).toString()
            }
            return AppRisk.assessApk(
                fileName = name,
                sender = sender,
                requestedPermissions = requested,
                declaresAccessibility = services.any { it.permission == "android.permission.BIND_ACCESSIBILITY_SERVICE" },
                declaresNotificationListener = services.any { it.permission == "android.permission.BIND_NOTIFICATION_LISTENER_SERVICE" },
                declaresDeviceAdmin = receivers.any { it.permission == "android.permission.BIND_DEVICE_ADMIN" },
            )
        } catch (e: Exception) {
            return AppRisk.assessApk(name, sender, emptySet(), false, false, false)
        } finally {
            tmp.delete()
        }
    }

    @Volatile private var appLabel: String? = null

    private fun render(name: String?, sender: String?, reasons: List<String>?) {
        val from = AppRisk.sourceName(sender)
        val root = ScrollView(this).apply {
            setBackgroundColor(Color.WHITE)
            isFillViewport = true
            fitsSystemWindows = true
        }
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 64, 48, 64)
        }
        fun text(value: String, size: Float, bold: Boolean = false, color: Int = Color.DKGRAY,
                 bottom: Int = 16) = TextView(this).apply {
            text = value
            textSize = size
            setTextColor(color)
            if (bold) setTypeface(null, Typeface.BOLD)
            setPadding(0, 0, 0, bottom)
        }

        layout.addView(text("NoScam stopped this", 13f, bottom = 12))
        layout.addView(text("Don't install apps that were sent to you", 22f, bold = true,
                            color = Color.BLACK, bottom = 20))
        val what = listOfNotNull(appLabel?.let { "\"$it\"" }, name).distinct().joinToString(" · ")
        if (what.isNotEmpty()) layout.addView(text(what, 14f, color = Color.GRAY, bottom = 20))

        layout.addView(text(
            (if (from != null) "This app was sent to you on $from. " else "") +
                "Apps sent in chats and messages are how scammers and spies take over phones: " +
                "they read bank and login codes, record calls, copy photos and documents, and " +
                "watch where you go. No bank, army office, courier, police or government " +
                "department sends an app in a message.",
            16f, color = Color.BLACK, bottom = 24))

        if (reasons == null) {
            layout.addView(text("Checking what this app would be able to do…", 14f))
        } else if (reasons.isNotEmpty()) {
            layout.addView(text("What we found:", 15f, bold = true, color = Color.BLACK, bottom = 12))
            for (reason in reasons) layout.addView(text("• $reason", 15f))
        }

        layout.addView(Button(this).apply {
            text = "Don't install"
            setBackgroundColor(Color.BLACK)
            setTextColor(Color.WHITE)
            setOnClickListener { finish() }
        })
        layout.addView(text(
            "If you really need this app, find it yourself in the Play Store by its name. " +
                "If someone is telling you to install it right now, that is the scam.",
            14f, bottom = 8).apply { setPadding(0, 24, 0, 8) })
        layout.addView(Button(this).apply {
            text = "Search the Play Store"
            setBackgroundColor(Color.TRANSPARENT)
            setTextColor(Color.DKGRAY)
            gravity = Gravity.CENTER
            setOnClickListener {
                val query = Uri.encode(appLabel ?: name?.substringBeforeLast('.') ?: "")
                try {
                    startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("market://search?q=$query")))
                } catch (e: Exception) {
                    // no store on this phone
                }
                finish()
            }
        })

        root.addView(layout)
        setContentView(root)
    }

    companion object {
        private const val MAX_APK_BYTES = 200L * 1024 * 1024
    }
}
