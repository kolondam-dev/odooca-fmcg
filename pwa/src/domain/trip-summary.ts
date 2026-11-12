import type { QueueItem } from "../storage/store";

const money = (v: unknown) => (Number.isFinite(Number(v)) ? Number(v) : 0);
const payloadOf = (q: QueueItem) =>
    (q.command.payload ?? {}) as Record<string, unknown>;
const wita = (iso: string) =>
    new Date(iso).toLocaleDateString("sv-SE", { timeZone: "Asia/Makassar" });

/**
 * Ringkasan uang satu trip dari antrean lokal (hanya baca): perintah pengguna ini pada
 * hari kerja aktif, tidak ditolak, kuitansi terkoreksi tidak dihitung, dibatasi ke trip.
 */
export function tripMoney(
    queue: QueueItem[],
    owner: string,
    businessDate: string | undefined,
    trip: string,
) {
    const live = (type: string) =>
        queue.filter(
            (q) =>
                q?.owner === owner &&
                q.command?.type === type &&
                q.state !== "rejected" &&
                !!businessDate &&
                wita(q.command.occurred_at) === businessDate,
        );
    const all = live("collection.receipt.submit");
    const superseded = new Set(
        all.map((q) => payloadOf(q).supersedes_uuid).filter(Boolean),
    );
    const receipts = all.filter(
        (q) =>
            !superseded.has(q.command.client_uuid) &&
            (payloadOf(q).source as { delivery?: { trip?: string } })?.delivery
                ?.trip === trip,
    );
    const by = (method: string) =>
        receipts
            .filter((q) => payloadOf(q).method === method)
            .reduce((a, q) => a + money(payloadOf(q).amount), 0);
    const cost = live("field_expense.request")
        .filter(
            (q) =>
                payloadOf(q).trip_id === trip &&
                payloadOf(q).scheduled_date === businessDate,
        )
        .reduce((a, q) => a + money(payloadOf(q).amount), 0);
    const cashReceiptUuids = receipts
        .filter((q) => payloadOf(q).method === "cash")
        .map((q) => q.command.client_uuid);
    return {
        cash: by("cash"),
        transfer: by("transfer"),
        cost,
        cashReceiptUuids,
    };
}
