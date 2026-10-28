import { tripCloseKey } from "../domain/trip-close-contracts";
import { validateTripClose } from "../domain/trip-close";
import { validateRevisionCommit } from "../domain/order-revisions";
import { OrderRevisionSchema } from "../domain/order-revision-contracts";
import { approvalTiers } from "../domain/delivery-approval";
import { validatePod } from "../domain/delivery";
import { requireVisitFix } from "../domain/visit-validation";
import { VisitOrderSchema } from "../domain/visit-contracts";
import {
    assertLocalEvidence,
    type VisualEvidence,
} from "../domain/evidence-package";
import { validatePodCommit, assertPodSource } from "../domain/delivery";
import {
    assertCollectionSource,
    validateCollectionCommit,
} from "../domain/collection";
import { collectionSourceKey } from "../domain/collection-contracts";
import { openDB, type DBSchema, type IDBPDatabase } from "idb";
import {
    ExpenseRealizationSchema,
    receiptKey,
} from "../domain/settlement-contracts";
import {
    VISITS_KEY,
    validateVisitCommit,
    type VisitCommitGuard,
} from "../domain/visit-validation";
import { morningReady } from "../domain/morning";
import {
    DeliverySessionSchema,
    type DeliveryTask,
} from "../domain/delivery-contracts";
import {
    DELIVERY_SESSION_KEY,
    validateDeliverySession,
} from "../domain/delivery";
import { MORNING_KEY } from "../domain/morning";
import { businessRejected } from "../domain/outbox-state";
import { CommandSchema, type Command, type Receipt } from "../domain/contracts";
export type QueueState =
    | "queued"
    | "sending"
    | "accepted"
    | "needs_approval"
    | "rejected"
    | "auth_required";
