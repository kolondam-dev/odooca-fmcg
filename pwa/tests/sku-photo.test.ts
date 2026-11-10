import { beforeEach, describe, expect, it, vi } from "vitest";
import { loadSkuPhoto } from "../src/domain/sku-photo";

function fakeCaches() {
    const store = new Map<string, Response>();
    const cache = {
        match: async (k: string) => store.get(k)?.clone(),
        put: async (k: string, r: Response) => void store.set(k, r),
        keys: async () =>
            [...store.keys()].map((u) => ({ url: `https://x${u}` })),
        delete: async (req: { url: string }) =>
            store.delete(req.url.replace("https://x", "")),
    };
    // @ts-expect-error uji
    globalThis.caches = { open: async () => cache };
    cache.match = async (k: string | { url: string }) =>
        store
            .get(typeof k === "string" ? k : k.url.replace("https://x", ""))
            ?.clone();
    return store;
}

const URL_ = "/api/v1/products/7/image";
beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:foto");
});

describe("foto SKU offline", () => {
    it("tanpa image_url -> placeholder (null)", async () => {
        fakeCaches();
        expect(await loadSkuPhoto(null, null)).toBeNull();
    });
    it("unduh sekali, lalu pakai cache selama versi sama", async () => {
        fakeCaches();
        const f = vi.fn(async () => new Response("img"));
        expect(await loadSkuPhoto(URL_, "v1", f as never)).toBe("blob:foto");
        expect(await loadSkuPhoto(URL_, "v1", f as never)).toBe("blob:foto");
        expect(f).toHaveBeenCalledTimes(1);
    });
    it("versi berubah -> unduh ulang dan buang versi lama", async () => {
        const store = fakeCaches();
        const f = vi.fn(async () => new Response("img"));
        await loadSkuPhoto(URL_, "v1", f as never);
        await loadSkuPhoto(URL_, "v2", f as never);
        expect(f).toHaveBeenCalledTimes(2);
        expect([...store.keys()]).toEqual([`${URL_}?v=v2`]);
    });
    it("offline memakai foto tersimpan; tanpa tersimpan -> null", async () => {
        fakeCaches();
        const ok = vi.fn(async () => new Response("img"));
        await loadSkuPhoto(URL_, "v1", ok as never);
        const down = vi.fn(async () => {
            throw new Error("offline");
        });
        expect(await loadSkuPhoto(URL_, "v2", down as never)).toBe("blob:foto");
        fakeCaches();
        expect(await loadSkuPhoto(URL_, "v1", down as never)).toBeNull();
    });
    it("respons 404 dari server -> placeholder", async () => {
        fakeCaches();
        const f = vi.fn(async () => new Response("", { status: 404 }));
        expect(await loadSkuPhoto(URL_, "v1", f as never)).toBeNull();
    });
});
