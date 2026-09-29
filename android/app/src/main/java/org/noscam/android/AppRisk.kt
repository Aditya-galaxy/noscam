package org.noscam.android

/**
 * Which installed apps deserve a second look, and why — in words a person can
 * check against what they remember installing.
 *
 * Pure Kotlin, no Android imports, so the rules are unit-tested on their own.
 * The facts are gathered by [AppScanner]; this file only judges them.
 *
 * The rule of thumb is the same one the desktop gate uses: what matters is not
 * whether an app is "known bad" — a spy APK is new every time — but how it
 * arrived and what it can do. An app that came in a WhatsApp message and can
 * read your notifications is the attack, whatever it calls itself.
 */

data class AppFacts(
    val packageName: String,
    val label: String,
    /** The store or installer that installed it, e.g. com.android.vending. */
    val installer: String?,
    /** The app that started the install, e.g. com.whatsapp (Android 11+). */
    val initiator: String?,
    val isSystem: Boolean,
    /** Permissions currently granted (runtime) or held (install-time). */
    val grantedPermissions: Set<String>,
    /** Capabilities that are switched on right now, not merely declared. */
    val activeAccessibility: Boolean = false,
    val activeNotificationListener: Boolean = false,
    val activeDeviceAdmin: Boolean = false,
    /** Declared, even if not switched on: the app is built to ask for it. */
    val declaresAccessibility: Boolean = false,
    val declaresNotificationListener: Boolean = false,
    val declaresDeviceAdmin: Boolean = false,
    /** Shows up in the app drawer. Spyware hides its icon after first launch. */
    val hasLauncherIcon: Boolean = true,
    /** Can act as a contactless card (HostApduService) — "ghost tapping". */
    val declaresCardEmulation: Boolean = false,
    /** Starts itself when the phone boots. */
    val startsAtBoot: Boolean = false,
    /** Holds Device Owner authority (enterprise MDM or rogue root profile). */
    val isDeviceOwner: Boolean = false,
    /** Holds Profile Owner authority (work profile MDM). */
    val isProfileOwner: Boolean = false,
    /** Epoch timestamp (ms) when app was first installed, or 0 if unknown. */
    val firstInstallTimeMs: Long = 0L,
)

enum class RiskLevel { NONE, WATCH, HIGH }

data class Assessment(
    val level: RiskLevel,
    val sideloaded: Boolean,
    /** Human name of the messenger or browser it came from, if it came from one. */
    val cameFrom: String?,
    val reasons: List<String>,
)

object AppRisk {

    /** Installers that review what they distribute. Anything else is a sideload. */
    val TRUSTED_STORES = setOf(
        "com.android.vending",                // Google Play
        "com.sec.android.app.samsungapps",    // Galaxy Store
        "com.huawei.appmarket",
        "com.xiaomi.mipicks", "com.xiaomi.market",
        "com.heytap.market", "com.oppo.market",
        "com.vivo.appstore",
        "com.amazon.venezia",
        "com.google.android.packageinstaller.managed", // enterprise / MDM
    )

    /** Where a sideloaded APK came from, when it came from a conversation. */
    val MESSENGERS = mapOf(
        "com.whatsapp" to "WhatsApp",
        "com.whatsapp.w4b" to "WhatsApp Business",
        "org.telegram.messenger" to "Telegram",
        "org.telegram.messenger.web" to "Telegram",
        "org.thunderdog.challegram" to "Telegram X",
        "org.thoughtcrime.securesms" to "Signal",
        "com.google.android.apps.messaging" to "Messages",
        "com.samsung.android.messaging" to "Samsung Messages",
        "com.facebook.orca" to "Messenger",
        "com.instagram.android" to "Instagram",
        "com.snapchat.android" to "Snapchat",
        "com.discord" to "Discord",
        "com.truecaller" to "Truecaller",
        "com.google.android.gm" to "Gmail",
        "com.microsoft.office.outlook" to "Outlook",
        "jp.naver.line.android" to "LINE",
        "com.imo.android.imoim" to "imo",
    )

    val BROWSERS = mapOf(
        "com.android.chrome" to "Chrome",
        "com.sec.android.app.sbrowser" to "Samsung Internet",
        "org.mozilla.firefox" to "Firefox",
        "com.microsoft.emmx" to "Edge",
        "com.brave.browser" to "Brave",
        "com.opera.browser" to "Opera",
        "com.opera.mini.native" to "Opera Mini",
        "com.UCMobile.intl" to "UC Browser",
    )

    /** Apps that hand live control of the phone to whoever has the code. */
    val REMOTE_ACCESS = mapOf(
        "com.anydesk.anydeskandroid" to "AnyDesk",
        "com.teamviewer.quicksupport.market" to "TeamViewer QuickSupport",
        "com.teamviewer.host.market" to "TeamViewer Host",
        "com.carriez.flutter_hbb" to "RustDesk",
        "com.sand.airdroid" to "AirDroid",
        "com.sand.airdroidbiz" to "AirDroid Business",
        "com.rsupport.mobizen.sec" to "Mobizen",
        "com.splashtop.remote.pad.v2" to "Splashtop",
        "net.soti.mobicontrol.androidwork" to "SOTI",
        "com.remotepc.viewer" to "RemotePC",
        "com.logmein.rescuemobile" to "LogMeIn Rescue",
    )

