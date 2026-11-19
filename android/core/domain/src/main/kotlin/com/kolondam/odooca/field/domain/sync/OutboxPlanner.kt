package com.kolondam.odooca.field.domain.sync

enum class QueueKind { COMMAND, EVIDENCE }

/** Item antrean. `id` adalah UUID klien yang stabil dan dipakai ulang pada setiap retry. */
data class QueueItem(
    val id: String,
    val ownerId: String,
    val kind: QueueKind,
    val state: CommandState,
    val createdAtMs: Long,
    val attempts: Int = 0,
    val nextAttemptAtMs: Long = 0,
    val dependsOn: List<String> = emptyList(),
    val error: String? = null,
)

data class StateChange(val id: String, val to: CommandState, val reason: String)

data class OutboxPlan(
    /** Item yang siap dikirim sekarang, berurutan. */
    val send: List<QueueItem>,
    /** Perubahan status yang harus disimpan lebih dulu (blokir atau pelepasan dependensi). */
    val changes: List<StateChange>,
    /** True bila ada item pemilik ini berstatus AUTH_REQUIRED: tidak ada yang boleh dikirim. */
    val haltedForAuth: Boolean,
)

object OutboxPlanner {
    /**
     * Menyusun rencana pengiriman untuk satu pemilik. Item pemilik lain tidak pernah disentuh,
     * sehingga data antar akun di perangkat yang sama tetap terisolasi.
     */
    fun plan(allItems: List<QueueItem>, ownerId: String, nowMs: Long, maxBatch: Int = 10): OutboxPlan {
        val items = allItems.filter { it.ownerId == ownerId }
        val byId = items.associateBy { it.id }

        if (items.any { it.state == CommandState.AUTH_REQUIRED }) {
            return OutboxPlan(emptyList(), emptyList(), haltedForAuth = true)
        }

        val changes = mutableListOf<StateChange>()
        val effectiveState = items.associate { it.id to it.state }.toMutableMap()

        // Propagasi blokir sampai stabil (rantai dependensi bisa bertingkat).
        var changed = true
        while (changed) {
            changed = false
            for (item in items) {
                val current = effectiveState.getValue(item.id)
                if (current != CommandState.QUEUED && current != CommandState.BLOCKED_DEPENDENCY) continue
                val deps = item.dependsOn.map { byId[it]?.let { dep -> effectiveState.getValue(dep.id) } }
                val broken = deps.any {
                    it == null || it == CommandState.REJECTED || it == CommandState.NEEDS_REVIEW ||
                        it == CommandState.BLOCKED_DEPENDENCY
                }
                if (broken && current == CommandState.QUEUED) {
                    effectiveState[item.id] = CommandState.BLOCKED_DEPENDENCY
                    changes += StateChange(item.id, CommandState.BLOCKED_DEPENDENCY, "Dependensi gagal atau hilang")
                    changed = true
                } else if (!broken && current == CommandState.BLOCKED_DEPENDENCY) {
                    effectiveState[item.id] = CommandState.QUEUED
                    changes += StateChange(item.id, CommandState.QUEUED, "Dependensi pulih")
                    changed = true
                }
            }
        }

        val ready = items
            .filter { effectiveState.getValue(it.id) == CommandState.QUEUED }
            .filter { it.nextAttemptAtMs <= nowMs }
            .filter { item ->
                item.dependsOn.all { dep -> byId[dep]?.let { effectiveState.getValue(it.id) }?.isServerAccepted == true }
            }
            .sortedWith(compareBy<QueueItem> { it.createdAtMs }.thenBy { it.id })
            .take(maxBatch.coerceAtLeast(0))

        return OutboxPlan(ready, changes, haltedForAuth = false)
    }
}
