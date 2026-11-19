package com.kolondam.odooca.field.domain.evidence

import com.kolondam.odooca.field.domain.visit.EvidenceRef
import java.security.MessageDigest
import java.util.Locale

object PhotoHash {
    fun sha256Hex(bytes: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { String.format(Locale.ROOT, "%02x", it) }
}

/**
 * Rujukan bukti untuk check-in yang disusun di perangkat sebelum unggahan selesai.
 * `packageHash` memakai SHA-256 foto asli: server menerima `original_sha256` sebagai hash yang sah
 * (selain `watermarked_sha256` dan `binding_sha256`), sehingga check-in dapat diantre offline setelah
 * unggahan evidence tanpa menunggu receipt. Asumsi: server menghitung `original_sha256` dari byte foto
 * yang diunggah apa adanya; perlu dibuktikan pada uji pertama ke backend nyata.
 */
fun EvidenceCapture.localRef(photoSha256: String) = EvidenceRef(
    id = clientUuid,
    packageHash = photoSha256,
    latitude = fix.latitude,
    longitude = fix.longitude,
    accuracyM = fix.accuracyM,
    capturedAtMs = photoSelectedAtMs,
)