    private const val P = "android.permission."

    /** What each permission lets an app do to you, said plainly. */
    val SENSITIVE_PERMISSIONS = linkedMapOf(
        "${P}READ_SMS" to "can read your text messages, including bank and login codes",
        "${P}RECEIVE_SMS" to "can see text messages as they arrive, including one-time codes",
        "${P}SEND_SMS" to "can send text messages from your number",
        "${P}READ_CALL_LOG" to "can read who you call and who calls you",
        "${P}RECORD_AUDIO" to "can record through the microphone",
        "${P}CAMERA" to "can take photos and video",
        "${P}ACCESS_FINE_LOCATION" to "can see exactly where you are",
        "${P}ACCESS_BACKGROUND_LOCATION" to "can track your location when you are not using it",
        "${P}READ_CONTACTS" to "can copy your contacts",
        "${P}READ_EXTERNAL_STORAGE" to "can read your photos and files",
        "${P}READ_MEDIA_IMAGES" to "can read your photos",
        "${P}MANAGE_EXTERNAL_STORAGE" to "can read every file on the phone",
        "${P}SYSTEM_ALERT_WINDOW" to "can draw over other apps — a fake login screen on top of your bank",
        "${P}REQUEST_INSTALL_PACKAGES" to "can install other apps",
        "${P}READ_PHONE_STATE" to "can read your phone number and call state",
    )

    /** The permissions that turn a sideloaded app into a spy or a thief. */
    private val TAKEOVER_PERMISSIONS = setOf(
        "${P}READ_SMS", "${P}RECEIVE_SMS", "${P}SEND_SMS", "${P}READ_CALL_LOG",
        "${P}SYSTEM_ALERT_WINDOW", "${P}MANAGE_EXTERNAL_STORAGE",
    )

    /** Names chosen to look like part of Android, so nobody removes them. */
    private val SYSTEM_LOOKING_LABEL = Regex(
        """^(system|android|google|play|sim toolkit|wi-?fi|bluetooth|settings|device|battery|""" +
            """security|update|sync|service|services|core|framework|backup|cloud|network)\b.*""" +
            """|.*\b(system|service|services|update|updater|framework|sync)$""",
        RegexOption.IGNORE_CASE)

    /** Package names used by Android and Google. Google's own apps carry them
     *  when installed from Play; one that arrived any other way is pretending. */
    private val SYSTEM_PACKAGE_PREFIXES = listOf("android.", "com.android.", "com.google.android.")

    fun isSideloaded(app: AppFacts): Boolean =
        !app.isSystem && (app.installer == null || app.installer !in TRUSTED_STORES)

    fun impersonatesSystem(app: AppFacts): Boolean =
        isSideloaded(app) && SYSTEM_PACKAGE_PREFIXES.any { app.packageName.startsWith(it) }

    fun sourceName(pkg: String?): String? =
        pkg?.let { MESSENGERS[it] ?: BROWSERS[it] }

