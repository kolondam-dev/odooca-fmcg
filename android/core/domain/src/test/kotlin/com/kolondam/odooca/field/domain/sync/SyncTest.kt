package com.kolondam.odooca.field.domain.sync

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertTrue

class SendClassifierTest {
    private val uuid = "0b9d6c52-3a41-4f4e-9d0e-2a6a8f1c7e11"

    @Test
    fun backoffDoublesAndCapsAt120Seconds() {
        assertEquals(2_000L, SendClassifier.backoffMs(1))
        assertEquals(4_000L, SendClassifier.backoffMs(2))
        assertEquals(64_000L, SendClassifier.backoffMs(6))
        assertEquals(120_000L, SendClassifier.backoffMs(7))
        assertEquals(120_000L, SendClassifier.backoffMs(50))
    }

    @Test
    fun unauthorizedRequiresLogin() {
        assertIs<SendOutcome.AuthRequired>(SendClassifier.classifyFailure(401, "x", 1, 0))
    }

    @Test
    fun definitiveClientErrorsAreRejected() {
        for (code in listOf(400, 403, 404, 409, 413, 422)) {
            val o = SendClassifier.classifyFailure(code, "x", 1, 0)
            assertIs<SendOutcome.Rejected>(o, "kode $code")
            assertEquals(code, o.httpStatus)
        }
    }

    @Test
    fun transientFailuresRetryWithBackoff() {
        for (code in listOf(408, 429, 500, 502, 503, null)) {
            val o = SendClassifier.classifyFailure(code, "x", attempts = 2, nowMs = 1_000)
            assertIs<SendOutcome.Retry>(o, "kode $code")
            assertEquals(1_000 + 4_000L, o.nextAttemptAtMs)
        }
    }

    @Test
    fun receiptStatusMapsToState() {
        fun state(status: ReceiptStatus): CommandState {
            val o = SendClassifier.classifyReceipt(uuid, Receipt(uuid, status, "ok", "SO001"))
            return (o as SendOutcome.Delivered).state
        }
        assertEquals(CommandState.ACCEPTED, state(ReceiptStatus.ACCEPTED))
        assertEquals(CommandState.NEEDS_APPROVAL, state(ReceiptStatus.NEEDS_APPROVAL))
        assertEquals(CommandState.REJECTED, state(ReceiptStatus.REJECTED))
    }

    @Test
    fun receiptUuidMustMatchCommandIgnoringCase() {
        val ok = SendClassifier.classifyReceipt(uuid, Receipt(uuid.uppercase(), ReceiptStatus.ACCEPTED, "", "R"))
        assertIs<SendOutcome.Delivered>(ok)
        val bad = SendClassifier.classifyReceipt(uuid, Receipt("other", ReceiptStatus.ACCEPTED, "", "R"))
        assertIs<SendOutcome.ProtocolMismatch>(bad)
    }

    @Test
    fun stateTransitionsFollowLifecycle() {
        assertTrue(CommandState.DRAFT.canTransitionTo(CommandState.QUEUED))
        assertFalse(CommandState.DRAFT.canTransitionTo(CommandState.ACCEPTED))
        assertTrue(CommandState.SENDING.canTransitionTo(CommandState.QUEUED))
        assertTrue(CommandState.AUTH_REQUIRED.canTransitionTo(CommandState.QUEUED))
        assertFalse(CommandState.REJECTED.canTransitionTo(CommandState.QUEUED))
        assertTrue(CommandState.REJECTED.canTransitionTo(CommandState.DRAFT))
        for (terminal in listOf(CommandState.ACCEPTED, CommandState.NEEDS_APPROVAL)) {
            assertTrue(CommandState.values().none { terminal.canTransitionTo(it) })
            assertTrue(terminal.isServerAccepted)
        }
        assertFalse(CommandState.REJECTED.isServerAccepted)
    }
}

class OutboxPlannerTest {
    private val owner = "user-1"

    private fun item(
        id: String,
        state: CommandState = CommandState.QUEUED,
        deps: List<String> = emptyList(),
        createdAt: Long = 0,
        kind: QueueKind = QueueKind.COMMAND,
        next: Long = 0,
        ownerId: String = owner,
    ) = QueueItem(id, ownerId, kind, state, createdAt, nextAttemptAtMs = next, dependsOn = deps)

