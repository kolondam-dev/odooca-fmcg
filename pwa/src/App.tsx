import type { ComponentChildren } from "preact";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { createProvider } from "./data/provider";
import {
    canOpen,
    ownerKey,
    validateOrder,
    type Command,
    type FieldProvider,
    type Identity,
    type Scenario,
    type Snapshot,
} from "./domain/contracts";
import { validateExpense } from "./domain/expense";
import { Brand } from "./components/Brand";
import { MorningSession } from "./components/MorningSession";
import { morningReady, type MorningRecord } from "./domain/morning";
import { Outbox } from "./domain/outbox";
import { haptic, money, queueLabels, time } from "./domain/format";
import { FieldStore, type QueueItem } from "./storage/store";
import { Icon, type IconName } from "./components/Icon";
import { EvidenceCapture, type EvidenceRef } from "./components/Evidence";

type Page = "home" | "sales" | "delivery" | "hris" | "more";
type Dialog =
    | { type: "order"; outlet: string }
    | { type: "extra" }
    | { type: "proof"; delivery: string }
    | { type: "expense"; trip?: string }
    | { type: "attendance" }
    | { type: "leave" };
const pages: { id: Page; name: string; icon: IconName }[] = [
    { id: "home", name: "Beranda", icon: "house" },
    { id: "sales", name: "Sales", icon: "store" },
    { id: "delivery", name: "Delivery", icon: "truck" },
    { id: "hris", name: "HRIS", icon: "user" },
    { id: "more", name: "Lainnya", icon: "grid" },
];
const store = new FieldStore();
const dateLabel = () =>
    new Intl.DateTimeFormat("id-ID", {
        weekday: "long",
        day: "numeric",
        month: "long",
        timeZone: "Asia/Makassar",
    }).format(new Date());
