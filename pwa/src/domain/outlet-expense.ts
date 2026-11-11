/**
 * Biaya toko disimpan sebagai satu pengajuan per komponen. Agar retry/buka ulang formulir tidak
 * menggandakan, tiap komponen memiliki client UUID tetap yang disimpan dalam rencana batch (draft
 * lokal). Sumber kebenaran "sudah masuk antrean" adalah antrean itu sendiri, bukan state komponen.
 */
export type StoreBatchItem = {
    key: string;
    uuid: string;
    payload: Record<string, unknown>;
    label: string;
};
export type StoreBatch = { batch_id: string; items: StoreBatchItem[] };

export const storeBatchKey = (outletId: string, businessDate: string) =>
    `store-expense-batch:${outletId}:${businessDate}`;

export function isStoreBatch(value: unknown): value is StoreBatch {
    const v = value as StoreBatch | undefined;
    return (
        !!v &&
        typeof v.batch_id === "string" &&
        Array.isArray(v.items) &&
        v.items.every(
            (i) =>
                typeof i?.key === "string" &&
                typeof i?.uuid === "string" &&
                !!i.payload &&
                typeof i.label === "string",
        )
    );
}

/** Kirim komponen yang belum ada di antrean; komponen yang sudah ada dilewati. */
export async function submitPending(
    items: StoreBatchItem[],
    queuedUuids: ReadonlySet<string>,
    send: (item: StoreBatchItem, last: boolean) => Promise<void>,
) {
    const todo = items.filter((i) => !queuedUuids.has(i.uuid));
    for (const [index, item] of todo.entries())
        await send(item, index === todo.length - 1);
}
