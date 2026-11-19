package com.kolondam.odooca.field.data.sync

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import androidx.work.workDataOf
import com.kolondam.odooca.field.data.repo.OutboxRepository
import java.util.concurrent.TimeUnit

/** Diimplementasikan oleh Application agar worker dapat mengambil repositori. */
interface OutboxServices {
    val outboxRepository: OutboxRepository
}

class OutboxWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val owner = inputData.getString(KEY_OWNER) ?: return Result.success()
        val services = applicationContext as? OutboxServices ?: return Result.failure()
        val result = services.outboxRepository.flush(owner)
        return if (result.retryLater) Result.retry() else Result.success()
    }

    companion object {
        const val KEY_OWNER = "owner"
    }
}

object OutboxScheduler {
    /** Menjadwalkan pengiriman begitu jaringan tersedia. Panggilan berulang diantrekan berurutan. */
    fun kick(context: Context, ownerId: String) {
        val request = OneTimeWorkRequestBuilder<OutboxWorker>()
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .setInputData(workDataOf(OutboxWorker.KEY_OWNER to ownerId))
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(context)
            .enqueueUniqueWork("outbox-$ownerId", ExistingWorkPolicy.APPEND_OR_REPLACE, request)
    }
}
