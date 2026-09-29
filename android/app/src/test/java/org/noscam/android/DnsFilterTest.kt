package org.noscam.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

class DnsFilterTest {

    @Test
    fun `ordinary legitimate domains are allowed`() {
        assertEquals(DnsAction.ALLOW, DnsFilter.assess("google.com").action)
        assertEquals(DnsAction.ALLOW, DnsFilter.assess("www.wikipedia.org").action)
        assertEquals(DnsAction.ALLOW, DnsFilter.assess("github.com").action)
        assertEquals(DnsAction.ALLOW, DnsFilter.assess("sbi.co.in").action)
        assertEquals(DnsAction.ALLOW, DnsFilter.assess("retail.onlinesbi.sbi").action)
        assertEquals(DnsAction.ALLOW, DnsFilter.assess("netbanking.hdfcbank.com").action)
        assertEquals(DnsAction.ALLOW, DnsFilter.assess("paypal.com").action)
        assertEquals(DnsAction.ALLOW, DnsFilter.assess("amazon.in").action)
    }

    @Test
    fun `brand impersonation lookalikes are sinkholed`() {
        val sbiScam = DnsFilter.assess("sbi-kyc-verification.com")
        assertEquals(DnsAction.SINKHOLE, sbiScam.action)
        assertNotNull(sbiScam.reason)

        val paypalScam = DnsFilter.assess("paypal-security-update.net")
        assertEquals(DnsAction.SINKHOLE, paypalScam.action)

        val hdfcScam = DnsFilter.assess("hdfc-pan-update.org")
        assertEquals(DnsAction.SINKHOLE, hdfcScam.action)

        val chaseScam = DnsFilter.assess("chase-online-login.info")
        assertEquals(DnsAction.SINKHOLE, chaseScam.action)
    }

    @Test
    fun `punycode homograph domains are sinkholed`() {
        val puny = DnsFilter.assess("xn--pple-43d.com")
        assertEquals(DnsAction.SINKHOLE, puny.action)
        assertEquals("Punycode domain disguised with foreign character lookalikes", puny.reason)
    }

    @Test
    fun `raw numeric IP addresses accessed as domain are sinkholed`() {
        val ip = DnsFilter.assess("192.168.1.100")
        assertEquals(DnsAction.SINKHOLE, ip.action)
        assertEquals("Numbered IP address used directly as website destination", ip.reason)
    }

    @Test
    fun `remote access tools pushed on calls are sinkholed`() {
        val anydesk = DnsFilter.assess("anydesk.com")
        assertEquals(DnsAction.SINKHOLE, anydesk.action)

        val teamviewer = DnsFilter.assess("download.teamviewer.com")
        assertEquals(DnsAction.SINKHOLE, teamviewer.action)

        val rustdesk = DnsFilter.assess("relay.rustdesk.com")
        assertEquals(DnsAction.SINKHOLE, rustdesk.action)
    }

    @Test
    fun `suspicious disposable TLDs are sinkholed`() {
        val xyz = DnsFilter.assess("urgent-challan-pay.xyz")
        assertEquals(DnsAction.SINKHOLE, xyz.action)

        val click = DnsFilter.assess("tax-refund-claim.click")
        assertEquals(DnsAction.SINKHOLE, click.action)

        val top = DnsFilter.assess("lottery-winner-portal.top")
        assertEquals(DnsAction.SINKHOLE, top.action)
    }

    @Test
    fun `empty or blank queries are safe fallbacks`() {
        assertEquals(DnsAction.ALLOW, DnsFilter.assess("").action)
        assertEquals(DnsAction.ALLOW, DnsFilter.assess("   ").action)
    }
}
