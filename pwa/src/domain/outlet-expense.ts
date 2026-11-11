/**
 * Kirim komponen biaya toko satu per satu tanpa duplikasi saat retry:
 * komponen yang sudah masuk antrean dicatat di `done` dan dilewati pada percobaan berikutnya.
 */
export async function submitPending<T extends { key: string }>(
    items: T[],
    done: Set<string>,
    send: (item: T, last: boolean) => Promise<void>,
) {
    const todo = items.filter((i) => !done.has(i.key));
    for (const [index, item] of todo.entries()) {
        await send(item, index === todo.length - 1);
        done.add(item.key);
    }
}