    fun assess(app: AppFacts, nowMs: Long = System.currentTimeMillis()): Assessment {
        if (app.isSystem) return Assessment(RiskLevel.NONE, false, null, emptyList())

        val sideloaded = isSideloaded(app)
        val fromMessenger = app.initiator in MESSENGERS || app.installer in MESSENGERS
        val cameFrom = sourceName(app.initiator) ?: sourceName(app.installer)

        val reasons = mutableListOf<String>()
        var takeover = false

        REMOTE_ACCESS[app.packageName]?.let {
            reasons += "is $it: anyone you give its code to can see and control this phone"
            takeover = true
        }
        if (app.isDeviceOwner || app.isProfileOwner) {
            if (sideloaded) {
                reasons += "holds enterprise Device Owner or Profile Owner authority, but was not installed by a verified enterprise store"
                takeover = true
            }
        }
        if (app.activeAccessibility) {
            reasons += "is switched on as an accessibility service: it can read everything on screen and press buttons for you"
            takeover = true
        } else if (app.declaresAccessibility && sideloaded) {
            reasons += "is built to ask for accessibility access, which would let it read your screen and press buttons"
        }
        if (app.activeNotificationListener) {
            reasons += "can read every notification, including one-time codes"
            takeover = true
        } else if (app.declaresNotificationListener && sideloaded) {
            reasons += "is built to ask to read your notifications, including one-time codes"
        }
        if (app.activeDeviceAdmin) {
            reasons += "is a device administrator: it can lock the phone and resist being uninstalled"
            takeover = true
        } else if (app.declaresDeviceAdmin && sideloaded) {
            reasons += "is built to ask to become a device administrator"
        }
        for ((permission, meaning) in SENSITIVE_PERMISSIONS) {
            if (permission in app.grantedPermissions) {
                reasons += meaning
                if (permission in TAKEOVER_PERMISSIONS) takeover = true
            }
        }
        if (app.declaresCardEmulation && sideloaded) {
            reasons += "can pretend to be a contactless bank card — the \"tap your card on your phone\" theft"
            takeover = true
        }

        // Temporal window: sideloaded apps requesting takeover capabilities immediately post-install
        val isRecent = app.firstInstallTimeMs > 0 && (nowMs - app.firstInstallTimeMs) in 0..(24 * 60 * 60 * 1000L)
        if (sideloaded && isRecent && (app.declaresAccessibility || app.declaresDeviceAdmin || app.grantedPermissions.any { it in TAKEOVER_PERMISSIONS })) {
            reasons += "was installed within the last 24 hours and holds high-privilege access"
            takeover = true
        }

        // How spy apps hide. None of these is harmful alone; each makes the
        // rest worse, because it is how a person fails to notice them.
        val hiding = mutableListOf<String>()
        if (impersonatesSystem(app)) {
            hiding += "uses a name reserved for Android and Google (${app.packageName}), but did not come from an app store"
        }
        if (!app.hasLauncherIcon && sideloaded) {
            hiding += "has no icon in your app list, so you would not see it"
        }
        if (sideloaded && SYSTEM_LOOKING_LABEL.matches(app.label.trim())) {
            hiding += "is named \"${app.label}\" to look like part of the phone, but it is not"
        }
        if (app.startsAtBoot && sideloaded && (reasons.isNotEmpty() || hiding.isNotEmpty())) {
            hiding += "starts itself every time the phone is switched on"
        }
        val hidden = hiding.isNotEmpty()
        reasons += hiding

        val level = when {
            // Pretending to be Android is never innocent.
            impersonatesSystem(app) -> RiskLevel.HIGH
            // Hiding, and able to do something with what it sees.
            sideloaded && hidden && reasons.size > hiding.size -> RiskLevel.HIGH
            // The pattern that matters: installed outside a store, and able
            // to take over the phone or its codes.
            sideloaded && takeover -> RiskLevel.HIGH
            // A remote-control app is dangerous wherever it came from; the
            // Play Store version is exactly what "support" callers ask for.
            app.packageName in REMOTE_ACCESS -> RiskLevel.HIGH
            // Arrived through a conversation and can do anything sensitive.
            sideloaded && fromMessenger && reasons.isNotEmpty() -> RiskLevel.HIGH
            sideloaded && reasons.isNotEmpty() -> RiskLevel.WATCH
            // From a store but holding the screen or the codes: worth knowing,
            // since legitimate apps (password managers, launchers) do this too.
            app.activeAccessibility || app.activeNotificationListener || app.activeDeviceAdmin -> RiskLevel.WATCH
            sideloaded && fromMessenger -> RiskLevel.WATCH
            else -> RiskLevel.NONE
        }
        if (level == RiskLevel.NONE) return Assessment(level, sideloaded, cameFrom, emptyList())

        val origin = when {
            cameFrom != null && fromMessenger -> "was installed from a file sent on $cameFrom"
            cameFrom != null -> "was downloaded in $cameFrom, not from an app store"
            sideloaded -> "was not installed from an app store"
            else -> null
        }
        return Assessment(level, sideloaded, cameFrom, listOfNotNull(origin) + reasons)
    }

    /** Judge an APK file before it is installed, from what it asks for. */
    fun assessApk(fileName: String?, sender: String?, requestedPermissions: Set<String>,
                  declaresAccessibility: Boolean, declaresNotificationListener: Boolean,
                  declaresDeviceAdmin: Boolean): List<String> {
        val reasons = mutableListOf<String>()
        val from = sourceName(sender)
        reasons += if (from != null) "It came from $from, not from an app store."
                   else "It is an app file, not from an app store."
        fileName?.let { name ->
            if (DISGUISED.containsMatchIn(name)) {
                reasons += "Its name, \"$name\", is made to look like a document. It is an app."
            }
        }
        if (declaresAccessibility) reasons += "It is built to ask to read your screen and press buttons for you."
        if (declaresNotificationListener) reasons += "It is built to ask to read your notifications, including one-time codes."
        if (declaresDeviceAdmin) reasons += "It is built to ask to become a device administrator, so it is hard to remove."
        for ((permission, meaning) in SENSITIVE_PERMISSIONS) {
            if (permission in requestedPermissions) reasons += "If allowed, it ${meaning}."
        }
        return reasons
    }

    /** "Posting_List.pdf.apk", "invoice.jpg .apk", "Army Welfare.docx.apk". */
    private val DISGUISED = Regex("""\.(pdf|jpe?g|png|docx?|xlsx?|pptx?|txt|mp4|zip)\s*\.apk$""", RegexOption.IGNORE_CASE)
}
