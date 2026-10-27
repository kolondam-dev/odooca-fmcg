import { openDB, type DBSchema, type IDBPDatabase } from "idb";
import type { Command, Receipt } from "../domain/contracts";
export type QueueState =
    | "queued"
    | "sending"
    | "accepted"
    | "needs_approval"
    | "rejected"
    | "auth_required";
export interface QueueItem {
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
interface Evidence {
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
        await (await this.db).put("evidence", e);
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
