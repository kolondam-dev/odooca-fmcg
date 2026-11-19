package com.kolondam.odooca.field.domain.sync

/**
 * Lifecycle satu item antrean (command atau unggahan bukti).
 * Receipt server adalah satu-satunya bukti final penerimaan.
 */
enum class CommandState {
    DRAFT,
    QUEUED,
    SENDING,

    /** Diterima server. */
    ACCEPTED,

    /** Diterima server, menunggu keputusan approval di Odoo. */
    NEEDS_APPROVAL,

    /** Ditolak server atau ditolak secara definitif (4xx selain 408/429). Perlu tindakan pengguna. */
    REJECTED,

    /** Sesi tidak valid (401). Seluruh pengiriman pemilik berhenti sampai login ulang. */
    AUTH_REQUIRED,

    /** Menunggu item lain yang gagal definitif atau perlu tinjauan. */
    BLOCKED_DEPENDENCY,

    /** Ada bukti yang harus selesai diunggah dulu. */
    EVIDENCE_HOLD,

    /** Respons tidak konsisten dengan permintaan (misalnya UUID receipt berbeda). */
    NEEDS_REVIEW,
    ;

    /** Server sudah menerima item ini, sehingga item yang bergantung boleh dikirim. */
    val isServerAccepted: Boolean get() = this == ACCEPTED || this == NEEDS_APPROVAL

    /** Item tidak akan berubah lagi tanpa tindakan pengguna. */
    val isTerminal: Boolean
        get() = this == ACCEPTED || this == NEEDS_APPROVAL || this == REJECTED || this == NEEDS_REVIEW

    fun canTransitionTo(next: CommandState): Boolean = next in allowedNext

    private val allowedNext: Set<CommandState>
        get() = when (this) {
            DRAFT -> setOf(QUEUED)
            QUEUED -> setOf(SENDING, BLOCKED_DEPENDENCY, EVIDENCE_HOLD)
            SENDING -> setOf(ACCEPTED, NEEDS_APPROVAL, REJECTED, AUTH_REQUIRED, QUEUED, NEEDS_REVIEW)
            AUTH_REQUIRED -> setOf(QUEUED)
            BLOCKED_DEPENDENCY -> setOf(QUEUED)
            EVIDENCE_HOLD -> setOf(QUEUED)
            REJECTED -> setOf(DRAFT)
            NEEDS_REVIEW -> setOf(DRAFT, QUEUED)
            ACCEPTED, NEEDS_APPROVAL -> emptySet()
        }
}

enum class ReceiptStatus { ACCEPTED, NEEDS_APPROVAL, REJECTED }

data class Receipt(
    val clientUuid: String,
    val status: ReceiptStatus,
    val message: String,
    val reference: String,
)

/** Hasil satu percobaan pengiriman, sebelum diterapkan ke item antrean. */
sealed interface SendOutcome {
    data class Delivered(val receipt: Receipt, val state: CommandState) : SendOutcome
    data object AuthRequired : SendOutcome
    data class Retry(val nextAttemptAtMs: Long) : SendOutcome
    data class Rejected(val httpStatus: Int, val message: String) : SendOutcome
    data class ProtocolMismatch(val reason: String) : SendOutcome
}

object SendClassifier {
    const val MAX_BACKOFF_MS = 120_000L
    private const val MAX_BACKOFF_EXPONENT = 7

    /**
     * @param attempts jumlah percobaan termasuk yang baru saja gagal (sudah dinaikkan).
     * Jeda: 1 detik x 2^min(attempts, 7), dibatasi 120 detik.
     */
    fun backoffMs(attempts: Int): Long {
        val exp = minOf(attempts.coerceAtLeast(0), MAX_BACKOFF_EXPONENT)
        return minOf(MAX_BACKOFF_MS, 1_000L * (1L shl exp))
    }

    /** Klasifikasi kegagalan transport atau HTTP. `httpStatus` null berarti tidak ada respons (jaringan). */
    fun classifyFailure(httpStatus: Int?, message: String, attempts: Int, nowMs: Long): SendOutcome = when {
        httpStatus == 401 -> SendOutcome.AuthRequired
        httpStatus != null && httpStatus in 400..499 && httpStatus != 408 && httpStatus != 429 ->
            SendOutcome.Rejected(httpStatus, message)
        else -> SendOutcome.Retry(nowMs + backoffMs(attempts))
    }

    /** Klasifikasi respons 2xx yang membawa receipt. */
    fun classifyReceipt(commandUuid: String, receipt: Receipt): SendOutcome {
        if (!receipt.clientUuid.equals(commandUuid, ignoreCase = true)) {
            return SendOutcome.ProtocolMismatch("UUID receipt tidak sama dengan UUID command")
        }
        val state = when (receipt.status) {
            ReceiptStatus.ACCEPTED -> CommandState.ACCEPTED
            ReceiptStatus.NEEDS_APPROVAL -> CommandState.NEEDS_APPROVAL
            ReceiptStatus.REJECTED -> CommandState.REJECTED
        }
        return SendOutcome.Delivered(receipt, state)
    }
}
