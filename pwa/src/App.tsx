import { EvidenceIdentityContext } from "./ui/evidenceIdentity";
import { ViewMemoryContext, useRememberedScroll } from "./ui/viewMemory";
import { TaskForm } from "./components/TaskForm";
import { ExtraCallScreen } from "./components/ExtraCallScreen";
import { LiveClock } from "./components/LiveClock";
import { useNavigation, type Page, type Dialog } from "./ui/navigation";
import { AppHeader, BottomNav } from "./ui";
import { Home } from "./components/Home";
import { AttendanceScreen } from "./components/AttendanceScreen";
import { OrderScreen } from "./components/OrderScreen";
import { DisplayStockScreen } from "./components/DisplayStockScreen";
import { OutletDirectory } from "./components/OutletDirectory";
import { TripClosing } from "./components/TripClosing";
import { OrderCorrections } from "./components/OrderCorrections";
import { DeliveryApproval } from "./components/DeliveryApproval";
import { DiscountApproval } from "./components/DiscountApproval";
import type { ComponentChildren } from "preact";
import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import { HttpProvider } from "./data/provider";
import { useRunningMode, DEMO_BANNER_TEXT } from "./domain/running-mode";
import { Login } from "./components/Login";
import {
    canOpen,
    ownerKey,
    type Command,
    type FieldProvider,
    type Identity,
    type Scenario,
    type Snapshot,
} from "./domain/contracts";
import { VisitPanel } from "./components/VisitPanel";
import { SalesVisits, captureVisitLocation } from "./domain/visits";
import { CollectionWorkspace } from "./components/CollectionWorkspace";
import { DeliveryWorkspace } from "./components/DeliveryWorkspace";
import { ExpenseWorkspace } from "./components/ExpenseWorkspace";
import { Brand } from "./components/Brand";
import { MorePage } from "./components/MorePage";
import { MorningSession } from "./components/MorningSession";
import {
    morningReady,
    MorningSimulation,
    type MorningRecord,
} from "./domain/morning";
import { Outbox } from "./domain/outbox";
import { haptic } from "./domain/format";
import { FieldStore, type QueueItem } from "./storage/store";
import { Icon, type IconName } from "./components/Icon";
import { type EvidenceRef } from "./components/Evidence";