export interface QueueItem {
    evidenceHold?: true;
    key: string;
    owner: string;
    command: Command;
    label: string;
    state: QueueState;
    attempts: number;
    nextAttempt: number;
    receipt?: Receipt;
    error?: string;
}
interface Value {
    key: string;
    owner: string;
    value: unknown;
}
export interface Evidence {
    visual?: VisualEvidence;
    key: string;
    owner: string;
    blob: Blob;
    capturedAt: string;
    latitude?: number;
    longitude?: number;
    accuracy?: number;
    mapStatus: "pending";
}
interface FieldDB extends DBSchema {
    outbox: { key: string; value: QueueItem; indexes: { owner: string } };
    drafts: { key: string; value: Value; indexes: { owner: string } };
    evidence: { key: string; value: Evidence; indexes: { owner: string } };
    receipts: {
        key: string;
        value: { key: string; receipt: Receipt; payload: string };
    };
}
export interface ExpenseWriteGuards {
    source: QueueItem;
    predecessor?: QueueItem;
}
export class FieldStore {
    private db: Promise<IDBPDatabase<FieldDB>>;
    constructor(name = `fmcg-field-${__DEMO__ ? "demo" : "live"}-v1`) {
        this.db = openDB<FieldDB>(name, 1, {
            upgrade(db) {
                for (const name of ["outbox", "drafts", "evidence"] as const)
                    db.createObjectStore(name, { keyPath: "key" }).createIndex(
                        "owner",
                        "owner",
                    );
                db.createObjectStore("receipts", { keyPath: "key" });
            },
        });
    }
    async list(owner: string) {
        return (await this.db).getAllFromIndex("outbox", "owner", owner);
    }
    async visitSyncState(owner: string) {
        const tx = (await this.db).transaction(
            ["outbox", "drafts"],
            "readonly",
        );
        const [rows, ledger, morning] = await Promise.all([
            tx.objectStore("outbox").index("owner").getAll(owner),
            tx.objectStore("drafts").get(`${owner}:${VISITS_KEY}`),
            tx.objectStore("drafts").get(`${owner}:${MORNING_KEY}`),
        ]);
        await tx.done;
        return { rows, ledger: ledger?.value, morning: morning?.value };
    }
    async collectionSyncState(owner: string, key: string, sourceKey: string) {
        const tx = (await this.db).transaction(
            ["outbox", "drafts"],
            "readonly",
        );
        const [rows, ledger, source] = await Promise.all([
            tx.objectStore("outbox").index("owner").getAll(owner),
            tx.objectStore("drafts").get(`${owner}:${key}`),
            tx.objectStore("drafts").get(`${owner}:${sourceKey}`),
        ]);
        await tx.done;
        return { rows, ledger: ledger?.value, source: source?.value };
    }
    async put(item: QueueItem) {
        await (await this.db).put("outbox", item);
    }
    async createDraftIfAbsent(
        owner: string,
        key: string,
        value: unknown,
    ): Promise<unknown> {
        const tx = (await this.db).transaction("drafts", "readwrite");
        const done = tx.done;
        try {
            const id = `${owner}:${key}`;
            const old = await tx.store.get(id);
            if (!old) await tx.store.add({ key: id, owner, value });
            await done;
            return old ? old.value : value;
        } catch (error) {
            await done.catch(() => {});
            throw error;
        }
    }
    async openDeliverySession(
        owner: string,
        source: DeliveryTask,
        raw: unknown,
    ) {
        const session = validateDeliverySession(
            raw,
            source,
            owner,
            new Date().toISOString(),
        );
        const openingMedia = await this.getEvidence(owner, session.opening.id);
        await assertLocalEvidence(openingMedia, session.opening, owner);
        if (!openingMedia?.visual)
            throw new Error("Opening wajib paket foto lengkap.");
        requireVisitFix(
            {
                latitude: session.opening.latitude,
                longitude: session.opening.longitude,
                accuracy: session.opening.accuracy,
                sampled_at: openingMedia.visual.fixSampledAt,
            },
            source.site,
            Date.parse(session.opened_at),
        );
        if (Date.now() - Date.parse(session.opened_at) > 60000)
            throw new Error("Opening sesi kedaluwarsa; ambil bukti baru.");
        const tx = (await this.db).transaction(
                ["drafts", "outbox"],
                "readwrite",
            ),
            done = tx.done;
        try {
            const drafts = tx.objectStore("drafts"),
                key = `${owner}:${DELIVERY_SESSION_KEY}`;
            if (
                await drafts.get(
                    `${owner}:${tripCloseKey(source.trip, source.business_date)}`,
                )
            )
                throw new Error(
                    "Trip sudah closed lokal; pembukaan sesi membutuhkan review.",
                );
            const prior = (await drafts.get(key))?.value as
                | { closed?: string; session?: unknown }
                | undefined;
            if (prior && !prior.closed)
                throw new Error(
                    "Masih ada sesi delivery aktif; tutup sesi sebelumnya.",
                );
            if (prior) {
                const previous = DeliverySessionSchema.parse(prior.session);
                const closed = await tx
                    .objectStore("outbox")
                    .get(`${owner}:${prior.closed}`);
                if (
                    !closed ||
                    closed.owner !== owner ||
                    closed.command.type !== "delivery.pod.submit" ||
                    JSON.stringify(closed.command.payload.session) !==
                        JSON.stringify(previous)
                )
                    throw new Error(
                        "Riwayat sesi delivery rusak; perlu review.",
                    );
            }
            const rows = await tx
                .objectStore("outbox")
                .index("owner")
                .getAll(owner);
            if (
                rows.some(
                    (r) =>
                        r.command.type === "delivery.pod.submit" &&
                        (r.command.payload.evidence.id === session.opening.id ||
                            r.command.payload.session?.opening.id ===
                                session.opening.id),
                )
            )
                throw new Error("Foto opening sudah dipakai sesi lain.");
            const morning = (await drafts.get(`${owner}:${MORNING_KEY}`))
                ?.value;
            if (
                JSON.stringify(morning) !==
                    JSON.stringify(session.daily_source) ||
                !morningReady(morning, owner)
            )
                throw new Error("Daily sync berubah/kedaluwarsa.");
            assertPodSource(
                (
                    await drafts.get(
                        `${owner}:delivery-manifest-v1:${source.business_date}`,
                    )
                )?.value,
                source,
            );
            await drafts.put({ key, owner, value: { session } });
            await done;
            return session;
        } catch (error) {
            tx.abort();
            await done.catch(() => {});
            throw error;
        }
    }
    async putWithDraft(
        item: QueueItem,
        key: string,
        value: unknown,
        expected: unknown,
        guards?: ExpenseWriteGuards,
        visitGuard?: VisitCommitGuard,
    ) {
        const tx = (await this.db).transaction(
            ["outbox", "drafts"],
            "readwrite",
        );
        const done = tx.done;
        try {
            const id = `${item.owner}:${key}`;
            const old = await tx.objectStore("drafts").get(id);
            const canonical = (value: unknown) =>
                ["delivery.pod.submit", "collection.receipt.submit"].includes(
                    item.command.type,
                ) && value !== undefined
                    ? CommandSchema.parse(value)
                    : value;
            if (
                JSON.stringify(canonical(old?.value)) !==
                JSON.stringify(canonical(expected))
            )
                throw new Error(
                    "Data berubah di tab lain. Muat ulang sebelum mengirim.",
                );
            if (item.command.type === "delivery.trip.close") {
                const p = validateTripClose(
                    item,
                    await tx
                        .objectStore("outbox")
                        .index("owner")
                        .getAll(item.owner),
                    item.owner,
                );
                const morning = (
                    await tx
                        .objectStore("drafts")
                        .get(`${item.owner}:${MORNING_KEY}`)
                )?.value;
                const active = (
                    await tx
                        .objectStore("drafts")
                        .get(`${item.owner}:${DELIVERY_SESSION_KEY}`)
                )?.value as { closed?: string } | undefined;
                if (
                    key !== tripCloseKey(p.trip_id, p.business_date) ||
                    old ||
                    JSON.stringify(CommandSchema.parse(value)) !==
                        JSON.stringify(item.command) ||
                    JSON.stringify(morning) !==
                        JSON.stringify(p.daily_source) ||
                    !morningReady(morning, item.owner) ||
                    (active && !active.closed)
                )
                    throw new Error(
                        "Sesi aktif/sumber closing berubah; tidak dapat tutup trip.",
                    );
            }
            if (item.command.type === "sales.order.revise") {
                validateRevisionCommit(
                    item,
                    await tx
                        .objectStore("outbox")
                        .index("owner")
                        .getAll(item.owner),
                    key,
                    value,
                    old?.value,
                    guards?.source,
                    (
                        await tx
                            .objectStore("drafts")
                            .get(`${item.owner}:${MORNING_KEY}`)
                    )?.value,
                    (
                        await tx
                            .objectStore("drafts")
                            .get(`${item.owner}:${VISITS_KEY}`)
                    )?.value,
                );
            }
            if (item.command.type === "delivery.pod.submit") {
                const payload = item.command.payload;
                if (
                    await tx
                        .objectStore("drafts")
                        .get(
                            `${item.owner}:${tripCloseKey(payload.source.trip, payload.source.business_date)}`,
                        )
                )
                    throw new Error(
                        "Trip sudah closed lokal; perubahan membutuhkan review.",
                    );
                if (payload.source.workflow_version === 2) {
                    const session = DeliverySessionSchema.parse(
                        payload.session,
                    );
                    const current = (
                        await tx
                            .objectStore("drafts")
                            .get(`${item.owner}:${DELIVERY_SESSION_KEY}`)
                    )?.value as
                        | { session?: unknown; closed?: string }
                        | undefined;
                    const morning = (
                        await tx
                            .objectStore("drafts")
                            .get(`${item.owner}:${MORNING_KEY}`)
                    )?.value;
                    if (
                        !current ||
                        current.closed ||
                        JSON.stringify(current.session) !==
                            JSON.stringify(session) ||
                        JSON.stringify(morning) !==
                            JSON.stringify(session.daily_source) ||
                        !morningReady(morning, item.owner)
                    )
                        throw new Error(
                            "Sesi delivery/daily sync berubah sebelum closing.",
                        );
                    await tx.objectStore("drafts").put({
                        key: `${item.owner}:${DELIVERY_SESSION_KEY}`,
                        owner: item.owner,
                        value: {
                            session,
                            closed: item.command.client_uuid,
                        },
                    });
                }
                if (item.command.payload.supersedes_uuid) {
                    if (
                        !guards ||
                        guards.source.command.client_uuid !==
                            item.command.payload.supersedes_uuid ||
                        guards.source.owner !== item.owner ||
                        JSON.stringify(
                            await tx
                                .objectStore("outbox")
                                .get(guards.source.key),
                        ) !== JSON.stringify(guards.source)
                    )
                        throw new Error(
                            "Parent/receipt POD berubah saat menyimpan koreksi.",
                        );
                }
                assertPodSource(
                    (
                        await tx
                            .objectStore("drafts")
                            .get(
                                `${item.owner}:delivery-manifest-v1:${item.command.payload.source.business_date}`,
                            )
                    )?.value,
                    item.command.payload.source,
                );
                validatePodCommit(
                    item,
                    key,
                    value,
                    await tx
                        .objectStore("outbox")
                        .index("owner")
                        .getAll(item.owner),
                    old?.value,
                );
            }
            if (item.command.type === "collection.receipt.submit") {
                assertCollectionSource(
                    (
                        await tx
                            .objectStore("drafts")
                            .get(
                                `${item.owner}:${collectionSourceKey(item.command.payload.source)}`,
                            )
                    )?.value,
                    item.command.payload.source,
                );
                if (item.command.payload.supersedes_uuid) {
                    if (
                        !guards ||
                        guards.source.owner !== item.owner ||
                        guards.source.command.client_uuid !==
                            item.command.payload.supersedes_uuid ||
                        JSON.stringify(
                            await tx
                                .objectStore("outbox")
                                .get(guards.source.key),
                        ) !== JSON.stringify(guards.source)
                    )
                        throw new Error("Parent/receipt collection berubah.");
                }
                validateCollectionCommit(
                    item,
                    key,
                    value,
                    await tx
                        .objectStore("outbox")
                        .index("owner")
                        .getAll(item.owner),
                    old?.value,
                );
            }
            if (visitGuard) {
                if (key !== VISITS_KEY)
                    throw new Error(
                        "Transaksi kunjungan memakai key yang salah.",
                    );
                const morning = (
                    await tx
                        .objectStore("drafts")
                        .get(`${item.owner}:${MORNING_KEY}`)
                )?.value;
                if (
                    JSON.stringify(morning) !==
                    JSON.stringify(visitGuard.morning)
                )
                    throw new Error(
                        "Sesi/paket pagi berubah saat menyimpan kunjungan. Muat ulang.",
                    );
                validateVisitCommit(
                    item,
                    old?.value,
                    value,
                    morning,
                    await tx
                        .objectStore("outbox")
                        .index("owner")
                        .getAll(item.owner),
                );
            }
            if (item.command.type === "field_expense.realization.submit") {
                if (
                    !guards ||
                    guards.source.owner !== item.owner ||
                    guards.source.key !==
                        `${item.owner}:${item.command.payload.source_request_uuid}` ||
                    JSON.stringify(
                        await tx.objectStore("outbox").get(guards.source.key),
                    ) !== JSON.stringify(guards.source)
                )
                    throw new Error(
                        "Pengajuan berubah saat pengiriman. Muat ulang dan review sumber.",
                    );
                const body = ExpenseRealizationSchema.parse(
                    item.command.payload,
                );
                if (!!body.supersedes_uuid !== !!body.correction_reason)
                    throw new Error("Koreksi memerlukan referensi dan alasan.");
                if (body.supersedes_uuid) {
                    if (
                        !guards.predecessor ||
                        !businessRejected(guards.predecessor) ||
                        guards.predecessor.owner !== item.owner ||
                        guards.predecessor.command.type !==
                            "field_expense.realization.submit" ||
                        guards.predecessor.command.payload
                            .source_request_uuid !== body.source_request_uuid ||
                        guards.predecessor.command.payload.advance_reference !==
                            body.advance_reference ||
                        guards.predecessor.command.client_uuid !==
                            body.supersedes_uuid ||
                        JSON.stringify(
                            await tx
                                .objectStore("outbox")
                                .get(guards.predecessor.key),
                        ) !== JSON.stringify(guards.predecessor)
                    )
                        throw new Error(
                            "Penolakan bisnis berubah. Koreksi ditahan.",
                        );
                } else if (guards.predecessor)
                    throw new Error("Referensi revisi wajib diisi.");
                const keys = body.lines.map(receiptKey);
                if (new Set(keys).size !== keys.length)
                    throw new Error(
                        "Struk yang sama tidak boleh dihitung dua kali.",
                    );
                // Scan inside the same read/write transaction, including legacy
                // queued rows: competing advances/tabs cannot both reserve a receipt.
                for (const q of await tx
                    .objectStore("outbox")
                    .index("owner")
                    .getAll(item.owner)) {
                    if (
                        q.command.type !== "field_expense.realization.submit" ||
                        businessRejected(q)
                    )
                        continue;
                    const prior = ExpenseRealizationSchema.safeParse(
                        q.command.payload,
                    );
                    if (!prior.success)
                        throw new Error(
                            "Antrean realisasi lama tidak valid. Periksa data sebelum mengirim.",
                        );
                    if (
                        prior.data.lines.some((line) =>
                            keys.includes(receiptKey(line)),
                        )
                    )
                        throw new Error(
                            "Struk sudah dipakai realisasi lain pada perangkat ini.",
                        );
                }
            }
            await Promise.all([
                tx.objectStore("outbox").add(item),
                tx
                    .objectStore("drafts")
                    .put({ key: id, owner: item.owner, value }),
                done,
            ]);
        } catch (error) {
            try {
                tx.abort();
            } catch {
                /* Transaction may already be aborted. */
            }
            await done.catch(() => {});
            throw error;
        }
    }
    async draft(owner: string, key: string, value?: unknown): Promise<unknown> {
        const db = await this.db;
        const id = `${owner}:${key}`;
        if (value !== undefined) {
            await db.put("drafts", { key: id, owner, value });
            return value;
        }
        return (await db.get("drafts", id))?.value;
    }
    async removeDraft(owner: string, key: string) {
        await (await this.db).delete("drafts", `${owner}:${key}`);
    }
    async saveEvidence(e: Evidence) {
        if (e.visual)
            await assertLocalEvidence(
                e,
                {
                    id: e.key.slice(e.owner.length + 1),
                    capturedAt: e.capturedAt,
                    latitude: e.latitude!,
                    longitude: e.longitude!,
                    accuracy: e.accuracy!,
                    packageHash: e.visual.bindingSha256,
                },
                e.owner,
            );
        const tx = (await this.db).transaction("evidence", "readwrite");
        const done = tx.done;
        try {
            const prior = await tx.store.get(e.key);
            if (prior?.visual || (e.visual && prior))
                throw new Error(
                    "Paket bukti tersimpan immutable. Buat bukti baru.",
                );
            await tx.store.put(e);
            await done;
        } catch (error) {
            try {
                tx.abort();
            } catch {}
            await done.catch(() => {});
            throw error;
        }
    }
    async getEvidence(owner: string, id: string) {
        const value = await (await this.db).get("evidence", `${owner}:${id}`);
        return value?.owner === owner ? value : undefined;
    }
    async listEvidence(owner: string) {
        return (await this.db).getAllFromIndex("evidence", "owner", owner);
    }
    async decideDemoDelivery(
        owner: string,
        expected: QueueItem,
        role: "spv" | "branch_manager",
        approved: boolean,
        reason: string,
    ) {
        if (
            !__DEMO__ ||
            expected.owner !== owner ||
            expected.command.type !== "delivery.pod.submit" ||
            expected.state !== "needs_approval" ||
            expected.receipt?.client_uuid !== expected.command.client_uuid ||
            expected.receipt.status !== "needs_approval" ||
            reason.trim().length < 3 ||
            reason.length > 500
        )
            throw new Error("Approval delivery tidak valid.");
        const p = validatePod(
            expected.command.payload,
            owner,
            expected.command.occurred_at,
        );
        if (!p.request) throw new Error("Bukan request pending/cancel.");
        const tiers = approvalTiers(p.request, p.source.business_date);
        const tx = (await this.db).transaction(
                ["outbox", "drafts", "receipts"],
                "readwrite",
            ),
            done = tx.done;
        try {
            if (
                JSON.stringify(
                    await tx.objectStore("outbox").get(expected.key),
                ) !== JSON.stringify(expected)
            )
                throw new Error("Receipt berubah; muat ulang.");
            const key = `${owner}:delivery-approval-v1:${expected.command.client_uuid}`;
            const prior = (await tx.objectStore("drafts").get(key))?.value as
                | {
                      role: string;
                      approved: boolean;
                      reason: string;
                      at: string;
                  }[]
                | undefined;
            const decisions = prior ?? [];
            if (
                decisions.some((d, i) => !d.approved || d.role !== tiers[i]) ||
                tiers[decisions.length] !== role
            )
                throw new Error(
                    "Urutan approval wajib SPV lalu Branch Manager.",
                );
            const next = [
                ...decisions,
                {
                    role,
                    approved,
                    reason: reason.trim(),
                    at: new Date().toISOString(),
                },
            ];
            const status: Receipt["status"] = !approved
                ? "rejected"
                : next.length === tiers.length
                  ? "accepted"
                  : "needs_approval";
            const receipt: Receipt = {
                ...expected.receipt!,
                status,
                message: `SIMULASI ${p.request.kind === "cancel" ? `Cancel: ${p.request.sub_reason}` : `Kirim ulang: ${p.request.requested_date}`} · ${next.map((d) => `${d.role}: ${d.approved ? "disetujui" : "ditolak"} (${d.reason})`).join(" → ")}${status === "needs_approval" ? " · menunggu Branch Manager" : ""}. Bukan approval/posting Odoo.`,
            };
            await tx.objectStore("drafts").put({ key, owner, value: next });
            await tx
                .objectStore("outbox")
                .put({ ...expected, state: status, receipt });
            const cachedKey = `${owner.slice(owner.indexOf(":") + 1)}:delivery.pod.submit:${expected.command.client_uuid}`,
                cached = await tx.objectStore("receipts").get(cachedKey);
            if (cached)
                await tx.objectStore("receipts").put({ ...cached, receipt });
            await done;
        } catch (error) {
            try {
                tx.abort();
            } catch {}
            await done.catch(() => {});
            throw error;
        }
    }
    async decideDemoDiscount(
        owner: string,
        expected: QueueItem,
        approved: boolean,
        reason: string,
    ) {
        if (!__DEMO__) throw new Error("Simulator tidak tersedia di live.");
        if (reason.trim().length < 3 || reason.length > 500)
            throw new Error("Alasan keputusan wajib 3–500 karakter.");
        const body =
            expected.command.type === "sales.order.revise"
                ? OrderRevisionSchema.parse(expected.command.payload)
                : VisitOrderSchema.parse(expected.command.payload);
        if (
            expected.owner !== owner ||
            !["sales.order.submit", "sales.order.revise"].includes(
                expected.command.type,
            ) ||
            (!body.discount_request &&
                expected.command.type !== "sales.order.revise") ||
            expected.state !== "needs_approval" ||
            expected.receipt?.client_uuid !== expected.command.client_uuid ||
            expected.receipt.status !== "needs_approval"
        )
            throw new Error("Bukan pengajuan diskon pending yang cocok.");
        const tx = (await this.db).transaction(
                ["outbox", "receipts"],
                "readwrite",
            ),
            done = tx.done;
        try {
            if (
                JSON.stringify(
                    await tx.objectStore("outbox").get(expected.key),
                ) !== JSON.stringify(expected)
            )
                throw new Error("Receipt berubah di tab lain.");
            const receipt: Receipt = {
                ...expected.receipt!,
                status: approved ? "accepted" : "rejected",
                message: `SIMULASI diskon: diminta ${body.discount_request?.percent ?? 0}%, disetujui ${approved ? (body.discount_request?.percent ?? 0) : 0}%. ${approved ? `Total disetujui Rp ${body.observed_total}` : "Pengajuan ditolak; tidak ada total disetujui"}. ${reason.trim()}. Bukan keputusan Odoo.`,
            };
            await tx
                .objectStore("outbox")
                .put({ ...expected, state: receipt.status, receipt });
            const cachedKey = `${owner.slice(owner.indexOf(":") + 1)}:${expected.command.type}:${expected.command.client_uuid}`;
            const cached = await tx.objectStore("receipts").get(cachedKey);
            if (cached)
                await tx.objectStore("receipts").put({ ...cached, receipt });
            await done;
        } catch (error) {
            tx.abort();
            await done.catch(() => {});
            throw error;
        }
    }
    async receipt(key: string) {
        return (await this.db).get("receipts", key);
    }
    async saveReceipt(key: string, receipt: Receipt, payload: string) {
        await (await this.db).put("receipts", { key, receipt, payload });
    }
    async close() {
        (await this.db).close();
    }
}
