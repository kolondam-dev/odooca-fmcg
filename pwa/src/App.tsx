import { TripClosing } from "./components/TripClosing";
import { OrderCorrections } from "./components/OrderCorrections";
import { DeliveryApproval } from "./components/DeliveryApproval";
import { DiscountApproval } from "./components/DiscountApproval";
import { orderQuote, type OrderUom } from "./domain/order-pricing";
import { OrderCatalog, OrderSummary } from "./components/OrderSheet";
import { DisplayPhoto } from "./components/DisplayPhoto";
import type { ComponentChildren } from "preact";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { HttpProvider } from "./data/provider";
import { AttendanceCapture } from "./components/AttendanceCapture";
import { Login } from "./components/Login";
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
import { SyncDiagnostics } from "./components/SyncDiagnostics";
import { VisitPanel } from "./components/VisitPanel";
import { SalesVisits, captureVisitLocation } from "./domain/visits";
import { CollectionWorkspace } from "./components/CollectionWorkspace";
import { DeliveryWorkspace } from "./components/DeliveryWorkspace";
import { ExpenseWorkspace } from "./components/ExpenseWorkspace";
import { Brand } from "./components/Brand";
import { MorningSession } from "./components/MorningSession";
import {
    morningReady,
    MorningSimulation,
    type MorningRecord,
} from "./domain/morning";
import { Outbox } from "./domain/outbox";
import { haptic, money } from "./domain/format";
import { FieldStore, type QueueItem } from "./storage/store";
import { Icon, type IconName } from "./components/Icon";
import { EvidenceCapture, type EvidenceRef } from "./components/Evidence";

