import {
    assertLocalEvidence,
    type VisualEvidence,
} from "../domain/evidence-package";
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
import { MORNING_KEY } from "../domain/morning";
import { businessRejected } from "../domain/outbox-state";
import type { Command, Receipt } from "../domain/contracts";
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
            if (JSON.stringify(old?.value) !== JSON.stringify(expected))
                throw new Error(
                    "Data berubah di tab lain. Muat ulang sebelum mengirim.",
                );
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
