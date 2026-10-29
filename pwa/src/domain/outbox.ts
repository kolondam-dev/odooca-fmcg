import { validateTripCloseMedia } from "./trip-close";
import { validateRevisionMedia } from "./order-revisions";
import { validateCollectionMedia } from "./collection";
import { validatePodMedia } from "./delivery";
import {
    validatePackagedCommandEvidence,
    EvidenceIntegrityError,
} from "./evidence-package";
import { visitDependenciesReady } from "./visit-dependencies";
import { validateVisitSync, type VisitCommitGuard } from "./visit-validation";
import {
    ApiError,
    CommandSchema,
    ReceiptSchema,
    type Command,
    type FieldProvider,
} from "./contracts";
import {
    FieldStore,
    type QueueItem,
    type ExpenseWriteGuards,
} from "../storage/store";
export class Outbox {
    private running?: Promise<void>;
    private retryRunning?: Promise<void>;
    constructor(
        private store: FieldStore,
        private owner: string,
        private provider: FieldProvider,
        private changed: () => void = () => {},
    ) {}
    async enqueue(
        type: Command["type"],
        payload: Record<string, unknown>,
        label: string,
        uuid = crypto.randomUUID(),
        draftWrite?: {
            key: string;
            value: unknown;
            expected: unknown;
            guards?: ExpenseWriteGuards;
            visitGuard?: VisitCommitGuard;
            occurredAt?: string;
        },
    ) {
        if (type === "delivery.trip.close" && !draftWrite)
            throw new Error("Closing wajib CAS trip.");
        if (type === "sales.order.revise" && !draftWrite?.guards)
            throw new Error("Revisi wajib snapshot parent dan CAS.");
        if (
            type === "delivery.pod.submit" &&
            payload.supersedes_uuid &&
            !draftWrite?.guards
        )
            throw new Error("Koreksi POD wajib snapshot parent receipt.");
        if (type === "delivery.pod.submit" && !draftWrite)
            throw new Error("POD wajib transaksi manifest atomik.");
        if (
            type === "collection.receipt.submit" &&
            payload.supersedes_uuid &&
            !draftWrite?.guards
        )
            throw new Error("Koreksi collection wajib snapshot parent.");
        if (type === "collection.receipt.submit" && !draftWrite)
            throw new Error("Collection wajib transaksi tagihan atomik.");
        if (type === "field_expense.realization.submit" && !draftWrite?.guards)
            throw new Error(
                "Realisasi harus memakai transaksi sumber/struk dan advance.",
            );
        if (
            (type === "sales.visit.check_in" ||
                type === "sales.visit.check_out" ||
                (type === "sales.order.submit" && payload.visit_context)) &&
            !draftWrite?.visitGuard
        )
            throw new Error(
                "Kunjungan/order memerlukan transaksi sesi dan geofence.",
            );
        const command = CommandSchema.parse({
            schema_version: 1,
            client_uuid: uuid,
            type,
            occurred_at: draftWrite?.occurredAt ?? new Date().toISOString(),
            payload,
        });
        const existing = (await this.store.list(this.owner)).find(
            (x) => x.command.client_uuid === uuid,
        );
        if (existing) throw new Error("Command UUID sudah digunakan.");
        const item: QueueItem = {
            key: `${this.owner}:${uuid}`,
            owner: this.owner,
            command,
            label,
            state: "queued",
            attempts: 0,
            nextAttempt: 0,
        };
        if (draftWrite)
            await this.store.putWithDraft(
                item,
                draftWrite.key,
                draftWrite.value,
                draftWrite.expected,
                draftWrite.guards,
                draftWrite.visitGuard,
            );
        else await this.store.put(item);
        this.changed();
        return item;
    }
    flush() {
        if (this.running) return this.running;
        const task = this.send().finally(() => {
            if (this.running === task) this.running = undefined;
        });
        this.running = task;
        return task;
    }
    private async send() {
        let progress = true;
        while (progress) {
            progress = false;
            for (const item of await this.store.list(this.owner)) {
                if (
                    !["queued", "sending"].includes(item.state) ||
                    item.nextAttempt > Date.now()
                )
                    continue;
                try {
                    const state = await this.store.visitSyncState(this.owner);
                    validateVisitSync(
                        item,
                        this.owner,
                        state.ledger,
                        state.rows,
                        state.morning,
                    );
                    if (
                        !visitDependenciesReady(
                            item.command,
                            this.owner,
                            state.rows,
                        )
                    ) {
                        const message =
                            "Menunggu receipt check-in/order sebelumnya. Transaksi tetap lokal.";
                        if (item.error !== message) {
                            item.error = message;
                            await this.store.put(item);
                            this.changed();
                        }
                        continue;
                    }
                } catch {
                    item.error =
                        "Integritas antrean/sumber kunjungan tidak valid. Data tetap lokal; perlu review.";
                    await this.store.put(item);
                    this.changed();
                    continue;
                }
                item.state = "sending";
                item.attempts++;
                await this.store.put(item);
                this.changed();
                try {
                    try {
                        await validateCollectionMedia(
                            item,
                            this.owner,
                            this.store,
                        );
                        await validatePodMedia(item, this.owner, this.store);
                        await validateRevisionMedia(
                            item,
                            this.owner,
                            this.store,
                        );
                        await validateTripCloseMedia(
                            item,
                            this.owner,
                            this.store,
                        );
                        await validatePackagedCommandEvidence(
                            item.command,
                            this.owner,
                            this.store,
                        );
                        delete item.evidenceHold;
                        const state = await this.store.visitSyncState(
                            this.owner,
                        );
                        validateVisitSync(
                            item,
                            this.owner,
                            state.ledger,
                            state.rows,
                            state.morning,
                        );
                        if (
                            !visitDependenciesReady(
                                item.command,
                                this.owner,
                                state.rows,
                            )
                        )
                            throw new Error("Dependency berubah");
                    } catch (error) {
                        if (error instanceof EvidenceIntegrityError)
                            item.evidenceHold = true;
                        throw new Error(
                            "Integritas transaksi/sumber berubah sebelum kirim; perlu review.",
                        );
                    }
                    await validatePodMedia(item, this.owner, this.store);
                    await validateCollectionMedia(item, this.owner, this.store);
                    await validateRevisionMedia(item, this.owner, this.store);
                    await validateTripCloseMedia(item, this.owner, this.store);
                    const receipt = ReceiptSchema.parse(
                        await this.provider.submit(item.command),
                    );
                    if (receipt.client_uuid !== item.command.client_uuid)
                        throw new Error("Receipt UUID tidak cocok.");
                    progress = true;
                    item.receipt = receipt;
                    item.state = receipt.status;
                    delete item.error;
                } catch (error) {
                    const status = error instanceof ApiError ? error.status : 0;
                    item.error =
                        error instanceof Error
                            ? error.message
                            : "Sinkronisasi gagal.";
                    item.state =
                        status === 401
                            ? "auth_required"
                            : status >= 400 &&
                                status < 500 &&
                                ![408, 429].includes(status)
                              ? "rejected"
                              : "queued";
                    item.nextAttempt =
                        Date.now() +
                        Math.min(
                            120_000,
                            1000 * 2 ** Math.min(item.attempts, 7),
                        );
                }
                await this.store.put(item);
                this.changed();
                if (item.state === "auth_required") return;
            }
        }
    }
    retry() {
        if (this.retryRunning) return this.retryRunning;
        const previous = this.running;
        // Reserve the engine before any IDB await. Reconnect must wait for the
        // in-flight attempt (including error/backoff writes and media hashes),
        // then clear backoff and start one fresh pass. Concurrent flush/retry
        // callers join this task instead of modifying its source snapshot.
        const task = (async () => {
            if (previous) await previous;
            for (const item of await this.store.list(this.owner)) {
                if (item.state === "queued") {
                    item.nextAttempt = 0;
                    await this.store.put(item);
                }
            }
            await this.send();
        })().finally(() => {
            if (this.running === task) this.running = undefined;
            if (this.retryRunning === task) this.retryRunning = undefined;
        });
        this.running = task;
        this.retryRunning = task;
        return task;
    }
}