type Page = "home" | "sales" | "delivery" | "hris" | "more" | "expenses";
type Dialog =
    | { type: "order"; outlet: string }
    | { type: "extra" }
    | { type: "proof"; delivery: string }
    | { type: "expense"; trip?: string }
    | { type: "attendance"; event?: "check_in" | "check_out" }
    | { type: "leave" }
    | { type: "profile" };
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
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
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
    note?: string;
    action?: ComponentChildren;
}) {
    return (
        <div class="section-heading">
            <div>
                <h2>{title}</h2>
                {note && <p class="muted">{note}</p>}
            </div>
            {action}
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
    const [boot, setBoot] = useState<{
        identity: Identity;
        snapshot: Snapshot;
        provider: FieldProvider;
    }>();
    const [checking, setChecking] = useState(true);
    const [loginError, setLoginError] = useState("");
    const generation = useRef(0);
    async function connect() {
        const ticket = ++generation.current;
        const source = new HttpProvider({ readOnly: true });
        const identity = await source.bootstrap();
        const snapshot = await source.snapshot();
        const { MockProvider } = await import("./data/mock");
        // Authentication, identity and work data are real. Existing transaction
        // simulation stays local until the command API has its own acceptance.
        const provider = new MockProvider("sales", true, source);
        if (ticket === generation.current)
            setBoot({ identity, snapshot, provider });
    }
    useEffect(() => {
        let active = true;
        void connect()
            .catch((error) => {
                if (active && error?.status !== 401)
                    setLoginError(
                        "Ruang kerja belum tersedia. Periksa koneksi atau hubungi admin.",
                    );
            })
            .finally(() => {
                if (active) setChecking(false);
            });
        return () => {
            active = false;
            generation.current++;
        };
    }, []);
    useEffect(() => {
        if (!boot) return;
        let active = true;
        const validate = async () => {
            if (document.visibilityState === "hidden" || !navigator.onLine)
                return;
            try {
                const identity = await new HttpProvider({
                    readOnly: true,
                }).bootstrap();
                if (active && ownerKey(identity) !== ownerKey(boot.identity)) {
                    generation.current++;
                    setBoot(undefined);
                    setLoginError("Memuat sesi akun…");
                    await connect();
                } else if (
                    active &&
                    identity.businessDate !== boot.identity.businessDate
                ) {
                    setBoot({ ...boot, identity });
                }
            } catch (failure) {
                if (
                    active &&
                    failure instanceof Error &&
                    "status" in failure &&
                    [401, 403, 409].includes(Number(failure.status))
                ) {
                    generation.current++;
                    setBoot(undefined);
                    setLoginError("Sesi berakhir. Silakan masuk kembali.");
                }
            }
        };
        window.addEventListener("focus", validate);
        window.addEventListener("online", validate);
        document.addEventListener("visibilitychange", validate);
        return () => {
            active = false;
            window.removeEventListener("focus", validate);
            window.removeEventListener("online", validate);
            document.removeEventListener("visibilitychange", validate);
        };
    }, [boot]);
    if (checking)
        return (
            <main class="login-page">
                <Brand />
                <p role="status">Memeriksa sesi…</p>
            </main>
        );
    if (!boot)
        return (
            <Login
                message={loginError}
                onSuccess={async () => {
                    setLoginError("");
                    try {
                        await connect();
                    } catch (failure) {
                        const status =
                            failure &&
                            typeof failure === "object" &&
                            "status" in failure
                                ? Number(failure.status)
                                : 0;
                        throw new Error(
                            status === 403 || status === 422
                                ? "Akun belum memiliki akses atau penugasan yang sesuai. Hubungi admin atau line manager."
                                : "Ruang kerja belum dapat dibuka. Periksa koneksi dan coba kembali.",
                        );
                    }
                }}
            />
        );
    return <Workspace key={ownerKey(boot.identity)} {...boot} />;
}
function Workspace({
    identity,
    snapshot: initialSnapshot,
    provider,
}: {
    identity: Identity;
    snapshot: Snapshot;
    provider: FieldProvider;
}) {
    const [now, setNow] = useState(Date.now());
    useEffect(() => {
        const timer = setInterval(() => setNow(Date.now()), 1000);
        return () => clearInterval(timer);
    }, []);
    const [page, setPage] = useState<Page>("home");
    const [dialog, setDialog] = useState<Dialog>();
    const [queue, setQueue] = useState<QueueItem[]>([]);
    const [online, setOnline] = useState(navigator.onLine);
    const [toast, setToast] = useState("");
    const [syncing, setSyncing] = useState(false);
    const [scenario, setScenario] = useState<Scenario>("normal");
    const [filter, setFilter] = useState("");
    const owner = ownerKey(identity);
    const [visitOutlet, setVisitOutlet] = useState<string>();
    const [morning, setMorning] = useState<MorningRecord>();
    const [morningRevision, setMorningRevision] = useState(0);
    const dailyReady =
        morningReady(morning, owner) &&
        (!identity.roles.includes("delivery") ||
            !!morning?.deliveryManifest?.length);
    const attended =
        !!morning &&
        morning.businessDate ===
            new Date(now).toLocaleDateString("en-CA", {
                timeZone: "Asia/Makassar",
            });
    const checkedOut = attended && !!morning?.clockOutAt;
    const snapshot = dailyReady ? morning!.snapshot! : initialSnapshot;
    const morningService = useMemo(
        () => new MorningSimulation(store, identity, provider),
        [identity, provider],
    );
    async function startSession(
        event: "check_in" | "check_out",
        evidence: EvidenceRef,
    ) {
        const record =
            event === "check_out"
                ? await morningService.clockOut(evidence)
                : await morningService.openDay(evidence);
        setMorning(record);
        setMorningRevision((value) => value + 1);
        setToast(
            event === "check_out"
                ? "Clock out tersimpan di perangkat."
                : "Check-in tersimpan di perangkat. Sesi kerja aktif.",
        );
        haptic();
    }
    function openOrder(outlet: string) {
        if (!dailyReady) {
            setToast("Buka sesi kerja terlebih dahulu sebelum order.");
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
    const visits = useMemo(
        () => new SalesVisits(store, identity, provider, engine),
        [identity, provider, engine],
    );
    function openVisit(outlet: string) {
        if (!dailyReady) {
            openOrder(outlet);
            return;
        }
        setVisitOutlet(outlet);
        go("sales");
    }
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
    // Accidental reload must not drop an open form or an unsent queue.
    useEffect(() => {
        const guard = (e: BeforeUnloadEvent) => {
            const unsent = queue.some((item) =>
                ["queued", "sending", "auth_required"].includes(item.state),
            );
            if (!dialog && !unsent) return;
            e.preventDefault();
            e.returnValue = "";
        };
        window.addEventListener("beforeunload", guard);
        return () => window.removeEventListener("beforeunload", guard);
    }, [dialog, queue]);
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
            if (!dailyReady)
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
        const item =
            type === "sales.order.submit"
                ? await visits.submitOrder(
                      payload,
                      await captureVisitLocation(),
                  )
                : await engine.enqueue(type, payload, label);
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
    const nav = pages.filter(
        (p) =>
            canOpen(identity.roles, p.id) &&
            !(p.id === "delivery" && identity.roles.includes("sales")),
    );
    return (
        <div class="app-shell">
            <div class="header-fixed">
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
                        <span
                            class={`connection-badge ${online ? "" : "is-offline"}`}
                            role="status"
                        >
                            <Icon name="signal" size={16} />
                            <span>{online ? "Online" : "Offline"}</span>
                        </span>
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
                            aria-label="Profil dan Sesi Akun"
                            title="Buka status akun & sesi"
                            onClick={() => setDialog({ type: "profile" })}
                        >
                            {identity.name[0]}
                        </button>
                    </div>
                </header>
            </div>
            <main id="main-content" class="content">
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
                            </div>
                        </div>
                        {identity.roles.some(
                            (r) => r === "sales" || r === "delivery",
                        ) && (
                            <MorningSession
                                key={`morning:${morningRevision}`}
                                identity={identity}
                                provider={provider}
                                store={store}
                                onChange={setMorning}
                            />
                        )}
                        <div class="quick-grid">
                            {identity.roles.includes("sales") && (
                                <button
                                    class="quick-sales"
                                    disabled={!attended || checkedOut}
                                    onClick={() => go("sales")}
                                >
                                    <span class="quick-icon">
                                        <Icon name="bag" size={26} />
                                    </span>
                                    <strong>Buat order</strong>
                                    <small>
                                        {snapshot.outlets.length} outlet
                                    </small>
                                </button>
                            )}
                            {identity.roles.includes("delivery") && (
                                <button
                                    class="quick-delivery"
                                    disabled={!attended || checkedOut}
                                    onClick={() => go("delivery")}
                                >
                                    <span class="quick-icon">
                                        <Icon name="truck" size={26} />
                                    </span>
                                    <strong>Pengiriman</strong>
                                    <small>
                                        {snapshot.deliveries.length} manifest
                                    </small>
                                </button>
                            )}
                            {attended ? (
                                <div class="quick-attendance-record">
                                    <div>
                                        <Icon name="user" size={22} />
                                        <strong>Clock in</strong>
                                        <time>
                                            {new Date(morning!.attendanceAt)
                                                .toLocaleTimeString("id-ID", {
                                                    timeZone: "Asia/Makassar",
                                                    hour12: false,
                                                })
                                                .replaceAll(".", ":")}{" "}
                                            WITA
                                        </time>
                                        <small>Tersimpan di perangkat</small>
                                    </div>
                                    <button
                                        disabled={checkedOut}
                                        onClick={() =>
                                            setDialog({
                                                type: "attendance",
                                                event: "check_out",
                                            })
                                        }
                                    >
                                        {checkedOut
                                            ? `Clock out ${new Date(morning!.clockOutAt!).toLocaleTimeString("id-ID", { timeZone: "Asia/Makassar" })}`
                                            : "Clock out"}
                                    </button>
                                </div>
                            ) : (
                                <button
                                    class="quick-attendance"
                                    onClick={() =>
                                        setDialog({ type: "attendance" })
                                    }
                                >
                                    <span class="quick-icon">
                                        <Icon name="user" size={26} />
                                    </span>
                                    <strong>Absensi</strong>
                                    <small>Check-in</small>
                                </button>
                            )}
                            <button
                                class="quick-expense"
                                disabled={!attended || checkedOut}
                                onClick={() => setDialog({ type: "expense" })}
                            >
                                <span class="quick-icon">
                                    <Icon name="wallet" size={26} />
                                </span>
                                <strong>Uang lapangan</strong>
                                <small>{pending + review} pending</small>
                            </button>
                        </div>
                        {identity.roles.includes("sales") && dailyReady ? (
                            <>
                                <Heading
                                    title="Kunjungan berikutnya"
                                    action={
                                        <button
                                            class="text-button"
                                            onClick={() => go("sales")}
                                        >
                                            Semua{" "}
                                            <Icon name="arrow" size={16} />
                                        </button>
                                    }
                                />
                                <OutletCard
                                    outlet={snapshot.outlets[0]}
                                    open={() =>
                                        openVisit(snapshot.outlets[0].id)
                                    }
                                />
                            </>
                        ) : (
                            !identity.roles.includes("sales") && (
                                <button
                                    class="outlet-card"
                                    onClick={() => go("delivery")}
                                >
                                    Buka manifest pengiriman
                                </button>
                            )
                        )}
                    </>
                )}
                {page === "sales" && !dailyReady && (
                    <p class="notice">
                        Buka sesi kerja sebelum membuka daftar outlet.
                    </p>
                )}
                {page === "sales" && dailyReady && (
                    <>
                        <Heading
                            title="Outlet"
                            action={
                                <button
                                    class="text-button"
                                    onClick={() => go("home")}
                                >
                                    Beranda
                                </button>
                            }
                        />
                        <div class="notice">
                            Harga & stok estimasi. Extra call memerlukan
                            approval supervisor.
                        </div>
                        {visitOutlet &&
                            dailyReady &&
                            snapshot.outlets.some(
                                (o) => o.id === visitOutlet,
                            ) && (
                                <VisitPanel
                                    key={`${owner}:${morning?.sessionId}:${visitOutlet}`}
                                    outlet={
                                        snapshot.outlets.find(
                                            (o) => o.id === visitOutlet,
                                        )!
                                    }
                                    service={visits}
                                    store={store}
                                    owner={owner}
                                    sessionId={morning!.sessionId!}
                                    queue={queue}
                                    changed={() => {
                                        void refresh();
                                        if (navigator.onLine)
                                            void engine.flush();
                                    }}
                                    order={() => openOrder(visitOutlet)}
                                    back={() => setVisitOutlet(undefined)}
                                />
                            )}
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
                                        status={
                                            queue.some(
                                                (q) =>
                                                    q.command.type ===
                                                        "sales.visit.check_out" &&
                                                    q.command.payload
                                                        .outlet_id === o.id &&
                                                    q.command.payload
                                                        .business_date ===
                                                        identity.businessDate,
                                            )
                                                ? "Session closed · hasil sync di Lainnya"
                                                : "Belum ditutup"
                                        }
                                        open={() => openVisit(o.id)}
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
                {page === "delivery" && !dailyReady && (
                    <p class="notice">
                        Daily sync wajib sebelum membuka list Delivery.
                    </p>
                )}
                {page === "delivery" && dailyReady && (
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
                        <DeliveryWorkspace
                            key={owner}
                            store={store}
                            identity={identity}
                            provider={provider}
                            engine={engine}
                            queue={queue}
                            changed={() => void refresh()}
                        />
                        <TripClosing
                            store={store}
                            identity={identity}
                            morning={morning}
                            queue={queue}
                            engine={engine}
                            changed={() => void refresh()}
                        />
                        <CollectionWorkspace
                            key={owner}
                            identity={identity}
                            provider={provider}
                            store={store}
                            engine={engine}
                            queue={queue}
                            changed={() => void refresh()}
                        />
                        <button
                            class="secondary full"
                            onClick={() =>
                                setDialog({
                                    type: "expense",
                                    trip: "TRIP-01",
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
                                <Pill>Employee</Pill>
                            </div>
                        </section>
                        <div class="hris-actions">
                            <button
                                disabled={checkedOut}
                                class="card-row"
                                onClick={() =>
                                    setDialog({
                                        type: "attendance",
                                        event: attended
                                            ? "check_out"
                                            : "check_in",
                                    })
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
                {page === "expenses" && (
                    <ExpenseWorkspace
                        identity={identity}
                        provider={provider}
                        store={store}
                        engine={engine}
                        queue={queue}
                        create={() => setDialog({ type: "expense" })}
                        back={() => go("more")}
                        queued={() => {
                            void refresh();
                            if (navigator.onLine) void engine.flush();
                        }}
                    />
                )}
                {page === "more" && (
                    <>
                        <OrderCorrections
                            store={store}
                            owner={owner}
                            morning={morning}
                            queue={queue}
                            engine={engine}
                            changed={() => void refresh()}
                        />
                        <DeliveryApproval
                            store={store}
                            owner={owner}
                            queue={queue}
                            changed={() => void refresh()}
                        />
                        <DiscountApproval
                            store={store}
                            owner={owner}
                            queue={queue}
                            changed={() => void refresh()}
                        />
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
                        <div
                            style={{
                                display: "flex",
                                gap: "10px",
                                margin: "14px 0",
                            }}
                        >
                            <a
                                href="/web/login?redirect=/field/"
                                class="button secondary"
                                style={{
                                    flex: 1,
                                    display: "inline-flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    gap: "6px",
                                    padding: "10px",
                                    borderRadius: "10px",
                                    textDecoration: "none",
                                    fontWeight: "600",
                                    fontSize: "0.85rem",
                                    color: "var(--navy)",
                                    border: "1px solid var(--border)",
                                    background: "#fff",
                                }}
                            >
                                <Icon name="user" size={16} /> Ganti Akun Odoo
                            </a>
                            <a
                                href="/web/session/logout?redirect=/field/"
                                class="button secondary"
                                style={{
                                    flex: 1,
                                    display: "inline-flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    gap: "6px",
                                    padding: "10px",
                                    borderRadius: "10px",
                                    textDecoration: "none",
                                    fontWeight: "600",
                                    fontSize: "0.85rem",
                                    color: "#dc2626",
                                    border: "1px solid #fecaca",
                                    background: "#fff5f5",
                                }}
                            >
                                <Icon name="close" size={16} /> Keluar (Logout)
                            </a>
                        </div>
                        <button
                            class="secondary full"
                            onClick={() => go("expenses")}
                        >
                            <Icon name="wallet" size={20} /> Realisasi & saldo
                            uang lapangan
                        </button>
                        <label class="local-mode-control">
                            Mode respons transaksi lokal
                            <select
                                aria-label="Mode respons"
                                value={scenario}
                                onChange={(event) =>
                                    setScenario(
                                        event.currentTarget.value as Scenario,
                                    )
                                }
                            >
                                <option value="normal">Normal</option>
                                <option value="approval">
                                    Menunggu approval
                                </option>
                                <option value="rejected">Ditolak</option>
                                <option value="timeout">
                                    Jaringan gagal / 503
                                </option>
                                <option value="expired">
                                    Sesi habis / 401
                                </option>
                            </select>
                        </label>
                        <Heading
                            title="Aktivitas perangkat ini"
                            note="Terkirim berbeda dengan disetujui atau diposting."
                        />
                        <SyncDiagnostics
                            key={owner}
                            store={store}
                            owner={owner}
                            queue={queue}
                            online={online}
                        />
                        <p class="footnote">
                            Binding perangkat, approval resmi, notifikasi
                            backend dan pengiriman evidence menunggu integrasi
                            API. Tidak ada token atau dokumen gaji di cache
                            lokal.
                        </p>
                    </>
                )}
            </main>
            <nav class="bottom-nav" aria-label="Navigasi utama">
                {nav.map((p) => (
                    <button
                        key={p.id}
                        class={
                            page === p.id ||
                            (page === "expenses" && p.id === "more") ||
                            (page === "delivery" && p.id === "sales")
                                ? "active"
                                : ""
                        }
                        aria-current={
                            page === p.id ||
                            (p.id === "sales" && page === "delivery")
                                ? "page"
                                : undefined
                        }
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
                    startSession={startSession}
                    close={() => setDialog(undefined)}
                />
            )}
        </div>
    );
}
function OutletCard({
    outlet,
    open,
    status,
}: {
    status?: string;
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
                {status && <p>{status}</p>}
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
function FormDialog({
    dialog,
    identity,
    snapshot,
    owner,
    submit,
    startSession,
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
    startSession: (
        event: "check_in" | "check_out",
        evidence: EvidenceRef,
    ) => Promise<void>;
    close: () => void;
}) {
    const focusOrigin = useRef(document.activeElement as HTMLElement | null);
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const [qty, setQty] = useState<Record<string, number>>({});
    const [principal, setPrincipal] = useState(
        () => snapshot.products[0]?.principal ?? "mayora",
    );
    const [units, setUnits] = useState<Record<string, OrderUom>>({});
    const [discount, setDiscount] = useState(0);
    const [discountReason, setDiscountReason] = useState("");
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
                        units?: Record<string, OrderUom>;
                        discount?: number;
                        discountReason?: string;
                        evidence?: EvidenceRef;
                    };
                    setQty(v.quantities ?? {});
                    setPrincipal(v.principal ?? "mayora");
                    setUnits(v.units ?? {});
                    setDiscount(v.discount ?? 0);
                    setDiscountReason(v.discountReason ?? "");
                    if (v.evidence) setEvidence(v.evidence);
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
                .draft(owner, key, {
                    quantities: qty,
                    principal,
                    units,
                    discount,
                    discountReason,
                    ...(evidence ? { evidence } : {}),
                })
                .catch(() =>
                    setError("Draft gagal disimpan. Periksa penyimpanan."),
                );
    }, [qty, principal, units, discount, discountReason, evidence, restored]);
    useEffect(() => {
        const old = document.body.style.overflow;
        document.body.style.overflow = "hidden";
        const previousFocus = focusOrigin.current;
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
            requestAnimationFrame(() => {
                if (previousFocus?.isConnected) previousFocus.focus();
            });
            document.removeEventListener("keydown", keys);
        };
    }, []);
    const orderLines = Object.entries(qty).filter(([, q]) => q > 0);
    const title = {
        order: "Buat Sales Order",
        extra: "Ajukan extra call",
        proof: "Bukti pengiriman",
        expense: "Uang lapangan",
        attendance: "Absensi foto & lokasi",
        leave: "Pengajuan cuti",
        profile: "Profil & Sesi Akun",
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
                if (!evidence)
                    throw new Error(
                        "Ambil foto display outlet sebelum mengirim order.",
                    );
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
                        uom: units[l.productId] ?? "carton",
                    })),
                    pricing_version: 1,
                    ...(discount > 0
                        ? {
                              discount_request: {
                                  percent: discount,
                                  reason: discountReason,
                              },
                          }
                        : {}),
                    note: String(f.get("note") ?? ""),
                    observed_total: String(
                        orderQuote(
                            lines.map((l) => ({
                                product_id: l.productId,
                                qty: String(l.quantity),
                                uom: units[l.productId] ?? "carton",
                            })),
                            snapshot,
                            discount > 0
                                ? { percent: discount, reason: discountReason }
                                : undefined,
                        ).requestedTotal,
                    ),
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
                if (dialog.type === "attendance") {
                    await startSession(dialog.event ?? "check_in", evidence);
                    close();
                    return;
                }
                if (dialog.type !== "proof")
                    throw new Error("Form bukti tidak dikenal.");
                type = "delivery.proof.submit";
                payload = {
                    event: f.get("event"),
                    delivery_id: dialog.delivery,
                    result: f.get("result"),
                    evidence,
                    map_status: "pending",
                };
                label = `POD • ${dialog.delivery}`;
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
        <div class="modal-backdrop page-backdrop">
            <section
                class="sheet full-page-form"
                role="dialog"
                aria-modal="true"
                aria-labelledby="dialog-title"
            >
                <header class="sheet-head">
                    <div>
                        <p class="eyebrow">{identity.name}</p>
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
                                <p class="sheet-subtitle">
                                    {
                                        snapshot.outlets.find(
                                            (o) => o.id === dialog.outlet,
                                        )?.name
                                    }{" "}
                                    · satu principal per order
                                </p>
                                <OrderCatalog
                                    snapshot={snapshot}
                                    principal={principal}
                                    onPrincipal={setPrincipal}
                                    qty={qty}
                                    onQty={setQty}
                                    units={units}
                                    onUnits={setUnits}
                                />
                                <details class="order-extra">
                                    <summary>Catatan & diskon</summary>
                                    <label>
                                        Diskon diminta (%)
                                        <input
                                            aria-label="Diskon diminta (%)"
                                            type="number"
                                            min="0"
                                            max="100"
                                            step="1"
                                            inputMode="numeric"
                                            value={discount}
                                            onInput={(e) =>
                                                setDiscount(
                                                    Number(
                                                        e.currentTarget.value,
                                                    ),
                                                )
                                            }
                                        />
                                    </label>
                                    {discount > 0 && (
                                        <label>
                                            Alasan permintaan diskon
                                            <textarea
                                                required
                                                minLength={3}
                                                maxLength={500}
                                                value={discountReason}
                                                onInput={(e) =>
                                                    setDiscountReason(
                                                        e.currentTarget.value,
                                                    )
                                                }
                                            />
                                        </label>
                                    )}
                                    <label>
                                        Catatan order
                                        <textarea
                                            name="note"
                                            maxLength={500}
                                            placeholder="Permintaan outlet (opsional)"
                                        />
                                    </label>
                                </details>
                                <DisplayPhoto
                                    store={store}
                                    owner={owner}
                                    value={evidence}
                                    outletName={
                                        snapshot.outlets.find(
                                            (o) => o.id === dialog.outlet,
                                        )?.name ?? "Outlet"
                                    }
                                    coordinates={(() => {
                                        const outlet = snapshot.outlets.find(
                                            (o) => o.id === dialog.outlet,
                                        );
                                        return outlet
                                            ? {
                                                  latitude: outlet.latitude,
                                                  longitude: outlet.longitude,
                                              }
                                            : undefined;
                                    })()}
                                    onChange={setEvidence}
                                />
                                <p class="footnote">
                                    Harga akhir, kredit dan approval below-HPP
                                    diputuskan backend. Angka ini estimasi.
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
                                            Tanggal bisnis:{" "}
                                            {identity.businessDate}. Pengajuan
                                            BBM H-1 memerlukan foto odometer;
                                            realisasi memerlukan struk dan foto
                                            odometer setelah isi.
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
                                    <select
                                        name="event"
                                        value={dialog.event ?? "check_in"}
                                        disabled
                                    >
                                        <option value="check_in">
                                            Absensi Masuk (Checkin)
                                        </option>
                                        <option value="check_out">
                                            Absensi Keluar (Checkout)
                                        </option>
                                    </select>
                                </label>
                                <AttendanceCapture
                                    store={store}
                                    owner={owner}
                                    onChange={setEvidence}
                                    employeeName={identity.name}
                                    companyName={
                                        identity.companyName ??
                                        `Perusahaan #${identity.companyId}`
                                    }
                                    mapSite={
                                        snapshot.office
                                            ? {
                                                  ...snapshot.office,
                                                  simulated:
                                                      snapshot.office
                                                          .coordinate_status !==
                                                      "verified",
                                              }
                                            : undefined
                                    }
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
                        {dialog.type === "profile" && (
                            <div
                                style={{
                                    display: "flex",
                                    flexDirection: "column",
                                    gap: "16px",
                                }}
                            >
                                <div
                                    style={{
                                        display: "flex",
                                        alignItems: "center",
                                        gap: "14px",
                                        padding: "14px",
                                        background: "#f8fafc",
                                        borderRadius: "14px",
                                        border: "1px solid #e2e8f0",
                                    }}
                                >
                                    <span class="avatar large">
                                        {identity.name[0]}
                                    </span>
                                    <div>
                                        <h3
                                            style={{
                                                fontSize: "1.1rem",
                                                fontWeight: "700",
                                                margin: 0,
                                            }}
                                        >
                                            {identity.name}
                                        </h3>
                                        <p
                                            class="muted"
                                            style={{ margin: "2px 0 0" }}
                                        >
                                            {identity.title}
                                        </p>
                                        <small
                                            style={{
                                                color: "#004ecc",
                                                fontWeight: "600",
                                                display: "block",
                                                marginTop: "2px",
                                            }}
                                        >
                                            PT Manado Distribusi Utama
                                        </small>
                                    </div>
                                </div>
                                <div
                                    style={{
                                        display: "flex",
                                        flexDirection: "column",
                                        gap: "8px",
                                    }}
                                >
                                    <div
                                        style={{
                                            display: "flex",
                                            justifyContent: "space-between",
                                            fontSize: "0.85rem",
                                            padding: "8px 0",
                                            borderBottom: "1px solid #f1f5f9",
                                        }}
                                    >
                                        <span class="muted">Perusahaan</span>
                                        <strong>
                                            PT Manado Distribusi Utama
                                        </strong>
                                    </div>
                                    <div
                                        style={{
                                            display: "flex",
                                            justifyContent: "space-between",
                                            fontSize: "0.85rem",
                                            padding: "8px 0",
                                            borderBottom: "1px solid #f1f5f9",
                                        }}
                                    >
                                        <span class="muted">Gudang & Hub</span>
                                        <strong>
                                            Interchange Maumbi, Manado
                                        </strong>
                                    </div>
                                    <div
                                        style={{
                                            display: "flex",
                                            justifyContent: "space-between",
                                            fontSize: "0.85rem",
                                            padding: "8px 0",
                                            borderBottom: "1px solid #f1f5f9",
                                        }}
                                    >
                                        <span class="muted">Rute & Sesi</span>
                                        <strong>WITA (GMT+8) Active</strong>
                                    </div>
                                </div>
                                <div
                                    style={{
                                        display: "flex",
                                        flexDirection: "column",
                                        gap: "10px",
                                        marginTop: "10px",
                                    }}
                                >
                                    <a
                                        href="/web/login?redirect=/field/"
                                        class="button primary"
                                        style={{
                                            display: "flex",
                                            alignItems: "center",
                                            justifyContent: "center",
                                            gap: "8px",
                                            padding: "12px",
                                            background: "#001a57",
                                            color: "#ffffff",
                                            borderRadius: "10px",
                                            textDecoration: "none",
                                            fontWeight: "600",
                                            fontSize: "0.95rem",
                                        }}
                                    >
                                        <Icon name="user" size={18} /> Masuk
                                        Akun Odoo / Ganti Akun
                                    </a>
                                    <a
                                        href="/web/session/logout?redirect=/field/"
                                        class="button secondary"
                                        style={{
                                            display: "flex",
                                            alignItems: "center",
                                            justifyContent: "center",
                                            gap: "8px",
                                            padding: "12px",
                                            background: "#fff0f0",
                                            color: "#dc2626",
                                            border: "1px solid #fecaca",
                                            borderRadius: "10px",
                                            textDecoration: "none",
                                            fontWeight: "600",
                                            fontSize: "0.95rem",
                                        }}
                                    >
                                        <Icon name="close" size={18} /> Keluar
                                        dari Sesi (Logout)
                                    </a>
                                </div>
                            </div>
                        )}
                        {error && (
                            <div class="error-box" role="alert">
                                <Icon name="warning" size={20} />
                                {error}
                            </div>
                        )}
                    </div>
                    {dialog.type !== "profile" ? (
                        <footer
                            class={`sheet-footer${dialog.type === "order" ? " order-footer" : ""}`}
                        >
                            {dialog.type === "order" ? (
                                <>
                                    <OrderSummary
                                        snapshot={snapshot}
                                        qty={qty}
                                        units={units}
                                        discount={discount}
                                    />
                                    {!evidence && (
                                        <p class="summary-hint">
                                            Foto display outlet wajib sebelum
                                            order dikirim.
                                        </p>
                                    )}
                                    <button
                                        type="submit"
                                        class="order-submit"
                                        disabled={
                                            busy ||
                                            !restored ||
                                            orderLines.length === 0 ||
                                            !evidence
                                        }
                                    >
                                        {busy
                                            ? "Menyimpan…"
                                            : "Simpan ke antrean"}
                                    </button>
                                </>
                            ) : (
                                <>
                                    <button
                                        type="button"
                                        class="secondary"
                                        onClick={close}
                                        disabled={busy}
                                    >
                                        Kembali
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={
                                            busy ||
                                            !restored ||
                                            (dialog.type === "attendance" &&
                                                !evidence)
                                        }
                                    >
                                        {busy
                                            ? "Menyimpan…"
                                            : dialog.type === "attendance"
                                              ? dialog.event === "check_out"
                                                  ? "Check out"
                                                  : "Check in"
                                              : "Simpan ke antrean"}
                                    </button>
                                </>
                            )}
                        </footer>
                    ) : (
                        <footer
                            class="sheet-footer"
                            style={{ justifyContent: "center" }}
                        >
                            <button
                                type="button"
                                class="secondary full"
                                onClick={close}
                                style={{ margin: 0 }}
                            >
                                Tutup
                            </button>
                        </footer>
                    )}
                </form>
            </section>
        </div>
    );
}
