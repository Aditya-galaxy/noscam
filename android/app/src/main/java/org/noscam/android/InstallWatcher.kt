package org.noscam.android

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.job.JobInfo
import android.app.job.JobParameters
import android.app.job.JobScheduler
import android.app.job.JobService
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.os.Build

/**
 * Notices apps installed since it last looked, and says so when one of them can
 * take the phone over.
 *
 * Android no longer lets an app be woken for every install (implicit broadcasts
 * were cut in Android 8), and keeping a service alive for it would cost battery
 * and a permanent notification. So this runs as a periodic job — about every
 * half hour, and whenever NoScam is opened — and compares the installed apps
 * with the ones it saw last time. A spy app installed at 10:00 is flagged by
 * about 10:30: after the install, but usually before the damage is complete,
 * and in time to remove it and change passwords.
 */
object InstallWatcher {

    private const val JOB_ID = 4201
    private const val PREFS = "install_watcher"
    private const val KEY_KNOWN = "known_packages"
    private const val CHANNEL = "new_apps"

    fun schedule(context: Context) {
        val scheduler = context.getSystemService(JobScheduler::class.java) ?: return
        if (scheduler.allPendingJobs.any { it.id == JOB_ID }) return
        val job = JobInfo.Builder(JOB_ID, ComponentName(context, InstallWatcherJob::class.java))
            .setPeriodic(30 * 60 * 1000L)
            .setPersisted(true)                  // survives a reboot (RECEIVE_BOOT_COMPLETED)
            .build()
        scheduler.schedule(job)
    }

    /** Compare with last time; notify about new apps worth a look. */
    fun check(context: Context) {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val current = userPackages(context)
        val known = prefs.getStringSet(KEY_KNOWN, null)
        prefs.edit().putStringSet(KEY_KNOWN, current).apply()
        if (known == null) return                // first run: this is the baseline

        val scanner = AppScanner(context)
        for (pkg in current - known) {
            val (facts, assessment) = scanner.scanPackage(pkg) ?: continue
            if (assessment.level != RiskLevel.NONE) notify(context, facts, assessment)
        }
    }

    @Suppress("DEPRECATION")
    private fun builder(context: Context): Notification.Builder =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) Notification.Builder(context, CHANNEL)
        else Notification.Builder(context)

    private fun userPackages(context: Context): Set<String> =
        context.packageManager.getInstalledApplications(0)
            .filter { it.flags and ApplicationInfo.FLAG_SYSTEM == 0 }
            .map { it.packageName }
            .toSet()

    private fun notify(context: Context, facts: AppFacts, assessment: Assessment) {
        val manager = context.getSystemService(NotificationManager::class.java) ?: return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(NotificationChannel(
                CHANNEL, "New apps that need checking", NotificationManager.IMPORTANCE_HIGH))
        }
        val open = PendingIntent.getActivity(
            context, facts.packageName.hashCode(),
            Intent(context, AuditActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)

        val title = if (assessment.level == RiskLevel.HIGH) "\"${facts.label}\" could be spying on this phone"
                    else "Check the new app \"${facts.label}\""
        val body = assessment.reasons.take(2).joinToString(". ") { "It $it" } + "."

        val notification = builder(context)
            .setSmallIcon(android.R.drawable.stat_sys_warning)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(Notification.BigTextStyle().bigText(body))
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        try {
            manager.notify(facts.packageName.hashCode(), notification)
        } catch (e: SecurityException) {
            // notifications not allowed; the audit screen still shows it
        }
    }
}

class InstallWatcherJob : JobService() {
    override fun onStartJob(params: JobParameters): Boolean {
        Thread {
            try { InstallWatcher.check(this) } finally { jobFinished(params, false) }
        }.start()
        return true
    }

    override fun onStopJob(params: JobParameters): Boolean = true
}