const pages: { id: Page; name: string; icon: IconName }[] = [
    { id: "home", name: "Beranda", icon: "house" },
    { id: "sales", name: "Sales", icon: "store" },
    { id: "delivery", name: "Delivery", icon: "truck" },
    { id: "hris", name: "HRIS", icon: "user" },
    { id: "more", name: "Lainnya", icon: "grid" },
];
const store = new FieldStore();
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
        const source = new HttpProvider();
        const identity = await source.bootstrap();
        const { MockProvider } = await import("./data/mock");
        // Authentication, identity and work data are real. All sales orders,
        // including discount requests, go to Odoo. Delivery remains simulated.
        const actor =
            identity.roles.includes("delivery") &&
            !identity.roles.includes("sales")
                ? "delivery"
                : identity.roles.includes("delivery") &&
                    identity.roles.includes("sales")
                  ? "canvass"
                  : "sales";
        const provider = new MockProvider(actor, true, source);
        const snapshot = await provider.snapshot();
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
    const [runningMode, setRunningMode] = useRunningMode();
    useEffect(() => {
        const app = document.querySelector<HTMLElement>(".app-shell");
        const header = document.querySelector<HTMLElement>(".header-fixed"),
            nav = document.querySelector<HTMLElement>(".bottom-nav");
        const measure = () => {
            app?.style.setProperty(
                "--field-header-height",
                `${header?.offsetHeight ?? 56}px`,
            );
            app?.style.setProperty(
                "--field-nav-height",
                `${nav?.offsetHeight ?? 70}px`,
            );
        };
        const viewport = window.visualViewport;
        const resize = () => {
            if (viewport && Math.abs(viewport.scale - 1) < 0.01)
                app?.style.setProperty(
                    "--field-viewport-height",
                    `${viewport.height}px`,
                );
            else app?.style.removeProperty("--field-viewport-height");
        };
        resize();
        viewport?.addEventListener("resize", resize);
        measure();
        const observer = new ResizeObserver(measure);
        if (header) observer.observe(header);
        if (nav) observer.observe(nav);
        return () => {
            observer.disconnect();
            viewport?.removeEventListener("resize", resize);
        };
    }, []);
    const [now, setNow] = useState(Date.now());
    useEffect(() => {
        const timer = setInterval(() => setNow(Date.now()), 10000);
        return () => clearInterval(timer);
    }, []);
    const [queue, setQueue] = useState<QueueItem[]>([]);
    const [online, setOnline] = useState(navigator.onLine);
    const [toast, setToast] = useState("");
    const [finishSignal, setFinishSignal] = useState(0);
    const [syncing, setSyncing] = useState(false);
    const [scenario, setScenario] = useState<Scenario>("normal");
    const owner = ownerKey(identity);
    const assignedOutlets = useRef(initialSnapshot.outlets);
    const navigation = useNavigation(
        `${owner}:${identity.businessDate}`,
        (route) => {
            const order =
                route.dialog?.type === "order" ? route.dialog : undefined;
            return (
                canOpen(identity.roles, route.page) &&
                (!route.outlet || route.page === "sales") &&
                (route.dialog?.type !== "extra" ||
                    identity.roles.includes("sales")) &&
                (route.dialog?.type !== "proof" ||
                    identity.roles.includes("delivery")) &&
                (!route.outlet ||
                    assignedOutlets.current.some(
                        (o) => o.id === route.outlet,
                    )) &&
                (!order ||
                    (identity.roles.includes("sales") &&
                        assignedOutlets.current.some(
                            (o) => o.id === order.outlet,
                        )))
            );
        },
    );
    const { page, dialog, outlet: visitOutlet } = navigation.route;
    const viewMemory = useMemo(
        () => new Map<string, unknown>(),
        [owner, identity.businessDate],
    );
    const mainScroll = useRememberedScroll(page, viewMemory);
    const setPage = (page: Page) => navigation.navigate({ page });
    const setDialog = (dialog?: Dialog) => navigation.dialog(dialog);
    const setVisitOutlet = (outlet?: string) =>
        navigation.navigate({ page: "sales", outlet });
    const [morning, setMorning] = useState<MorningRecord>();
    const [morningLoaded, setMorningLoaded] = useState(false);
    const [morningError, setMorningError] = useState("");
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
    assignedOutlets.current = snapshot.outlets;
    const morningService = useMemo(
        () => new MorningSimulation(store, identity, provider),
        [identity, provider],
    );
    useEffect(() => {
        let active = true;
        setMorningLoaded(false);
        setMorningError("");
        void morningService
            .restore()
            .then((record) => {
                if (active) setMorning(record);
            })
            .catch(() => {
                if (active) {
                    setMorning(undefined);
                    setMorningError(
                        "Penyimpanan sesi tidak tersedia. Kunjungan tetap terkunci.",
                    );
                }
            })
            .finally(() => {
                if (active) setMorningLoaded(true);
            });
        return () => {
            active = false;
        };
    }, [morningService, morningRevision]);
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
        setToast("");
        navigation.navigate({ page: "sales", outlet });
        haptic();
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
        const id = setTimeout(() => setToast(""), 3000);
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
    const doneOutletIds = new Set(
        queue
            .filter(
                (q) =>
                    q.command?.type === "sales.visit.check_out" &&
                    q.command.payload?.business_date === identity.businessDate,
            )
            .map((q) =>
                String((q.command.payload as { outlet_id?: string }).outlet_id),
            ),
    );
    const orderCount = queue.filter(
        (q) =>
            q.command?.type === "sales.order.submit" &&
            q.command.payload?.business_date === identity.businessDate,
    ).length;
    const go = (id: Page) => {
        if (canOpen(identity.roles, id)) {
            setPage(id);
            setToast("");
            haptic();
            window.scrollTo({ top: 0 });
        }
    };
    async function submit(
        type: Command["type"],
        payload: Record<string, unknown>,
        label: string,
        keepOpen?: boolean,
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
        if (!keepOpen) setDialog(undefined);
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
        <EvidenceIdentityContext.Provider
            value={{
                company: identity.companyName ?? identity.companyId,
                employee: identity.name,
            }}
        >
            <ViewMemoryContext.Provider value={viewMemory}>
                <div class="app-shell">
                    <div class="header-fixed">
                        <AppHeader
                            eyebrow={
                                page === "home" ? <LiveClock /> : undefined
                            }
                            title={
                                {
                                    home: <>Selamat bekerja, {identity.name}</>,
                                    sales: "Outlet",
                                    delivery: "Delivery",
                                    hris: "HRIS",
                                    expenses: "Uang lapangan",
                                    more: "Lainnya",
                                }[page] ?? "Beranda"
                            }
                            online={online}
                            pending={pending}
                            initial={identity.name[0]}
                            onSync={() => go("more")}
                            onProfile={() => setDialog({ type: "profile" })}
                            extra={
                                <button
                                    type="button"
                                    class={`running-mode-pill ${runningMode}`}
                                    aria-label={`Mode Operasi: ${runningMode.toUpperCase()}`}
                                    title={`Mode ${runningMode.toUpperCase()} aktif (klik untuk beralih)`}
                                    onClick={() =>
                                        setRunningMode(
                                            runningMode === "demo"
                                                ? "live"
                                                : "demo",
                                        )
                                    }
                                >
                                    {runningMode.toUpperCase()}
                                </button>
                            }
                        />
                        {runningMode === "demo" && (
                            <div
                                class="mode-indicator demo-running-banner"
                                role="note"
                            >
                                {DEMO_BANNER_TEXT}
                            </div>
                        )}
                    </div>
                    <main
                        ref={mainScroll}
                        id="main-content"
                        class={`content${page === "sales" ? " sales-content" : ""}`}
                    >
                        {page === "home" && (
                            <Home
                                day={
                                    identity.roles.some(
                                        (r) =>
                                            r === "sales" || r === "delivery",
                                    ) ? (
                                        <MorningSession
                                            key={`morning:${morningRevision}`}
                                            identity={identity}
                                            provider={provider}
                                            store={store}
                                            onChange={setMorning}
                                            record={morning}
                                            loaded={morningLoaded}
                                            restoreError={morningError}
                                            attended={attended}
                                            onAttend={() =>
                                                setDialog({
                                                    type: "attendance",
                                                })
                                            }
                                            onClockOut={() =>
                                                setDialog({
                                                    type: "attendance",
                                                    event: "check_out",
                                                })
                                            }
                                        />
                                    ) : null
                                }
                                outlets={snapshot.outlets}
                                doneIds={doneOutletIds}
                                orders={orderCount}
                                canWork={dailyReady && attended && !checkedOut}
                                isSales={identity.roles.includes("sales")}
                                isDelivery={identity.roles.includes("delivery")}
                                deliveries={snapshot.deliveries.length}
                                pendingExpense={pending + review}
                                onOpenVisit={(id) => openVisit(id)}
                                onSales={() => go("sales")}
                                onDelivery={() => go("delivery")}
                                onExpense={() => setDialog({ type: "expense" })}
                            />
                        )}
                        {page === "sales" && !dailyReady && (
                            <p class="notice">
                                Buka sesi kerja sebelum membuka daftar outlet.
                                <button
                                    onClick={() =>
                                        setDialog({ type: "attendance" })
                                    }
                                >
                                    Absensi masuk
                                </button>
                            </p>
                        )}
                        {page === "sales" && dailyReady && (
                            <>
                                {!visitOutlet && (
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
                                    </>
                                )}
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
                                            display={() =>
                                                setDialog({
                                                    type: "display",
                                                    outlet: visitOutlet,
                                                })
                                            }
                                            dialogType={dialog?.type}
                                            finishSignal={finishSignal}
                                            back={() =>
                                                setVisitOutlet(undefined)
                                            }
                                        />
                                    )}
                                {!visitOutlet && (
                                    <OutletDirectory
                                        outlets={snapshot.outlets}
                                        open={openVisit}
                                        extra={() =>
                                            setDialog({ type: "extra" })
                                        }
                                        closed={(id) => doneOutletIds.has(id)}
                                    />
                                )}
                            </>
                        )}
                        {page === "delivery" && !dailyReady && (
                            <p class="notice">
                                Daily sync wajib sebelum membuka list Delivery.
                            </p>
                        )}
                        {page === "delivery" && dailyReady && (
                            <>
                                <section class="trip-card">
                                    <Icon name="truck" size={36} />
                                    <div>
                                        <strong>TRIP-DEMO-01</strong>
                                        <p>
                                            2 pengiriman · 20 karton · DB • DEMO
                                        </p>
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
                                    Bukti POD tidak otomatis menjadikan picking
                                    selesai. Posting stok dan settlement tetap
                                    di Odoo.
                                </p>
                            </>
                        )}
                        {page === "hris" && (
                            <>
                                <section class="profile-card">
                                    <span class="avatar large">
                                        {identity.name[0]}
                                    </span>
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
                                            <small>
                                                Foto, lokasi & hasil validasi
                                            </small>
                                        </div>
                                        <Icon name="caret" />
                                    </button>
                                    <button
                                        class="card-row"
                                        onClick={() =>
                                            setDialog({ type: "leave" })
                                        }
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
                                        onClick={() =>
                                            setDialog({ type: "expense" })
                                        }
                                    >
                                        <span class="metric-icon amber">
                                            <Icon name="wallet" />
                                        </span>
                                        <div>
                                            <strong>
                                                Petty cash luar kota
                                            </strong>
                                            <small>
                                                Makan, BBM & penginapan
                                            </small>
                                        </div>
                                        <Icon name="caret" />
                                    </button>
                                </div>
                                <section class="paper-card">
                                    <Icon name="receipt" size={30} />
                                    <h3>Slip gaji & dokumen pribadi</h3>
                                    <p class="muted">
                                        Belum terintegrasi. Dokumen personal
                                        hanya dibuka online setelah
                                        dipublikasikan backend.
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
                            <MorePage
                                identity={identity}
                                store={store}
                                owner={owner}
                                queue={queue}
                                online={online}
                                syncing={syncing}
                                pending={pending}
                                onSync={() => void sync()}
                                onExpenses={() => go("expenses")}
                                runningMode={runningMode}
                                setRunningMode={setRunningMode}
                                corrections={
                                    <OrderCorrections
                                        store={store}
                                        owner={owner}
                                        morning={morning}
                                        queue={queue}
                                        engine={engine}
                                        changed={() => void refresh()}
                                    />
                                }
                                qaTools={
                                    __QA_TOOLS__ ? (
                                        <>
                                            <p class="ui-sectionlabel">
                                                Alat QA
                                            </p>
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
                                            <label class="local-mode-control">
                                                Mode respons transaksi lokal
                                                <select
                                                    aria-label="Mode respons"
                                                    value={scenario}
                                                    onChange={(event) =>
                                                        setScenario(
                                                            event.currentTarget
                                                                .value as Scenario,
                                                        )
                                                    }
                                                >
                                                    <option value="normal">
                                                        Normal
                                                    </option>
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
                                        </>
                                    ) : null
                                }
                            />
                        )}
                    </main>
                    <BottomNav
                        items={nav.map((p) => ({
                            id: p.id,
                            name: p.name,
                            icon: p.icon,
                            active:
                                page === p.id ||
                                (page === "expenses" && p.id === "more") ||
                                (page === "delivery" && p.id === "sales"),
                            current:
                                page === p.id ||
                                (p.id === "sales" && page === "delivery"),
                            dot: p.id === "more" && pending > 0,
                        }))}
                        onSelect={(id) => go(id as Page)}
                    />
                    <div class="sr-only" aria-live="polite">
                        {online
                            ? ""
                            : "Offline · aktivitas disimpan di perangkat"}
                    </div>
                    {toast && (
                        <div class="toast" role="status">
                            <Icon name="check" size={22} />
                            {toast}
                        </div>
                    )}
                    {dialog?.type === "attendance" && (
                        <AttendanceScreen
                            key={JSON.stringify(dialog)}
                            event={dialog.event ?? "check_in"}
                            store={store}
                            owner={owner}
                            identity={identity}
                            office={snapshot.office}
                            startSession={startSession}
                            close={() => setDialog(undefined)}
                        />
                    )}
                    {dialog?.type === "order" && (
                        <OrderScreen
                            key={JSON.stringify(dialog)}
                            snapshot={snapshot}
                            outletId={dialog.outlet}
                            owner={owner}
                            store={store}
                            provider={provider}
                            queue={queue}
                            submit={submit as never}
                            close={() => setDialog(undefined)}
                            finishVisit={() => {
                                setDialog(undefined);
                                setFinishSignal((n) => n + 1);
                            }}
                        />
                    )}
                    {dialog?.type === "display" && (
                        <DisplayStockScreen
                            key={JSON.stringify(dialog)}
                            snapshot={snapshot}
                            outletId={dialog.outlet}
                            owner={owner}
                            store={store}
                            close={() => setDialog(undefined)}
                        />
                    )}
                    {dialog?.type === "extra" && (
                        <ExtraCallScreen
                            snapshot={snapshot}
                            submit={submit as never}
                            close={() => setDialog(undefined)}
                        />
                    )}
                    {dialog &&
                        dialog.type !== "attendance" &&
                        dialog.type !== "extra" &&
                        dialog.type !== "order" &&
                        dialog.type !== "display" && (
                            <TaskForm
                                key={JSON.stringify(dialog)}
                                dialog={dialog}
                                store={store}
                                identity={identity}
                                snapshot={snapshot}
                                owner={owner}
                                workStatus={
                                    checkedOut
                                        ? "Sesi kerja selesai"
                                        : dailyReady
                                          ? "Sesi kerja aktif"
                                          : "Sesi kerja belum dibuka"
                                }
                                submit={submit}
                                startSession={startSession}
                                close={() => setDialog(undefined)}
                            />
                        )}
                </div>
            </ViewMemoryContext.Provider>
        </EvidenceIdentityContext.Provider>
    );
}
