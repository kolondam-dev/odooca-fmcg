package com.kolondam.odooca.field.data.repo

import androidx.room.withTransaction
import com.kolondam.odooca.field.data.db.OdoocaDatabase
import com.kolondam.odooca.field.domain.evidence.EvidenceCapture
import com.kolondam.odooca.field.domain.evidence.EvidenceMetadata
import com.kolondam.odooca.field.domain.evidence.PhotoHash
import com.kolondam.odooca.field.domain.evidence.localRef
import com.kolondam.odooca.field.domain.visit.BuildResult
import com.kolondam.odooca.field.domain.visit.VisitCommands
import com.kolondam.odooca.field.domain.visit.VisitContext
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Check-in kunjungan: memvalidasi dengan aturan domain, lalu mengantre unggahan bukti dan command
 * check-in (yang bergantung pada unggahan itu) dalam satu transaksi. Tidak ada yang diantre bila validasi gagal.
 */
class VisitRepository(private val db: OdoocaDatabase, private val outbox: OutboxRepository) {
    suspend fun queueCheckIn(
        ownerId: String,
        nowMs: Long,
        commandUuid: String,
        capture: EvidenceCapture,
        photo: File,
        context: VisitContext,
    ): BuildResult {
        val metadata = EvidenceMetadata.build(capture, nowMs)
        if (metadata is BuildResult.Invalid) return metadata
        metadata as BuildResult.Ok

        val photoHash = withContext(Dispatchers.IO) { PhotoHash.sha256Hex(photo.readBytes()) }
        val command = VisitCommands.checkIn(commandUuid, nowMs, context.copy(evidence = capture.localRef(photoHash)))
        if (command is BuildResult.Invalid) return command
        command as BuildResult.Ok

        db.withTransaction {
            outbox.enqueueEvidence(ownerId, capture.clientUuid, metadata.json, photo.absolutePath, nowMs)
            outbox.enqueueCommand(ownerId, commandUuid, command.json, listOf(capture.clientUuid), nowMs + 1)
        }
        return command
    }
}