    @Test
    fun dependenciesGateSendingOrder() {
        val e = item("evidence", kind = QueueKind.EVIDENCE, createdAt = 1)
        val c = item("checkin", deps = listOf("evidence"), createdAt = 2)
        val o = item("order", deps = listOf("checkin"), createdAt = 3)

        assertEquals(listOf("evidence"), OutboxPlanner.plan(listOf(e, c, o), owner, 10).send.map { it.id })

        val e2 = e.copy(state = CommandState.ACCEPTED)
        assertEquals(listOf("checkin"), OutboxPlanner.plan(listOf(e2, c, o), owner, 10).send.map { it.id })

        val c2 = c.copy(state = CommandState.NEEDS_APPROVAL)
        assertEquals(listOf("order"), OutboxPlanner.plan(listOf(e2, c2, o), owner, 10).send.map { it.id })
    }

    @Test
    fun backoffExcludesItemsUntilDue() {
        val a = item("a", next = 5_000)
        assertTrue(OutboxPlanner.plan(listOf(a), owner, 4_999).send.isEmpty())
        assertEquals(listOf("a"), OutboxPlanner.plan(listOf(a), owner, 5_000).send.map { it.id })
    }

    @Test
    fun authRequiredHaltsEverythingForThatOwner() {
        val plan = OutboxPlanner.plan(
            listOf(item("a", state = CommandState.AUTH_REQUIRED), item("b")),
            owner, 10,
        )
        assertTrue(plan.haltedForAuth)
        assertTrue(plan.send.isEmpty())
    }

    @Test
    fun ownersAreIsolated() {
        val other = item("x", state = CommandState.AUTH_REQUIRED, ownerId = "user-2")
        val mine = item("b")
        val plan = OutboxPlanner.plan(listOf(other, mine, item("y", ownerId = "user-2")), owner, 10)
        assertFalse(plan.haltedForAuth)
        assertEquals(listOf("b"), plan.send.map { it.id })
    }

    @Test
    fun rejectedDependencyBlocksTheWholeChain() {
        val e = item("evidence", state = CommandState.REJECTED, kind = QueueKind.EVIDENCE)
        val c = item("checkin", deps = listOf("evidence"))
        val o = item("order", deps = listOf("checkin"))
        val plan = OutboxPlanner.plan(listOf(e, c, o), owner, 10)
        assertTrue(plan.send.isEmpty())
        assertEquals(
            setOf("checkin" to CommandState.BLOCKED_DEPENDENCY, "order" to CommandState.BLOCKED_DEPENDENCY),
            plan.changes.map { it.id to it.to }.toSet(),
        )
    }

    @Test
    fun blockedItemRecoversWhenDependencyIsAccepted() {
        val e = item("evidence", state = CommandState.ACCEPTED, kind = QueueKind.EVIDENCE)
        val c = item("checkin", state = CommandState.BLOCKED_DEPENDENCY, deps = listOf("evidence"))
        val plan = OutboxPlanner.plan(listOf(e, c), owner, 10)
        assertEquals(listOf(StateChange("checkin", CommandState.QUEUED, "Dependensi pulih")), plan.changes)
        assertEquals(listOf("checkin"), plan.send.map { it.id })
    }

    @Test
    fun missingDependencyBlocks() {
        val plan = OutboxPlanner.plan(listOf(item("a", deps = listOf("ghost"))), owner, 10)
        assertTrue(plan.send.isEmpty())
        assertEquals(CommandState.BLOCKED_DEPENDENCY, plan.changes.single().to)
    }

    @Test
    fun orderingIsByCreationTimeThenIdAndBatchLimited() {
        val items = listOf(item("c", createdAt = 2), item("b", createdAt = 1), item("a", createdAt = 1))
        assertEquals(listOf("a", "b"), OutboxPlanner.plan(items, owner, 10, maxBatch = 2).send.map { it.id })
    }

    @Test
    fun sendingAndDraftItemsAreNeverPlanned() {
        val items = listOf(item("s", state = CommandState.SENDING), item("d", state = CommandState.DRAFT))
        assertTrue(OutboxPlanner.plan(items, owner, 10).send.isEmpty())
    }
}
