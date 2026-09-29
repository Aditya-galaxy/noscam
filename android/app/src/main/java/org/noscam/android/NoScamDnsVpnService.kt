package org.noscam.android

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.net.VpnService
import android.os.Build
import android.os.ParcelFileDescriptor
import android.util.Log
import java.io.FileInputStream
import java.io.FileOutputStream
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.nio.ByteBuffer

/**
 * Local DNS-Only VPN Service.
 *
 * Intercepts outbound DNS queries on loopback without routing ordinary
 * web/app traffic through a remote VPN server. Queries are evaluated locally
 * via DnsFilter: malicious or lookalike domains are sinkholed to 0.0.0.0
 * before the browser or app can open a connection.
 */
class NoScamDnsVpnService : VpnService(), Runnable {

    companion object {
        const val TAG = "NoScamDnsVpn"
        const val CHANNEL_ID = "noscam_dns_protection"
        const val NOTIFICATION_ID = 4001
        const val ACTION_STOP = "org.noscam.android.action.STOP_DNS"

        @Volatile
        var isRunning = false
            private set
    }

    private var vpnInterface: ParcelFileDescriptor? = null
    private var workerThread: Thread? = null
    @Volatile private var shouldRun = false

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopVpn()
            return START_NOT_STICKY
        }

        startForeground(NOTIFICATION_ID, createNotification())
        if (!isRunning) {
            setupVpn()
        }
        return START_STICKY
    }

    private fun setupVpn() {
        try {
            val builder = Builder()
                .setSession("NoScam DNS Guardian")
                .addAddress("10.0.0.2", 32)
                .addDnsServer("1.1.1.1")
                .addRoute("1.1.1.1", 32) // Only route DNS queries to the local TUN interface

            vpnInterface = builder.establish()
            shouldRun = true
            isRunning = true
            workerThread = Thread(this, "NoScamDnsWorker").apply { start() }
            Log.i(TAG, "NoScam DNS Guardian established successfully")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to establish VPN interface", e)
            stopSelf()
        }
    }

    override fun run() {
        val pfd = vpnInterface ?: return
        val inputStream = FileInputStream(pfd.fileDescriptor)
        val outputStream = FileOutputStream(pfd.fileDescriptor)
        val packet = ByteBuffer.allocate(32767)

        val upstreamSocket = DatagramSocket()
        protect(upstreamSocket) // Prevent VPN from looping its own upstream queries

        while (shouldRun) {
            try {
                packet.clear()
                val length = inputStream.read(packet.array())
                if (length <= 0) continue

                packet.limit(length)
                // Check if packet is IPv4 UDP to port 53
                if (isUdpDnsPacket(packet)) {
                    val query = extractDnsQuery(packet)
                    if (query != null) {
                        val verdict = DnsFilter.assess(query.domain)
                        if (verdict.action == DnsAction.SINKHOLE) {
                            Log.w(TAG, "SINKHOLED domain: ${query.domain} (${verdict.reason})")
                            val sinkholeResponse = buildSinkholeResponse(packet, query)
                            outputStream.write(sinkholeResponse.array(), 0, sinkholeResponse.limit())
                            continue
                        }
                    }

                    // Forward clean query upstream to 1.1.1.1:53
                    forwardUpstream(packet, length, upstreamSocket, outputStream)
                }
            } catch (e: Exception) {
                if (shouldRun) Log.d(TAG, "DNS tunnel read cycle: ${e.message}")
            }
        }
        try { upstreamSocket.close() } catch (_: Exception) {}
    }

    private fun isUdpDnsPacket(buffer: ByteBuffer): Boolean {
        if (buffer.limit() < 28) return false
        val ipVersion = (buffer.get(0).toInt() shr 4) and 0x0F
        if (ipVersion != 4) return false
        val protocol = buffer.get(9).toInt() and 0xFF
        if (protocol != 17) return false // UDP
        val destPort = buffer.getShort(22).toInt() and 0xFFFF
        return destPort == 53
    }

    data class ParsedQuery(val domain: String, val transactionId: Short, val queryType: Short)

    private fun extractDnsQuery(buffer: ByteBuffer): ParsedQuery? {
        try {
            val ipHeaderLen = (buffer.get(0).toInt() and 0x0F) * 4
            val dnsOffset = ipHeaderLen + 8
            if (buffer.limit() < dnsOffset + 12) return null

            val txId = buffer.getShort(dnsOffset)
            var pos = dnsOffset + 12
            val sb = StringBuilder()

            while (pos < buffer.limit()) {
                val len = buffer.get(pos).toInt() and 0xFF
                pos++
                if (len == 0) break
                if (sb.isNotEmpty()) sb.append('.')
                val labelBytes = ByteArray(len)
                for (i in 0 until len) {
                    if (pos < buffer.limit()) labelBytes[i] = buffer.get(pos++)
                }
                sb.append(String(labelBytes))
            }
            val qType = if (pos + 2 <= buffer.limit()) buffer.getShort(pos) else 1
            return ParsedQuery(sb.toString(), txId, qType)
        } catch (_: Exception) {
            return null
        }
    }

    private fun buildSinkholeResponse(originalPacket: ByteBuffer, query: ParsedQuery): ByteBuffer {
        // Construct IPv4 UDP DNS response resolving to 0.0.0.0
        val ipHeaderLen = (originalPacket.get(0).toInt() and 0x0F) * 4
        val dnsOffset = ipHeaderLen + 8
        val dnsLength = originalPacket.limit() - dnsOffset

        // Create response buffer
        val respDns = ByteBuffer.allocate(dnsLength + 16)
        val origDns = ByteArray(dnsLength)
        originalPacket.position(dnsOffset)
        originalPacket.get(origDns)

        respDns.put(origDns)
        // Set QR=1 (response), RA=1
        respDns.put(2, (respDns.get(2).toInt() or 0x81).toByte())
        // Answer count = 1
        respDns.putShort(6, 1)

        // Append Answer Resource Record: Name Pointer (0xc00c), Type A (1), Class IN (1), TTL (60s), Length (4), IP 0.0.0.0
        respDns.putShort(0xc00c.toShort())
        respDns.putShort(1) // Type A
        respDns.putShort(1) // Class IN
        respDns.putInt(60)  // TTL
        respDns.putShort(4) // RdLength
        respDns.put(byteArrayOf(0, 0, 0, 0)) // 0.0.0.0

        respDns.flip()
        return buildIpUdpPacket(originalPacket, respDns)
    }

    private fun buildIpUdpPacket(original: ByteBuffer, dnsPayload: ByteBuffer): ByteBuffer {
        val totalLength = 20 + 8 + dnsPayload.limit()
        val out = ByteBuffer.allocate(totalLength)

        // IPv4 Header
        out.put(0x45.toByte())
        out.put(0x00.toByte())
        out.putShort(totalLength.toShort())
        out.putShort(0)
        out.putShort(0x4000.toShort()) // Don't fragment
        out.put(64.toByte()) // TTL
        out.put(17.toByte()) // UDP
        out.putShort(0) // Checksum (0 for simplicity)

        // Swap src and dst IP
        val srcIp = ByteArray(4)
        val dstIp = ByteArray(4)
        original.position(12)
        original.get(srcIp)
        original.get(dstIp)
        out.put(dstIp)
        out.put(srcIp)

        // UDP Header (swap src and dst port)
        val srcPort = original.getShort(20)
        val dstPort = original.getShort(22)
        out.putShort(dstPort)
        out.putShort(srcPort)
        out.putShort((8 + dnsPayload.limit()).toShort())
        out.putShort(0) // UDP checksum

        out.put(dnsPayload)
        out.flip()
        return out
    }

    private fun forwardUpstream(
        packet: ByteBuffer,
        length: Int,
        socket: DatagramSocket,
        tunOut: FileOutputStream
    ) {
        val ipHeaderLen = (packet.get(0).toInt() and 0x0F) * 4
        val dnsOffset = ipHeaderLen + 8
        val dnsLen = length - dnsOffset
        if (dnsLen <= 0) return

        val dnsQueryBytes = ByteArray(dnsLen)
        packet.position(dnsOffset)
        packet.get(dnsQueryBytes)

        val outPacket = DatagramPacket(
            dnsQueryBytes,
            dnsQueryBytes.size,
            InetAddress.getByName("1.1.1.1"),
            53
        )
        socket.send(outPacket)

        val inBuf = ByteArray(4096)
        val inPacket = DatagramPacket(inBuf, inBuf.size)
        socket.soTimeout = 2000
        socket.receive(inPacket)

        val dnsResponse = ByteBuffer.wrap(inBuf, 0, inPacket.length)
        val fullPacket = buildIpUdpPacket(packet, dnsResponse)
        tunOut.write(fullPacket.array(), 0, fullPacket.limit())
    }

    private fun createNotification(): Notification {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "NoScam DNS Guardian",
                NotificationManager.IMPORTANCE_LOW
            ).apply { description = "Intercepts and sinkholes malicious lookalike domains on device" }
            nm.createNotificationChannel(channel)
        }

        val stopIntent = Intent(this, NoScamDnsVpnService::class.java).apply {
            action = ACTION_STOP
        }
        val stopPending = PendingIntent.getService(
            this, 0, stopIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
        } else {
            Notification.Builder(this)
        }

        return builder
            .setContentTitle("NoScam DNS Guardian Active")
            .setContentText("Device-wide protection against lookalike domains and scam links")
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Stop", stopPending)
            .setOngoing(true)
            .build()
    }

    private fun stopVpn() {
        shouldRun = false
        isRunning = false
        try { vpnInterface?.close() } catch (_: Exception) {}
        vpnInterface = null
        stopForeground(true)
        stopSelf()
        Log.i(TAG, "NoScam DNS Guardian stopped")
    }

    override fun onDestroy() {
        stopVpn()
        super.onDestroy()
    }
}
