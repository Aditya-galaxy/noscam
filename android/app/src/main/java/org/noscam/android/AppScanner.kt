package org.noscam.android

import android.app.admin.DevicePolicyManager
import android.content.Context
import android.content.pm.ApplicationInfo
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Settings

/**
 * Reads the facts [AppRisk] judges, from the phone itself. Nothing leaves it.
 *
 * Seeing other apps at all needs QUERY_ALL_PACKAGES on Android 11+. Google Play
 * allows that for security apps whose core purpose is scanning installed apps,
 * which is this part of NoScam.
 */
class AppScanner(private val context: Context) {

    private val pm: PackageManager = context.packageManager

    @Suppress("DEPRECATION")
    private val flags = PackageManager.GET_PERMISSIONS or PackageManager.GET_SERVICES or
        PackageManager.GET_RECEIVERS

    fun scanAll(): List<Pair<AppFacts, Assessment>> {
        val active = activeCapabilities()
        @Suppress("DEPRECATION")
        val packages = pm.getInstalledPackages(flags)
        return packages
            .filter { it.packageName != context.packageName }
            .mapNotNull { info -> factsFor(info, active) }
            .map { it to AppRisk.assess(it) }
            .filter { it.second.level != RiskLevel.NONE }
            .sortedWith(compareByDescending<Pair<AppFacts, Assessment>> { it.second.level }
                .thenBy { it.first.label.lowercase() })
    }

    fun scanPackage(packageName: String): Pair<AppFacts, Assessment>? {
        val info = try {
            @Suppress("DEPRECATION")
            pm.getPackageInfo(packageName, flags)
        } catch (e: PackageManager.NameNotFoundException) {
            return null
        }
        val facts = factsFor(info, activeCapabilities()) ?: return null
        return facts to AppRisk.assess(facts)
    }

    private data class Active(
        val accessibility: Set<String>,
        val notificationListeners: Set<String>,
        val deviceAdmins: Set<String>,
    )

    /** Which packages hold the dangerous capabilities right now. */
    private fun activeCapabilities(): Active {
        fun packagesIn(setting: String): Set<String> =
            (Settings.Secure.getString(context.contentResolver, setting) ?: "")
                .split(':')
                .mapNotNull { it.substringBefore('/').takeIf(String::isNotBlank) }
                .toSet()

        val dpm = context.getSystemService(DevicePolicyManager::class.java)
        val admins = dpm?.activeAdmins?.map { it.packageName }?.toSet() ?: emptySet()
        return Active(
            accessibility = packagesIn("enabled_accessibility_services"),
            notificationListeners = packagesIn("enabled_notification_listeners"),
            deviceAdmins = admins,
        )
    }

    private fun factsFor(info: PackageInfo, active: Active): AppFacts? {
        val app = info.applicationInfo ?: return null
        val isSystem = app.flags and (ApplicationInfo.FLAG_SYSTEM or ApplicationInfo.FLAG_UPDATED_SYSTEM_APP) != 0

        val granted = mutableSetOf<String>()
        val requested = info.requestedPermissions ?: emptyArray()
        val grantedFlags = info.requestedPermissionsFlags ?: IntArray(0)
        for (i in requested.indices) {
            if (i < grantedFlags.size && grantedFlags[i] and PackageInfo.REQUESTED_PERMISSION_GRANTED != 0) {
                granted += requested[i]
            }
        }
        // Drawing over other apps and installing apps are special app-ops, not
        // runtime grants, so "requested" is the honest signal for those two.
        for (special in listOf("android.permission.SYSTEM_ALERT_WINDOW",
                               "android.permission.REQUEST_INSTALL_PACKAGES",
                               "android.permission.MANAGE_EXTERNAL_STORAGE")) {
            if (special in requested) granted += special
        }

        val services = info.services ?: emptyArray()
        val receivers = info.receivers ?: emptyArray()
        val (installer, initiator) = installSource(info.packageName)

        return AppFacts(
            packageName = info.packageName,
            label = app.loadLabel(pm).toString(),
            installer = installer,
            initiator = initiator,
            isSystem = isSystem,
            grantedPermissions = granted,
            activeAccessibility = info.packageName in active.accessibility,
            activeNotificationListener = info.packageName in active.notificationListeners,
            activeDeviceAdmin = info.packageName in active.deviceAdmins,
            declaresAccessibility = services.any {
                it.permission == "android.permission.BIND_ACCESSIBILITY_SERVICE"
            },
            declaresNotificationListener = services.any {
                it.permission == "android.permission.BIND_NOTIFICATION_LISTENER_SERVICE"
            },
            declaresDeviceAdmin = receivers.any {
                it.permission == "android.permission.BIND_DEVICE_ADMIN"
            },
        )
    }

    /** (installer, initiator). Android 11 added who *started* the install —
     *  WhatsApp, Chrome, a file manager — which is the provenance that matters. */
    private fun installSource(packageName: String): Pair<String?, String?> = try {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val source = pm.getInstallSourceInfo(packageName)
            source.installingPackageName to source.initiatingPackageName
        } else {
            @Suppress("DEPRECATION")
            pm.getInstallerPackageName(packageName) to null
        }
    } catch (e: Exception) {
        null to null
    }
}