function Pill({
    children,
    tone = "",
}: {
    children: ComponentChildren;
    tone?: string;
}) {
    return <span class={`pill ${tone}`}>{children}</span>;
}
function Heading({
    title,
    note,
    action,
}: {
    title: string;
    note: string;
    action?: ComponentChildren;
}) {
    return (
        <div class="section-heading">
            <div>
                <h2>{title}</h2>
                <p class="muted">{note}</p>
            </div>
            {action}
        </div>
    );
}
function Empty({ text }: { text: string }) {
    return (
        <div class="empty">
            <Icon name="check" size={32} />
            <p>{text}</p>
        </div>
    );
}
export function App() {
    if (!__DEMO__)
        return (
            <main class="boot">
                <Brand large />
                <h1 class="sr-only">Odoo FMCG Mobile</h1>
                <p role="status">
                    Integrasi layanan perusahaan belum diaktifkan.
                </p>
                <p class="muted">
                    Build live dikunci sampai kontrak, autentikasi, ACL dan
                    backend lulus penerimaan. Tidak ada login simulasi atau
                    fallback data demo.
                </p>
            </main>
        );
    const [actor, setActor] = useState("sales");
    const [attempt, setAttempt] = useState(0);
    const [boot, setBoot] = useState<{
        identity: Identity;
        snapshot: Snapshot;
        provider: FieldProvider;
    }>();
    const [error, setError] = useState("");
    useEffect(() => {
        let active = true;
        setBoot(undefined);
        setError("");
        void (async () => {
            try {
                const provider = await createProvider(actor);
                const identity = await provider.bootstrap();
                const snapshot = await provider.snapshot();
                if (active) setBoot({ provider, identity, snapshot });
            } catch (e) {
                if (active)
                    setError(
                        e instanceof Error
                            ? e.message
                            : "Layanan belum tersedia.",
                    );
            }
        })();
        return () => {
            active = false;
        };
    }, [actor, attempt]);
    if (!boot)
        return (
            <main class="boot">
                <Brand large />
                <h1 class="sr-only">Odoo FMCG Mobile</h1>
                <p role="status">{error || "Menyiapkan ruang kerja…"}</p>
                {error && (
                    <>
                        <p class="muted">
                            {__DEMO__
                                ? "Simulator gagal dimuat."
                                : "Mode live. Tidak ada fallback ke data simulasi. Backend/sesi resmi diperlukan."}
                        </p>
                        <button onClick={() => setAttempt((x) => x + 1)}>
                            Coba lagi
                        </button>
                    </>
                )}
            </main>
        );
    return (
        <Workspace
            key={boot.identity.id}
            {...boot}
            actor={actor}
            changeActor={setActor}
        />
    );
}
function Workspace({
    identity,
    snapshot: initialSnapshot,
    provider,
    actor,
    changeActor,
}: {
    identity: Identity;
    snapshot: Snapshot;
    provider: FieldProvider;
    actor: string;
    changeActor: (actor: string) => void;
}) {
    const [page, setPage] = useState<Page>("home");
    const [dialog, setDialog] = useState<Dialog>();
    const [queue, setQueue] = useState<QueueItem[]>([]);
    const [online, setOnline] = useState(navigator.onLine);
    const [toast, setToast] = useState("");
    const [syncing, setSyncing] = useState(false);
    const [scenario, setScenario] = useState<Scenario>("normal");
    const [filter, setFilter] = useState("");
    const owner = ownerKey(identity);
    const [morning, setMorning] = useState<MorningRecord>();
    const snapshot = morningReady(morning, owner)
        ? morning!.snapshot!
        : initialSnapshot;
    function openOrder(outlet: string) {
        if (!morningReady(morning, owner)) {
            setToast(
                "Absensi simulasi dan sync pagi wajib selesai sebelum kunjungan/order.",
            );
            setPage("home");
            window.scrollTo({ top: 0 });
            return;
        }
        setDialog({ type: "order", outlet });
    }
    const engine = useMemo(
        () =>
            new Outbox(store, owner, provider, () => {
                void refresh();
            }),
        [owner, provider],
    );
    async function refresh() {
        try {
            setQueue(await store.list(owner));
        } catch {
            setToast(
                "Penyimpanan lokal tidak tersedia. Tidak ada klaim data tersimpan.",
            );
        }
    }
    useEffect(() => {
        void refresh();
        const a = () => setOnline(true),
            b = () => setOnline(false);
        window.addEventListener("online", a);
        window.addEventListener("offline", b);
        return () => {
            window.removeEventListener("online", a);
            window.removeEventListener("offline", b);
        };
    }, []);
    useEffect(() => {
        provider.scenario = scenario;
    }, [scenario, provider]);
    useEffect(() => {
        if (!online) return;
        void engine.retry();
        const id = window.setInterval(() => {
            if (document.visibilityState === "visible" && navigator.onLine)
                void engine.flush();
        }, 15000);
        const resume = () => {
            if (document.visibilityState === "visible" && navigator.onLine)
                void engine.flush();
        };
        document.addEventListener("visibilitychange", resume);
        return () => {
            clearInterval(id);
            document.removeEventListener("visibilitychange", resume);
        };
    }, [online, engine]);
    useEffect(() => {
        if (!toast) return;
        const id = setTimeout(() => setToast(""), 6000);
        return () => clearTimeout(id);
    }, [toast]);
    const pending = queue.filter((x) =>
        ["queued", "sending", "auth_required"].includes(x.state),
    ).length;
    const review = queue.filter((x) => x.state === "needs_approval").length;
    const go = (id: Page) => {
        if (canOpen(identity.roles, id)) {
            setPage(id);
            setFilter("");
            haptic();
            window.scrollTo({ top: 0 });
        }
    };
    async function submit(
        type: Command["type"],
        payload: Record<string, unknown>,
        label: string,
    ) {
        if (type.startsWith("sales.")) {
            if (!morningReady(morning, owner))
                throw new Error(
                    "Sesi pagi belum terbuka atau sudah berganti hari. Sync pagi kembali.",
                );
            payload = {
                ...payload,
                work_session_id: morning!.sessionId,
                morning_business_date: morning!.businessDate,
                snapshot_version: morning!.snapshot!.version,
            };
        }
        const item = await engine.enqueue(type, payload, label);
        setDialog(undefined);
        setToast(
            "Tersimpan di perangkat. " +
                (online
                    ? "Mengirim ke simulator…"
                    : "Akan dikirim saat koneksi pulih."),
        );
        haptic();
        if (navigator.onLine) void engine.flush();
        return item;
    }
    async function sync() {
        setSyncing(true);
        try {
            await engine.retry();
            await refresh();
        } finally {
            setSyncing(false);
        }
    }
    const nav = pages.filter((p) => canOpen(identity.roles, p.id));
    return (
        <div class="app-shell">
            <div class="simulation">
                <span class="sim-dot" />
                {provider.mode === "demo"
                    ? "SIMULASI • Data fiktif, belum terhubung Odoo"
                    : "LIVE • Menggunakan layanan perusahaan"}
            </div>
            <header class="topbar">
                <a
                    class="wordmark"
                    href="#"
                    onClick={(e) => {
                        e.preventDefault();
                        go("home");
                    }}
                >
                    <Brand />
                </a>
                <div class="top-actions">
                    <button
                        class="icon-button"
                        aria-label="Lihat antrean sinkronisasi"
                        onClick={() => go("more")}
                    >
                        <Icon name="sync" />
                        {pending > 0 && <b class="counter">{pending}</b>}
                    </button>
                    <button
                        class="avatar"
                        aria-label="Akun dan pengaturan"
                        onClick={() => go("more")}
                    >
                        {identity.name[0]}
                    </button>
                </div>
            </header>
            <main id="main-content" class="content">
                {identity.roles.includes("sales") &&
                    (page === "home" || page === "sales") && (
                        <MorningSession
                            identity={identity}
                            provider={provider}
                            store={store}
                            onChange={setMorning}
                        />
                    )}
                {page === "home" && (
                    <>
                        <div class="greeting">
                            <div>
                                <p class="eyebrow">{dateLabel()} · WITA</p>
                                <h1>
                                    Selamat bekerja,
                                    <br />
                                    <span>{identity.name}.</span>
                                </h1>
                                <p class="muted">
                                    Satu hari, langkah yang berarti.
                                </p>
                            </div>
                            <span class="weather">
                                <Icon name="signal" size={20} />
                                {online ? "Online" : "Offline"}
                            </span>
                        </div>
                        <section class="day-card" aria-label="Ringkasan hari">
                            <div class="day-top">
                                <Pill tone="light">
                                    <span class="live-dot" />
                                    Ruang kerja simulasi
                                </Pill>
                                <Icon name="arrow" />
                            </div>
                            <h2>
                                Siap untuk
                                <br />
                                perjalanan hari ini?
                            </h2>
                            <p>
                                Semua tugas dalam satu genggaman.
                                <br />
                                Draft tetap tersedia saat jaringan putus.*
                            </p>
                            <div class="day-bottom">
                                <span>
                                    <Icon name="pin" size={18} /> Manado &
                                    sekitarnya
                                </span>
                                <strong>
                                    MDU<span>FIELD TEAM</span>
                                </strong>
                            </div>
                            <div class="hero-orbit" aria-hidden="true" />
                        </section>
                        <div class="summary-grid">
                            <button
                                class="metric"
                                onClick={() =>
                                    go(
                                        identity.roles.includes("sales")
                                            ? "sales"
                                            : "delivery",
                                    )
                                }
                            >
                                <span class="metric-icon blue">
                                    <Icon
                                        name={
                                            identity.roles.includes("sales")
                                                ? "store"
                                                : "truck"
                                        }
                                    />
                                </span>
                                <strong>
                                    {identity.roles.includes("sales")
                                        ? snapshot.outlets.length
                                        : snapshot.deliveries.length}
                                    <small>tugas hari ini</small>
                                </strong>
                                <Icon name="caret" size={18} />
                            </button>
                            <button class="metric" onClick={() => go("more")}>
                                <span class="metric-icon amber">
                                    <Icon name="clock" />
                                </span>
                                <strong>
                                    {pending + review}
                                    <small>pending / review</small>
                                </strong>
                                <Icon name="caret" size={18} />
                            </button>
                        </div>
                        <Heading
                            title="Akses cepat"
                            note="Kebutuhan kerja, tanpa berputar."
                        />
                        <div class="quick-grid">
                            {identity.roles.includes("sales") && (
                                <button onClick={() => go("sales")}>
                                    <span class="quick-icon">
                                        <Icon name="bag" size={28} />
                                    </span>
                                    <strong>Buat order</strong>
                                    <small>Untuk outlet PJP</small>
                                </button>
                            )}
                            {identity.roles.includes("delivery") && (
                                <button onClick={() => go("delivery")}>
                                    <span class="quick-icon">
                                        <Icon name="truck" size={28} />
                                    </span>
                                    <strong>Pengiriman</strong>
                                    <small>Manifest & bukti</small>
                                </button>
                            )}
                            <button
                                onClick={() =>
                                    setDialog({ type: "attendance" })
                                }
                            >
                                <span class="quick-icon">
                                    <Icon name="user" size={28} />
                                </span>
                                <strong>Absensi</strong>
                                <small>Foto & lokasi</small>
                            </button>
                            <button
                                onClick={() => setDialog({ type: "expense" })}
                            >
                                <span class="quick-icon">
                                    <Icon name="wallet" size={28} />
                                </span>
                                <strong>Uang lapangan</strong>
                                <small>Biaya & petty cash</small>
                            </button>
                        </div>
                        <Heading
                            title={
                                identity.roles.includes("sales")
                                    ? "Kunjungan berikutnya"
                                    : "Tugas berikutnya"
                            }
                            note="Mulai dari rencana, lanjutkan dengan aksi."
                            action={
                                <button
                                    class="text-button"
                                    onClick={() =>
                                        go(
                                            identity.roles.includes("sales")
                                                ? "sales"
                                                : "delivery",
                                        )
                                    }
                                >
                                    Lihat semua <Icon name="arrow" size={16} />
                                </button>
                            }
                        />
                        {identity.roles.includes("sales") ? (
                            <OutletCard
                                outlet={snapshot.outlets[0]}
                                open={() => openOrder(snapshot.outlets[0].id)}
                            />
                        ) : (
                            <DeliveryCard
                                task={snapshot.deliveries[0]}
                                open={() =>
                                    setDialog({
                                        type: "proof",
                                        delivery: snapshot.deliveries[0].id,
                                    })
                                }
                            />
                        )}
                        <div class="tip">
                            <span class="quick-icon">
                                <Icon name="bell" />
                            </span>
                            <div>
                                <strong>Sebelum memulai kunjungan</strong>
                                <p>
                                    Selesaikan dua langkah sesi pagi di atas.
                                    Paket yang tersimpan berlaku sampai
                                    pergantian hari WITA; otorisasi resmi tetap
                                    menunggu backend.
                                </p>
                            </div>
                        </div>
                        <p class="footnote">
                            * Penyimpanan browser dapat terhapus saat
                            clear-data/uninstall. Sinkronkan sebelum mengakhiri
                            pekerjaan.
                        </p>
                    </>
                )}
                {page === "sales" && (
                    <>
                        <Heading
                            title="Sales & kunjungan"
                            note={`PJP contoh · snapshot ${time(snapshot.updatedAt)} WITA*`}
                        />
                        <div class="notice">
                            Harga & stok di bawah adalah estimasi simulasi.
                            Extra call memerlukan approval supervisor.
                        </div>
                        <label class="search">
                            <Icon name="store" size={20} />
                            <input
                                placeholder="Cari outlet atau alamat…"
                                aria-label="Cari outlet"
                                value={filter}
                                onInput={(e) =>
                                    setFilter(e.currentTarget.value)
                                }
                            />
                        </label>
                        <div class="list-stack">
                            {snapshot.outlets
                                .filter((o) =>
                                    `${o.name} ${o.address}`
                                        .toLowerCase()
                                        .includes(filter.toLowerCase()),
                                )
                                .map((o) => (
                                    <OutletCard
                                        key={o.id}
                                        outlet={o}
                                        open={() => openOrder(o.id)}
                                    />
                                ))}
                        </div>
                        <button
                            class="secondary full"
                            onClick={() => setDialog({ type: "extra" })}
                        >
                            <Icon name="pin" size={20} />
                            Ajukan extra call
                        </button>
                        <p class="footnote">
                            * Waktu tampilan mengikuti perangkat; penetapan
                            sesi/harga resmi menunggu backend.
                        </p>
                    </>
                )}
                {page === "delivery" && (
                    <>
                        <Heading
                            title="Delivery"
                            note="Manifest contoh · Maumbi — Manado"
                        />
                        <section class="trip-card">
                            <Icon name="truck" size={36} />
                            <div>
                                <strong>TRIP-DEMO-01</strong>
                                <p>2 pengiriman · 20 karton · DB • DEMO</p>
                            </div>
                        </section>
                        <div class="list-stack">
                            {snapshot.deliveries.map((d) => (
                                <DeliveryCard
                                    key={d.id}
                                    task={d}
                                    open={() =>
                                        setDialog({
                                            type: "proof",
                                            delivery: d.id,
                                        })
                                    }
                                />
                            ))}
                        </div>
                        <button
                            class="secondary full"
                            onClick={() =>
                                setDialog({
                                    type: "expense",
                                    trip: "TRIP-DEMO-01",
                                })
                            }
                        >
                            <Icon name="gas" />
                            Biaya trip / pengajuan BBM
                        </button>
                        <p class="notice">
                            Bukti POD tidak otomatis menjadikan picking selesai.
                            Posting stok dan settlement tetap di Odoo.
                        </p>
                    </>
                )}
                {page === "hris" && (
                    <>
                        <Heading
                            title="Personal HRIS"
                            note="Ruang personal, untuk kebutuhan Anda."
                        />
                        <section class="profile-card">
                            <span class="avatar large">{identity.name[0]}</span>
                            <div>
                                <h2>{identity.name}</h2>
                                <p>{identity.title}</p>
                                <Pill>Employee simulasi</Pill>
                            </div>
                        </section>
                        <div class="hris-actions">
                            <button
                                class="card-row"
                                onClick={() =>
                                    setDialog({ type: "attendance" })
                                }
                            >
                                <span class="metric-icon blue">
                                    <Icon name="camera" />
                                </span>
                                <div>
                                    <strong>Absensi hari ini</strong>
                                    <small>Foto, lokasi & hasil validasi</small>
                                </div>
                                <Icon name="caret" />
                            </button>
                            <button
                                class="card-row"
                                onClick={() => setDialog({ type: "leave" })}
                            >
                                <span class="metric-icon purple">
                                    <Icon name="clock" />
                                </span>
                                <div>
                                    <strong>Pengajuan cuti</strong>
                                    <small>Draft & review atasan</small>
                                </div>
                                <Icon name="caret" />
                            </button>
                            <button
                                class="card-row"
                                onClick={() => setDialog({ type: "expense" })}
                            >
                                <span class="metric-icon amber">
                                    <Icon name="wallet" />
                                </span>
                                <div>
                                    <strong>Petty cash luar kota</strong>
                                    <small>Makan, BBM & penginapan</small>
                                </div>
                                <Icon name="caret" />
                            </button>
                        </div>
                        <section class="paper-card">
                            <Icon name="receipt" size={30} />
                            <h3>Slip gaji & dokumen pribadi</h3>
                            <p class="muted">
                                Belum terintegrasi. Dokumen personal hanya
                                dibuka online setelah dipublikasikan backend.
                            </p>
                            <Pill tone="neutral">Menunggu backend</Pill>
                        </section>
                    </>
                )}
                {page === "more" && (
                    <>
                        <Heading
                            title="Akun & sinkronisasi"
                            note={identity.title}
                        />
                        <section class="sync-card">
                            <div>
                                <span class="metric-icon blue">
                                    <Icon name="sync" />
                                </span>
                                <h3>{pending} aktivitas menunggu</h3>
                                <p class="muted">
                                    {online
                                        ? "Koneksi tersedia"
                                        : "Offline • antrean disimpan di perangkat"}
                                </p>
                            </div>
                            <button
                                disabled={!online || syncing}
                                onClick={() => void sync()}
                            >
                                {syncing ? "Mengirim…" : "Sinkronkan"}
                            </button>
                        </section>
                        {__DEMO__ && (
                            <section class="paper-card demo-controls">
                                <h3>Laboratorium simulasi</h3>
                                <p class="muted">
                                    Kontrol ini hanya ada pada build demo.
                                    Mengganti persona tidak memindahkan antrean.
                                </p>
                                <label>
                                    Persona demo
                                    <select
                                        aria-label="Persona demo"
                                        value={actor}
                                        onChange={(e) =>
                                            changeActor(e.currentTarget.value)
                                        }
                                    >
                                        <option value="sales">
                                            Salesman — Andre
                                        </option>
                                        <option value="delivery">
                                            Driver — Novry
                                        </option>
                                        <option value="canvass">
                                            Canvasser — Steven
                                        </option>
                                    </select>
                                </label>
                                <label>
                                    Respons simulator
                                    <select
                                        aria-label="Respons simulator"
                                        value={scenario}
                                        onChange={(e) =>
                                            setScenario(
                                                e.currentTarget
                                                    .value as Scenario,
                                            )
                                        }
                                    >
                                        <option value="normal">Normal</option>
                                        <option value="approval">
                                            Menunggu approval
                                        </option>
                                        <option value="rejected">
                                            Ditolak
                                        </option>
                                        <option value="timeout">
                                            Jaringan gagal / 503
                                        </option>
                                        <option value="expired">
                                            Sesi habis / 401
                                        </option>
                                    </select>
                                </label>
                            </section>
                        )}
                        <Heading
                            title="Aktivitas perangkat ini"
                            note="Terkirim berbeda dengan disetujui atau diposting."
                        />
                        {!queue.length ? (
                            <Empty text="Belum ada aktivitas. Mulai dari order atau pengajuan." />
                        ) : (
                            <div class="activity-list">
                                {[...queue].reverse().map((q) => (
                                    <article class="activity" key={q.key}>
                                        <span
                                            class={`activity-dot ${q.state}`}
                                        />
                                        <div>
                                            <strong>{q.label}</strong>
                                            <small>
                                                {time(q.command.occurred_at)} ·{" "}
                                                {q.command.client_uuid.slice(
                                                    0,
                                                    8,
                                                )}
                                            </small>
                                            <p>
                                                {q.receipt?.message ??
                                                    q.error ??
                                                    "Tersimpan lokal, belum diterima server."}
                                            </p>
                                            <Pill
                                                tone={
                                                    q.state === "accepted"
                                                        ? "green"
                                                        : q.state === "rejected"
                                                          ? "red"
                                                          : "amber"
                                                }
                                            >
                                                {queueLabels[q.state]}
                                            </Pill>
                                        </div>
                                    </article>
                                ))}
                            </div>
                        )}
                        <p class="footnote">
                            Binding perangkat, approval resmi, notifikasi
                            backend dan pengiriman evidence menunggu integrasi
                            API. Tidak ada token atau dokumen gaji di cache
                            demo.
                        </p>
                    </>
                )}
            </main>
            <nav class="bottom-nav" aria-label="Navigasi utama">
                {nav.map((p) => (
                    <button
                        key={p.id}
                        class={page === p.id ? "active" : ""}
                        aria-current={page === p.id ? "page" : undefined}
                        onClick={() => go(p.id)}
                    >
                        <span class="nav-icon">
                            <Icon name={p.icon} size={24} />
                            {p.id === "more" && pending > 0 && (
                                <span class="nav-dot" />
                            )}
                        </span>
                        <span>{p.name}</span>
                    </button>
                ))}
            </nav>
            <div
                class={`connection ${online ? "" : "offline"}`}
                aria-live="polite"
            >
                {online ? "" : "Offline · aktivitas disimpan di perangkat"}
            </div>
            {toast && (
                <div class="toast" role="status">
                    <Icon name="check" size={22} />
                    {toast}
                </div>
            )}
            {dialog && (
                <FormDialog
                    key={JSON.stringify(dialog)}
                    dialog={dialog}
                    identity={identity}
                    snapshot={snapshot}
                    owner={owner}
                    submit={submit}
                    close={() => setDialog(undefined)}
                />
            )}
        </div>
    );
}
function OutletCard({
    outlet,
    open,
}: {
    outlet: Snapshot["outlets"][number];
    open: () => void;
}) {
    return (
        <button class="outlet-card" onClick={open}>
            <span class="outlet-icon">
                <Icon name="store" size={28} />
            </span>
            <div>
                <div class="card-title">
                    <strong>{outlet.name}</strong>
                    <Pill>{outlet.channel}</Pill>
                </div>
                <p>{outlet.address}</p>
                <small>
                    <Icon name="clock" size={14} />
                    {outlet.time}
                    <span>·</span>
                    <Icon name="pin" size={14} />
                    {outlet.distance}
                </small>
            </div>
            <Icon name="caret" size={18} />
        </button>
    );
}
function DeliveryCard({
    task,
    open,
}: {
    task: Snapshot["deliveries"][number];
    open: () => void;
}) {
    return (
        <button class="outlet-card" onClick={open}>
            <span class="outlet-icon">
                <Icon name="truck" size={28} />
            </span>
            <div>
                <strong>{task.outlet}</strong>
                <p>
                    {task.id} · {task.address}
                </p>
                <small>
                    {task.items} SKU · {task.cartons} karton
                </small>
            </div>
            <Icon name="caret" size={18} />
        </button>
    );
}
function FormDialog({
    dialog,
    identity,
    snapshot,
    owner,
    submit,
    close,
}: {
    dialog: Dialog;
    identity: Identity;
    snapshot: Snapshot;
    owner: string;
    submit: (
        type: Command["type"],
        payload: Record<string, unknown>,
        label: string,
    ) => Promise<QueueItem>;
    close: () => void;
}) {
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const [qty, setQty] = useState<Record<string, number>>({});
    const [principal, setPrincipal] = useState("mayora");
    const [evidence, setEvidence] = useState<EvidenceRef>();
    const [restored, setRestored] = useState(false);
    const [category, setCategory] = useState("fuel_planned");
    const busyRef = useRef(false);
    busyRef.current = busy;
    const key = dialog.type === "order" ? `order:${dialog.outlet}` : "";
    useEffect(() => {
        if (!key) {
            setRestored(true);
            return;
        }
        let active = true;
        void store
            .draft(owner, key)
            .then((value) => {
                if (active && value && typeof value === "object") {
                    const v = value as {
                        quantities: Record<string, number>;
                        principal: string;
                    };
                    setQty(v.quantities ?? {});
                    setPrincipal(v.principal ?? "mayora");
                }
                if (active) setRestored(true);
            })
            .catch(() => {
                setError("Draft tidak dapat dibaca.");
            });
        return () => {
            active = false;
        };
    }, []);
    useEffect(() => {
        if (restored && key)
            void store
                .draft(owner, key, { quantities: qty, principal })
                .catch(() =>
                    setError("Draft gagal disimpan. Periksa penyimpanan."),
                );
    }, [qty, principal, restored]);
    useEffect(() => {
        const old = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        const previousFocus = document.activeElement as HTMLElement | null;
        const sheet = document.querySelector<HTMLElement>(".sheet");
        const behind = [
            ...document.querySelectorAll<HTMLElement>(
                ".content, .topbar, .bottom-nav",
            ),
        ];
        behind.forEach((el) => {
            el.inert = true;
        });
        sheet
            ?.querySelector<HTMLElement>("input, select, textarea, button")
            ?.focus();
        const keys = (e: KeyboardEvent) => {
            if (e.key === "Escape" && !busyRef.current) close();
            if (e.key !== "Tab" || !sheet) return;
            const items = [
                ...sheet.querySelectorAll<HTMLElement>(
                    "button:not([disabled]), input:not([disabled]), select, textarea",
                ),
            ].filter((el) => el.getClientRects().length);
            const first = items[0],
                last = items.at(-1);
            if (e.shiftKey && document.activeElement === first) {
                e.preventDefault();
                last?.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault();
                first?.focus();
            }
        };
        document.addEventListener("keydown", keys);
        return () => {
            document.body.style.overflow = old;
            behind.forEach((el) => {
                el.inert = false;
            });
            previousFocus?.focus();
            document.removeEventListener("keydown", keys);
        };
    }, []);
    const total = snapshot.products.reduce(
        (n, p) => n + p.price * (qty[p.id] || 0),
        0,
    );
    const title = {
        order: "Buat Sales Order",
        extra: "Ajukan extra call",
        proof: "Bukti pengiriman",
        expense: "Uang lapangan",
        attendance: "Absensi foto & lokasi",
        leave: "Pengajuan cuti",
    }[dialog.type];
    async function send(e: SubmitEvent) {
        e.preventDefault();
        if (busy) return;
        setError("");
        const f = new FormData(e.currentTarget as HTMLFormElement);
        setBusy(true);
        try {
            let type: Command["type"];
            let payload: Record<string, unknown>;
            let label: string;
            if (dialog.type === "order") {
                const lines = Object.entries(qty)
                    .filter(([, q]) => q > 0)
                    .map(([productId, quantity]) => ({ productId, quantity }));
                const invalid = validateOrder(lines, snapshot);
                if (invalid) throw new Error(invalid);
                type = "sales.order.submit";
                payload = {
                    outlet_id: dialog.outlet,
                    snapshot_version: snapshot.version,
                    lines: lines.map((l) => ({
                        product_id: l.productId,
                        qty: String(l.quantity),
                        uom: "carton",
                    })),
                    note: String(f.get("note") ?? ""),
                    observed_total: String(total),
                };
                label = `Order • ${snapshot.outlets.find((o) => o.id === dialog.outlet)?.name}`;
            } else if (dialog.type === "extra") {
                type = "sales.extra_call.request";
                payload = {
                    outlet_name: f.get("outlet"),
                    reason: f.get("reason"),
                };
                label = `Extra call • ${f.get("outlet")}`;
            } else if (dialog.type === "expense") {
                const amount = Number(f.get("amount"));
                if (!Number.isFinite(amount) || amount < 1)
                    throw new Error("Nominal harus lebih dari nol.");
                type = "field_expense.request";
                payload = validateExpense(
                    {
                        category,
                        amount: String(amount),
                        trip_id: String(f.get("trip") ?? ""),
                        delivery_id:
                            f.get("scope") === "delivery"
                                ? String(f.get("delivery") ?? "").trim() || null
                                : null,
                        expense_scope: f.get("scope"),
                        scheduled_date: f.get("date"),
                        odometer:
                            f.get("odometer") === null ||
                            f.get("odometer") === ""
                                ? null
                                : Number(f.get("odometer")),
                        reason: f.get("reason"),
                        evidence: evidence ?? null,
                    },
                    identity.businessDate,
                );
                label = `Petty cash • ${money(amount)}`;
            } else if (dialog.type === "leave") {
                const from = String(f.get("from")),
                    to = String(f.get("to"));
                if (to < from)
                    throw new Error(
                        "Tanggal selesai tidak boleh sebelum mulai.",
                    );
                type = "hris.leave.request";
                payload = {
                    date_from: from,
                    date_to: to,
                    reason: f.get("reason"),
                };
                label = "Pengajuan cuti";
            } else {
                if (!evidence)
                    throw new Error("Simpan foto dan lokasi dahulu.");
                type =
                    dialog.type === "attendance"
                        ? "hris.attendance.capture"
                        : "delivery.proof.submit";
                payload = {
                    event: f.get("event"),
                    delivery_id:
                        dialog.type === "proof" ? dialog.delivery : null,
                    result: f.get("result"),
                    evidence,
                    map_status: "pending",
                };
                label =
                    dialog.type === "attendance"
                        ? "Bukti absensi • map pending"
                        : `POD • ${dialog.delivery}`;
            }
            // Evidence remains local: receipts must not claim the backend has verified it.
            if (
                evidence &&
                ["hris.attendance.capture", "delivery.proof.submit"].includes(
                    type,
                )
            )
                throw new Error(
                    "Bukti tersimpan lokal. Pengiriman resmi menunggu API evidence & snapshot peta.",
                );
            await submit(type, payload, label);
            if (key) await store.removeDraft(owner, key);
        } catch (x) {
            setError(
                x instanceof Error
                    ? x.message
                    : "Penyimpanan gagal. Form tetap tersedia.",
            );
        } finally {
            setBusy(false);
        }
    }
    return (
        <div class="modal-backdrop">
            <section
                class="sheet"
                role="dialog"
                aria-modal="true"
                aria-labelledby="dialog-title"
            >
                <header class="sheet-head">
                    <div>
                        <p class="eyebrow">{identity.name} · SIMULASI</p>
                        <h2 id="dialog-title">{title}</h2>
                    </div>
                    <button
                        class="icon-button"
                        type="button"
                        onClick={close}
                        aria-label="Tutup form"
                        disabled={busy}
                    >
                        <Icon name="close" />
                    </button>
                </header>
                <form onSubmit={(e) => void send(e)}>
                    <div class="sheet-body">
                        {dialog.type === "order" && (
                            <>
                                <p class="muted">
                                    {
                                        snapshot.outlets.find(
                                            (o) => o.id === dialog.outlet,
                                        )?.name
                                    }{" "}
                                    · satu principal per SO
                                </p>
                                <label>
                                    Principal
                                    <select
                                        value={principal}
                                        onChange={(e) => {
                                            setPrincipal(e.currentTarget.value);
                                            setQty({});
                                        }}
                                    >
                                        <option value="mayora">Mayora</option>
                                        <option value="santos">Santos</option>
                                    </select>
                                </label>
                                <div class="product-list">
                                    {snapshot.products
                                        .filter(
                                            (p) => p.principal === principal,
                                        )
                                        .map((p) => (
                                            <article class="product" key={p.id}>
                                                <span class="product-symbol">
                                                    <Icon
                                                        name="bag"
                                                        size={26}
                                                    />
                                                </span>
                                                <div>
                                                    <small class="eyebrow">
                                                        {p.brand}
                                                    </small>
                                                    <strong>{p.name}</strong>
                                                    <small>
                                                        {p.unit} · stok contoh{" "}
                                                        {p.stock}
                                                    </small>
                                                    <b>{money(p.price)}</b>
                                                </div>
                                                <input
                                                    aria-label={`Kuantitas ${p.name}`}
                                                    type="number"
                                                    min="0"
                                                    max="999"
                                                    step="1"
                                                    inputMode="numeric"
                                                    value={qty[p.id] || 0}
                                                    onInput={(e) =>
                                                        setQty((v) => ({
                                                            ...v,
                                                            [p.id]: Number(
                                                                e.currentTarget
                                                                    .value,
                                                            ),
                                                        }))
                                                    }
                                                />
                                            </article>
                                        ))}
                                </div>
                                <label>
                                    Catatan order
                                    <textarea
                                        name="note"
                                        placeholder="Permintaan outlet (opsional)"
                                    />
                                </label>
                                <div class="estimate">
                                    <span>Estimasi total</span>
                                    <strong>{money(total)}</strong>
                                </div>
                                <p class="footnote">
                                    Harga akhir, kredit, extra discount dan
                                    approval below-HPP diputuskan backend. Angka
                                    ini belum menjadi penawaran resmi.
                                </p>
                            </>
                        )}
                        {dialog.type === "extra" && (
                            <>
                                <p class="notice">
                                    Kunjungan di luar PJP baru sah setelah
                                    supervisor menyetujui.
                                </p>
                                <label>
                                    Nama outlet
                                    <input
                                        name="outlet"
                                        required
                                        maxLength={100}
                                    />
                                </label>
                                <label>
                                    Alasan extra call
                                    <textarea
                                        name="reason"
                                        required
                                        maxLength={500}
                                    />
                                </label>
                            </>
                        )}
                        {dialog.type === "expense" && (
                            <>
                                <label>
                                    Kategori
                                    <select
                                        aria-label="Kategori"
                                        value={category}
                                        onChange={(e) =>
                                            setCategory(e.currentTarget.value)
                                        }
                                    >
                                        <option value="fuel_planned">
                                            BBM terencana (H-1)
                                        </option>
                                        <option value="fuel_emergency">
                                            BBM insidentil
                                        </option>
                                        <option value="meal">
                                            Uang makan luar kota
                                        </option>
                                        <option value="lodging">
                                            Penginapan luar kota
                                        </option>
                                        <option value="repair">
                                            Perbaikan darurat / derek
                                        </option>
                                    </select>
                                </label>
                                <label>
                                    Lingkup biaya
                                    <select name="scope">
                                        <option value="trip">
                                            Biaya perjalanan / trip
                                        </option>
                                        <option value="delivery">
                                            Biaya per pengiriman / DO
                                        </option>
                                    </select>
                                </label>
                                <label>
                                    Referensi trip / perjalanan
                                    <input
                                        name="trip"
                                        required
                                        maxLength={100}
                                        defaultValue={dialog.trip ?? ""}
                                    />
                                </label>
                                <label>
                                    Referensi DO (untuk biaya per pengiriman)
                                    <input name="delivery" maxLength={100} />
                                </label>
                                <p class="notice">
                                    {category === "fuel_emergency"
                                        ? "BBM insidentil: Supervisor + Branch Manager, berapa pun nominalnya."
                                        : "Wajib approval supervisor. Di atas limit kewenangan diteruskan ke Branch Manager."}
                                </p>
                                <label>
                                    Tanggal perjalanan
                                    <input name="date" type="date" required />
                                </label>
                                <label>
                                    Nominal pengajuan (Rp)
                                    <input
                                        name="amount"
                                        type="number"
                                        min="1"
                                        max="100000000"
                                        inputMode="numeric"
                                        required
                                    />
                                </label>
                                {category.startsWith("fuel") && (
                                    <>
                                        <label>
                                            KM / odometer awal
                                            <input
                                                name="odometer"
                                                type="number"
                                                min="0"
                                                required
                                            />
                                        </label>
                                        <p class="footnote">
                                            Tanggal bisnis simulasi:{" "}
                                            {identity.businessDate}. Pengajuan
                                            BBM H-1 memerlukan foto odometer;
                                            realisasi memerlukan struk dan foto
                                            odometer setelah isi. Form ini baru
                                            draft permohonan simulasi.
                                        </p>
                                    </>
                                )}
                                <label>
                                    Tujuan / alasan
                                    <textarea
                                        name="reason"
                                        required
                                        maxLength={500}
                                    />
                                </label>
                                <EvidenceCapture
                                    store={store}
                                    owner={owner}
                                    onChange={setEvidence}
                                />
                            </>
                        )}
                        {dialog.type === "attendance" && (
                            <>
                                <label>
                                    Aktivitas
                                    <select name="event">
                                        <option value="check_in">
                                            Absen masuk
                                        </option>
                                        <option value="check_out">
                                            Absen keluar
                                        </option>
                                    </select>
                                </label>
                                <p class="notice">
                                    Foto dan lokasi disimpan lokal. Validasi
                                    employee, geofence kantor/gudang, perangkat
                                    dan sesi resmi menunggu server.
                                </p>
                                <EvidenceCapture
                                    store={store}
                                    owner={owner}
                                    onChange={setEvidence}
                                />
                            </>
                        )}
                        {dialog.type === "proof" && (
                            <>
                                <p class="muted">{dialog.delivery}</p>
                                <label>
                                    Hasil serah terima
                                    <select name="result">
                                        <option value="accepted">
                                            Diterima lengkap
                                        </option>
                                        <option value="partial">
                                            Diterima sebagian / retur
                                        </option>
                                    </select>
                                </label>
                                <p class="notice">
                                    Realisasi qty/lot dan posting stok
                                    memerlukan API domain. Ini capture bukti
                                    lokal, bukan validasi DO.
                                </p>
                                <EvidenceCapture
                                    store={store}
                                    owner={owner}
                                    onChange={setEvidence}
                                />
                            </>
                        )}
                        {dialog.type === "leave" && (
                            <>
                                <label>
                                    Tanggal mulai
                                    <input name="from" type="date" required />
                                </label>
                                <label>
                                    Tanggal selesai
                                    <input name="to" type="date" required />
                                </label>
                                <label>
                                    Alasan
                                    <textarea
                                        name="reason"
                                        required
                                        maxLength={500}
                                    />
                                </label>
                                <p class="footnote">
                                    Saldo cuti dan keputusan atasan divalidasi
                                    server. Tidak ada saldo resmi dalam
                                    simulator.
                                </p>
                            </>
                        )}
                        {error && (
                            <div class="error-box" role="alert">
                                <Icon name="warning" size={20} />
                                {error}
                            </div>
                        )}
                    </div>
                    <footer class="sheet-footer">
                        <button
                            type="button"
                            class="secondary"
                            onClick={close}
                            disabled={busy}
                        >
                            Kembali
                        </button>
                        <button type="submit" disabled={busy || !restored}>
                            {busy
                                ? "Menyimpan…"
                                : ["attendance", "proof"].includes(dialog.type)
                                  ? "Periksa kesiapan bukti"
                                  : "Simpan ke antrean demo"}
                        </button>
                    </footer>
                </form>
            </section>
        </div>
    );
}
