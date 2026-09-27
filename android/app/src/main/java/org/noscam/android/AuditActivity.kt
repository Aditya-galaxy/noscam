package org.noscam.android

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView

/**
 * The second line: apps already on the phone that arrived outside an app store
 * and can take it over, or that hold the screen or the codes wherever they came
 * from. Each one says why, and offers the two things a person can do about it.
 */
class AuditActivity : Activity() {

    override fun onResume() {
        super.onResume()
        render(null)
        Thread {
            val found = AppScanner(this).scanAll()
            runOnUiThread { if (!isFinishing) render(found) }
        }.start()
    }

    private fun render(found: List<Pair<AppFacts, Assessment>>?) {
        val root = ScrollView(this).apply {
            setBackgroundColor(Color.WHITE)
            fitsSystemWindows = true
        }
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 64, 48, 64)
        }
        fun text(value: String, size: Float, bold: Boolean = false, color: Int = Color.DKGRAY,
                 bottom: Int = 12) = TextView(this).apply {
            text = value
            textSize = size
            setTextColor(color)
            if (bold) setTypeface(null, Typeface.BOLD)
            setPadding(0, 0, 0, bottom)
        }

        layout.addView(text("Apps to check", 22f, bold = true, color = Color.BLACK, bottom = 16))

        when {
            found == null -> layout.addView(text("Looking at the apps on this phone…", 16f))
            found.isEmpty() -> layout.addView(text(
                "Nothing to worry about. Every app here came from an app store, and none of " +
                    "them can read your screen, your notifications or your messages.", 16f))
            else -> {
                val high = found.count { it.second.level == RiskLevel.HIGH }
                layout.addView(text(
                    if (high > 0) "$high ${if (high == 1) "app" else "apps"} could be spying on this " +
                        "phone or stealing codes. If you don't remember installing one yourself, " +
                        "remove it, then change your bank and email passwords from another device."
                    else "Nothing looks like a takeover, but these can do more than most apps. " +
                        "Check that you recognise each one.",
                    16f, color = Color.BLACK, bottom = 28))
                for ((facts, assessment) in found) addApp(layout, facts, assessment, ::text)
            }
        }

        root.addView(layout)
        setContentView(root)
    }

    private fun addApp(layout: LinearLayout, facts: AppFacts, assessment: Assessment,
                       text: (String, Float, Boolean, Int, Int) -> TextView) {
        val tag = if (assessment.level == RiskLevel.HIGH) "Remove unless you installed it yourself"
                  else "Worth checking"
        layout.addView(text(facts.label, 18f, true, Color.BLACK, 4))
        layout.addView(text(tag, 13f, false, Color.GRAY, 8))
        for (reason in assessment.reasons) layout.addView(text("• It $reason", 15f, false, Color.DKGRAY, 6))

        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, 8, 0, 36)
        }
        row.addView(Button(this).apply {
            text = "Remove"
            setBackgroundColor(Color.BLACK)
            setTextColor(Color.WHITE)
            setOnClickListener {
                // A device administrator cannot be uninstalled until it is
                // switched off, so send the person where that happens first.
                val intent = if (facts.activeDeviceAdmin) Intent(Settings.ACTION_SECURITY_SETTINGS)
                             else Intent(Intent.ACTION_DELETE, Uri.parse("package:${facts.packageName}"))
                try { startActivity(intent) } catch (e: Exception) { openDetails(facts.packageName) }
            }
        })
        row.addView(Button(this).apply {
            text = "App settings"
            setBackgroundColor(Color.TRANSPARENT)
            setTextColor(Color.DKGRAY)
            setOnClickListener { openDetails(facts.packageName) }
        })
        layout.addView(row)
    }

    private fun openDetails(packageName: String) {
        try {
            startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                                 Uri.parse("package:$packageName")))
        } catch (e: Exception) {
            // settings unavailable; nothing else to offer
        }
    }
}
