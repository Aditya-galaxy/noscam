package org.noscam.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class AppRiskTest {

    private val sms = "android.permission.READ_SMS"
    private val camera = "android.permission.CAMERA"

    private fun app(
        pkg: String = "com.example.app",
        installer: String? = "com.android.vending",
        initiator: String? = installer,
        granted: Set<String> = emptySet(),
        system: Boolean = false,
        accessibility: Boolean = false,
        listener: Boolean = false,
        admin: Boolean = false,
    ) = AppFacts(pkg, "Example", installer, initiator, system, granted,
                 activeAccessibility = accessibility, activeNotificationListener = listener,
                 activeDeviceAdmin = admin)

    @Test fun `an ordinary store app is left alone`() {
        assertEquals(RiskLevel.NONE, AppRisk.assess(app(granted = setOf(camera))).level)
    }

    @Test fun `system apps are never flagged`() {
        assertEquals(RiskLevel.NONE, AppRisk.assess(app(installer = null, system = true, admin = true)).level)
    }

    @Test fun `the Transparent Tribe pattern - sent on WhatsApp, reads SMS`() {
        val result = AppRisk.assess(app(installer = "com.google.android.packageinstaller",
                                        initiator = "com.whatsapp", granted = setOf(sms)))
        assertEquals(RiskLevel.HIGH, result.level)
        assertEquals("WhatsApp", result.cameFrom)
        assertTrue(result.reasons.first().contains("sent on WhatsApp"))
        assertTrue(result.reasons.any { it.contains("text messages") })
    }

    @Test fun `a sideloaded app reading notifications is a takeover`() {
        val result = AppRisk.assess(app(installer = "com.google.android.packageinstaller",
                                        initiator = "com.android.documentsui", listener = true))
        assertEquals(RiskLevel.HIGH, result.level)
    }

    @Test fun `sent in a chat with any sensitive permission is high`() {
        val result = AppRisk.assess(app(installer = "com.google.android.packageinstaller",
                                        initiator = "org.telegram.messenger", granted = setOf(camera)))
        assertEquals(RiskLevel.HIGH, result.level)
    }

    @Test fun `downloaded in a browser with a camera permission is worth a look, not an alarm`() {
        val result = AppRisk.assess(app(installer = "com.google.android.packageinstaller",
                                        initiator = "com.android.chrome", granted = setOf(camera)))
        assertEquals(RiskLevel.WATCH, result.level)
        assertTrue(result.reasons.first().contains("Chrome"))
    }

    @Test fun `remote control apps are high even from the Play Store`() {
        val result = AppRisk.assess(app(pkg = "com.anydesk.anydeskandroid"))
        assertEquals(RiskLevel.HIGH, result.level)
        assertTrue(result.reasons.any { it.contains("AnyDesk") })
    }

    @Test fun `a store app with accessibility on is worth checking, not removing`() {
        assertEquals(RiskLevel.WATCH, AppRisk.assess(app(accessibility = true)).level)
    }

    @Test fun `an APK disguised as a document says so`() {
        val reasons = AppRisk.assessApk("Posting_List.pdf.apk", "com.whatsapp", setOf(sms),
                                        declaresAccessibility = true,
                                        declaresNotificationListener = false,
                                        declaresDeviceAdmin = false)
        assertTrue(reasons.first().contains("WhatsApp"))
        assertTrue(reasons.any { it.contains("look like a document") })
        assertTrue(reasons.any { it.contains("read your screen") })
        assertTrue(reasons.any { it.contains("text messages") })
    }

    @Test fun `an honest file name is not called a disguise`() {
        val reasons = AppRisk.assessApk("app-release.apk", null, emptySet(), false, false, false)
        assertTrue(reasons.none { it.contains("look like a document") })
    }

    private val sideload = "com.google.android.packageinstaller"

    @Test fun `a hidden app that reads SMS is high`() {
        val result = AppRisk.assess(app(installer = sideload, initiator = "com.android.documentsui",
                                        granted = setOf(sms)).copy(hasLauncherIcon = false))
        assertEquals(RiskLevel.HIGH, result.level)
        assertTrue(result.reasons.any { it.contains("no icon") })
    }

    @Test fun `a hidden app with no permissions is only worth checking`() {
        val result = AppRisk.assess(app(installer = sideload, initiator = null)
            .copy(hasLauncherIcon = false))
        assertEquals(RiskLevel.WATCH, result.level)
    }

    @Test fun `a store app without an icon is not accused of hiding`() {
        val result = AppRisk.assess(app().copy(hasLauncherIcon = false))
        assertEquals(RiskLevel.NONE, result.level)
    }

    @Test fun `using a package name reserved for Android is high`() {
        val result = AppRisk.assess(app(pkg = "com.android.system.update", installer = sideload))
        assertEquals(RiskLevel.HIGH, result.level)
        assertTrue(result.reasons.any { it.contains("reserved for Android") })
    }

    @Test fun `a sideloaded app named like the system is called out`() {
        val result = AppRisk.assess(app(installer = sideload, initiator = null, granted = setOf(camera))
            .copy(label = "System Update"))
        assertTrue(result.reasons.any { it.contains("look like part of the phone") })
        assertEquals(RiskLevel.HIGH, result.level)
    }

    @Test fun `a sideloaded contactless card emulator is the ghost tapping pattern`() {
        val result = AppRisk.assess(app(installer = sideload, initiator = "com.android.chrome")
            .copy(declaresCardEmulation = true))
        assertEquals(RiskLevel.HIGH, result.level)
        assertTrue(result.reasons.any { it.contains("contactless bank card") })
    }

    @Test fun `Google Pay from the Play Store may emulate a card`() {
        val result = AppRisk.assess(app(pkg = "com.google.android.apps.nbu.paisa.user")
            .copy(declaresCardEmulation = true, isSystem = false))
        assertEquals(RiskLevel.NONE, result.level)
    }

    @Test fun `a sideloaded app holding device owner authority is high risk`() {
        val result = AppRisk.assess(app(installer = sideload).copy(isDeviceOwner = true))
        assertEquals(RiskLevel.HIGH, result.level)
        assertTrue(result.reasons.any { it.contains("Device Owner") })
    }

    @Test fun `a sideloaded app holding profile owner authority is high risk`() {
        val result = AppRisk.assess(app(installer = sideload).copy(isProfileOwner = true))
        assertEquals(RiskLevel.HIGH, result.level)
        assertTrue(result.reasons.any { it.contains("Profile Owner") })
    }

    @Test fun `a sideloaded app installed in the last 24 hours declaring accessibility is high risk`() {
        val now = 1700000000000L
        val installedTwoHoursAgo = now - (2 * 3600 * 1000L)
        val result = AppRisk.assess(
            app(installer = sideload, initiator = "com.android.chrome")
                .copy(declaresAccessibility = true, firstInstallTimeMs = installedTwoHoursAgo),
            nowMs = now
        )
        assertEquals(RiskLevel.HIGH, result.level)
        assertTrue(result.reasons.any { it.contains("last 24 hours") })
    }
}
