package com.kolondam.odooca.field.data.repo

import com.kolondam.odooca.field.data.db.OdoocaDatabase
import com.kolondam.odooca.field.data.db.OutboxEntity
import com.kolondam.odooca.field.data.network.ApiException
import com.kolondam.odooca.field.data.network.ApiJson
import com.kolondam.odooca.field.data.network.OdoocaApi
import com.kolondam.odooca.field.domain.sync.CommandState
import com.kolondam.odooca.field.domain.sync.OutboxPlanner
import com.kolondam.odooca.field.domain.sync.QueueItem
import com.kolondam.odooca.field.domain.sync.QueueKind
import com.kolondam.odooca.field.domain.sync.Receipt
import com.kolondam.odooca.field.domain.sync.ReceiptStatus
import com.kolondam.odooca.field.domain.sync.SendClassifier
import com.kolondam.odooca.field.domain.sync.SendOutcome
import java.io.File
import kotlinx.coroutines.flow.Flow
import kotlinx.serialization.SerializationException
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.builtins.serializer

data class FlushResult(val sent: Int, val authRequired: Boolean, val retryLater: Boolean)

/** Hasil satu pengiriman beserta receipt JSON mentah (untuk bukti) bila ada. */
private data class Sent(val outcome: SendOutcome, val receiptJson: String? = null)

/**
 * Antrean pengiriman ke server untuk command dan unggahan bukti. Urutan, dependensi, retry, dan
 * klasifikasi hasil ditentukan oleh logika domain yang sudah diuji; kelas ini hanya menyimpan dan memanggil API.
 */
