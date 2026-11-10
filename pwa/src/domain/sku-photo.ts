/**
 * Foto SKU: ditampilkan dari DB live sebagai aksi default, disimpan offline di
 * Cache Storage, dan diunduh ulang hanya bila `image_version` dari server berubah.
 * Ketiadaan foto menjadi tanggung jawab backend; UI hanya jatuh ke placeholder.
 */
const CACHE = "fmcg-sku-photos-v1";

const keyFor = (url: string, version: string) =>
    `${url}?v=${encodeURIComponent(version)}`;

/** Mengembalikan object URL foto, atau null bila belum ada/ tidak tersedia. */
export async function loadSkuPhoto(
    url: string | null | undefined,
    version: string | null | undefined,
    fetcher: typeof fetch = fetch,
): Promise<string | null> {
    if (!url) return null;
    const v = version ?? "0";
    try {
        const cache = await caches.open(CACHE);
        const key = keyFor(url, v);
        const hit = await cache.match(key);
        if (hit) return URL.createObjectURL(await hit.blob());
        // Versi baru (atau belum pernah diunduh): ambil dari server bila online.
        const res = await fetcher(url, { credentials: "same-origin" });
        if (!res.ok) return fallback(cache, url);
        const copy = res.clone();
        for (const req of await cache.keys())
            if (
                req.url.includes(url) &&
                !req.url.endsWith(`?v=${encodeURIComponent(v)}`)
            )
                await cache.delete(req);
        await cache.put(key, copy);
        return URL.createObjectURL(await res.blob());
    } catch {
        // Offline atau kegagalan: pakai versi tersimpan bila ada.
        try {
            return await fallback(await caches.open(CACHE), url);
        } catch {
            return null;
        }
    }
}

async function fallback(cache: Cache, url: string) {
    for (const req of await cache.keys())
        if (req.url.includes(url)) {
            const hit = await cache.match(req);
            if (hit) return URL.createObjectURL(await hit.blob());
        }
    return null;
}
