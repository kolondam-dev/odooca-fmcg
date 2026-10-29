import { useEffect, useMemo, useState } from "preact/hooks";
import { Brand } from "./components/Brand";
import { ReadSession, type ReadState } from "./data/read-session";
import { money } from "./domain/format";

export function ReadApp() {
    const [state, setState] = useState<ReadState>({ phase: "idle" });
    const session = useMemo(() => new ReadSession(undefined, setState), []);
    const [tab, setTab] = useState<"outlets" | "products">("outlets");
    useEffect(() => {
        void session.load();
        const expire = () => session.checkDay();
        const offline = () =>
            session.clear(
                "Koneksi terputus. Hubungkan sesi kembali saat online.",
            );
        const revisit = () => {
            if (document.visibilityState === "hidden")
                session.clear("Tampilan dibersihkan. Hubungkan sesi kembali.");
            else expire();
        };
        const timer = window.setInterval(expire, 1000);
        window.addEventListener("offline", offline);
        document.addEventListener("visibilitychange", revisit);
        return () => {
            clearInterval(timer);
            window.removeEventListener("offline", offline);
            document.removeEventListener("visibilitychange", revisit);
            session.clear();
        };
    }, [session]);
    const busy = state.phase === "connecting" || state.phase === "syncing";
    return (
        <main class="read-shell">
            <header>
                <Brand />
                <span class="pill">STAGING · BACA SAJA</span>
            </header>
            <h1>Data kerja Sales</h1>
            <p>
                Data resmi Odoo. Daily sync tahap ini membaca katalog dan
                outlet; belum mencatat absensi atau mengirim transaksi.
            </p>
            <nav class="read-actions" aria-label="Sesi dan sinkronisasi">
                <a href="/web/login?redirect=%2Ffield%2F">
                    Masuk / ganti akun di Odoo
                </a>
                <button disabled={busy} onClick={() => void session.load()}>
                    Hubungkan sesi
                </button>
                <button
                    disabled={busy || !state.identity}
                    onClick={() => void session.load(true)}
                >
                    Daily sync
                </button>
                <button onClick={() => session.clear("Tampilan dibersihkan.")}>
                    Bersihkan tampilan
                </button>
            </nav>
            <p role="status" aria-live="polite">
                {busy
                    ? "Membaca sesi dan data Odoo…"
                    : (state.message ??
                      (state.snapshot
                          ? "Daily sync berhasil."
                          : state.identity
                            ? "Sesi terhubung. Lakukan daily sync untuk membuka daftar."
                            : "Hubungkan sesi Odoo."))}
            </p>
            {state.identity && (
                <section aria-label="Identitas sesi" class="read-card">
                    <strong>{state.identity.name}</strong>
                    <p>
                        Company {state.identity.companyId} · Hari WITA{" "}
                        {state.identity.businessDate}
                    </p>
                </section>
            )}
            {state.snapshot && (
                <>
                    <section class="read-card" aria-label="Scope sinkronisasi">
                        <p>
                            Warehouse {state.snapshot.scope?.warehouse_id} ·{" "}
                            {state.snapshot.outlets.length} outlet ·{" "}
                            {state.snapshot.products.length} SKU
                        </p>
                        <p>Terbaca: {state.snapshot.updatedAt}</p>
                        <p>
                            Data hanya disimpan dalam memori tab. Harga dan stok
                            adalah estimasi snapshot.
                        </p>
                    </section>
                    <div
                        class="read-actions"
                        role="group"
                        aria-label="Daftar kerja"
                    >
                        <button
                            aria-pressed={tab === "outlets"}
                            onClick={() => setTab("outlets")}
                        >
                            Outlet terjadwal
                        </button>
                        <button
                            aria-pressed={tab === "products"}
                            onClick={() => setTab("products")}
                        >
                            Katalog SKU
                        </button>
                    </div>
                    {tab === "outlets" ? (
                        <section aria-label="Outlet terjadwal">
                            <h2>Outlet terjadwal</h2>
                            {state.snapshot.outlets.map((outlet) => (
                                <article key={outlet.id} class="read-card">
                                    <h3>{outlet.name}</h3>
                                    <p>
                                        {outlet.channel} · {outlet.address}
                                    </p>
                                </article>
                            ))}
                        </section>
                    ) : (
                        <section aria-label="Katalog SKU">
                            <h2>Katalog SKU</h2>
                            {state.snapshot.products.map((product) => (
                                <article key={product.id} class="read-card">
                                    <h3>{product.name}</h3>
                                    <p>
                                        {product.sku_code} · {product.unit}
                                    </p>
                                    <p>
                                        {money(product.price)} / karton ·
                                        tersedia {product.stock} karton
                                    </p>
                                </article>
                            ))}
                        </section>
                    )}
                    <p>
                        Manifest Delivery, SO, approval, foto, collection, dan
                        closing belum terhubung pada tahap baca ini.
                    </p>
                </>
            )}
        </main>
    );
}