class OutboxRepository(
    private val db: OdoocaDatabase,
    private val api: OdoocaApi,
    private val csrfToken: () -> String?,
) {
    private val dao get() = db.outbox()
    private val idsSerializer = ListSerializer(String.serializer())

    fun observe(ownerId: String): Flow<List<OutboxEntity>> = dao.observe(ownerId)

    /** Menyimpan command yang siap dikirim. `id` = UUID klien dan juga `client_uuid` di payload. */
    suspend fun enqueueCommand(
        ownerId: String,
        id: String,
        payloadJson: String,
        dependsOn: List<String> = emptyList(),
        nowMs: Long = System.currentTimeMillis(),
    ) = insert(ownerId, id, QueueKind.COMMAND, payloadJson, dependsOn, null, nowMs)

    /** Menyimpan unggahan foto bukti. `metadataJson` adalah metadata multipart, `photoPath` berkas foto lokal. */
    suspend fun enqueueEvidence(
        ownerId: String,
        id: String,
        metadataJson: String,
        photoPath: String,
        nowMs: Long = System.currentTimeMillis(),
    ) = insert(ownerId, id, QueueKind.EVIDENCE, metadataJson, emptyList(), photoPath, nowMs)

    private suspend fun insert(
        ownerId: String,
        id: String,
        kind: QueueKind,
        payload: String,
        dependsOn: List<String>,
        filePath: String?,
        nowMs: Long,
    ) {
        dao.insert(
            OutboxEntity(
                id = id,
                ownerId = ownerId,
                kind = kind.name,
                state = CommandState.QUEUED.name,
                createdAtMs = nowMs,
                attempts = 0,
                nextAttemptAtMs = 0,
                dependsOnJson = ApiJson.encodeToString(idsSerializer, dependsOn),
                payload = payload,
                error = null,
                receiptReference = null,
                receiptMessage = null,
                filePath = filePath,
            ),
        )
    }

    suspend fun flush(ownerId: String, nowMs: () -> Long = System::currentTimeMillis): FlushResult {
        recoverInterrupted(ownerId)
        var sent = 0
        while (true) {
            val items = dao.all(ownerId).map { it.toDomain() }
            val plan = OutboxPlanner.plan(items, ownerId, nowMs())
            for (change in plan.changes) setState(change.id, change.to, change.reason)
            if (plan.haltedForAuth) return FlushResult(sent, authRequired = true, retryLater = false)
            if (plan.send.isEmpty()) {
                val waiting = items.any { it.state == CommandState.QUEUED && it.nextAttemptAtMs > nowMs() }
                return FlushResult(sent, authRequired = false, retryLater = waiting)
            }
            for (item in plan.send) {
                sendOne(item, nowMs)
                sent++
            }
        }
    }

    /** Item yang tertinggal SENDING karena proses mati dikirim ulang dengan UUID yang sama (idempoten). */
    private suspend fun recoverInterrupted(ownerId: String) {
        for (e in dao.all(ownerId)) {
            if (e.state == CommandState.SENDING.name) dao.update(e.copy(state = CommandState.QUEUED.name))
        }
    }

    private suspend fun sendOne(item: QueueItem, nowMs: () -> Long) {
        val entity = dao.get(item.id) ?: return
        val attempts = item.attempts + 1
        dao.update(entity.copy(state = CommandState.SENDING.name, attempts = attempts))

        val result = try {
            when (item.kind) {
                QueueKind.COMMAND -> sendCommand(entity, item.id)
                QueueKind.EVIDENCE -> sendEvidence(entity, item.id)
            }
        } catch (e: ApiException) {
            Sent(SendClassifier.classifyFailure(e.status, e.message.orEmpty(), attempts, nowMs()))
        } catch (e: SerializationException) {
            // Respons tidak terbaca: aman diulang karena server idempoten terhadap UUID yang sama.
            Sent(SendClassifier.classifyFailure(null, "Respons server tidak dapat dibaca", attempts, nowMs()))
        }

        val current = dao.get(item.id) ?: return
        val updated = when (val outcome = result.outcome) {
            is SendOutcome.Delivered -> current.copy(
                state = outcome.state.name,
                error = null,
                receiptReference = outcome.receipt.reference,
                receiptMessage = outcome.receipt.message,
                receiptJson = result.receiptJson,
            )
            SendOutcome.AuthRequired -> current.copy(state = CommandState.AUTH_REQUIRED.name, error = "Sesi berakhir")
            is SendOutcome.Retry -> current.copy(
                state = CommandState.QUEUED.name,
                nextAttemptAtMs = outcome.nextAttemptAtMs,
                error = null,
            )
            is SendOutcome.Rejected -> current.copy(
                state = CommandState.REJECTED.name,
                error = "HTTP ${outcome.httpStatus}: ${outcome.message}",
            )
            is SendOutcome.ProtocolMismatch -> current.copy(
                state = CommandState.NEEDS_REVIEW.name,
                error = outcome.reason,
            )
        }
        dao.update(updated)
    }

    private suspend fun sendCommand(entity: OutboxEntity, id: String): Sent {
        val r = api.postCommand(entity.payload, csrfToken())
        return Sent(
            SendClassifier.classifyReceipt(
                commandUuid = id,
                receipt = Receipt(r.clientUuid, r.status.toReceiptStatus(), r.message, r.reference),
            ),
        )
    }

    private suspend fun sendEvidence(entity: OutboxEntity, id: String): Sent {
        val photo = File(entity.filePath.orEmpty())
        if (!photo.isFile) return Sent(SendOutcome.Rejected(0, "Berkas foto bukti tidak ditemukan"))
        val r = api.uploadEvidence(entity.payload, photo, csrfToken())
        val outcome = SendClassifier.classifyReceipt(
            commandUuid = id,
            receipt = Receipt(r.clientUuid, ReceiptStatus.ACCEPTED, "Bukti diterima", r.bindingSha256),
        )
        return Sent(outcome, ApiJson.encodeToString(com.kolondam.odooca.field.data.network.EvidenceReceiptDto.serializer(), r))
    }

    private suspend fun setState(id: String, to: CommandState, reason: String) {
        val e = dao.get(id) ?: return
        dao.update(e.copy(state = to.name, error = if (to == CommandState.QUEUED) null else reason))
    }

    private fun OutboxEntity.toDomain() = QueueItem(
        id = id,
        ownerId = ownerId,
        kind = QueueKind.valueOf(kind),
        state = CommandState.valueOf(state),
        createdAtMs = createdAtMs,
        attempts = attempts,
        nextAttemptAtMs = nextAttemptAtMs,
        dependsOn = ApiJson.decodeFromString(idsSerializer, dependsOnJson),
        error = error,
    )

    private fun String.toReceiptStatus(): ReceiptStatus = when (lowercase()) {
        "accepted" -> ReceiptStatus.ACCEPTED
        "needs_approval" -> ReceiptStatus.NEEDS_APPROVAL
        else -> ReceiptStatus.REJECTED
    }
}
