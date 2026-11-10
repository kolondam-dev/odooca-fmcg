import { useState } from "preact/hooks";
import type { ComponentChildren } from "preact";
import type { Identity } from "../domain/contracts";
import type { QueueItem } from "../storage/store";
import { Card, ListRow } from "../ui";
import {
    ActivityScreen,
    QueueScreen,
    RequestsScreen,
    requestsFrom,
} from "./ActivityScreens";
import type { FieldStore } from "../storage/store";

type Sub = null | "queue" | "activity" | "requests";

/** Lainnya (DS): aktivitas & sinkronisasi, akun, tentang. Alat QA/legacy tetap di bawah. */
export function MorePage({
    identity,
    store,
    owner,
    queue,
    online,
    syncing,
    pending,
    onSync,
    onExpenses,
    runningMode,
    setRunningMode,
    corrections,
    qaTools,
}: {
    identity: Identity;
    store: FieldStore;
    owner: string;
    queue: QueueItem[];
    online: boolean;
    syncing: boolean;
    pending: number;
    onSync: () => void;
    onExpenses: () => void;
    runningMode: "demo" | "live";
    setRunningMode: (m: "demo" | "live") => void;
    /** Alur koreksi SO (dipasang di Riwayat pengajuan). */
    corrections: ComponentChildren;
    qaTools?: ComponentChildren;
}) {
    const [sub, setSub] = useState<Sub>(null);
    const waiting = requestsFrom(queue).filter(
        (r) => r.status.label === "Menunggu",
    ).length;
    const [account, setAccount] = useState(false);
    return (
        <>
            <p class="ui-sectionlabel">Aktivitas & sinkronisasi</p>
            <Card>
                <ListRow
                    icon="sync"
                    title="Antrean sinkronisasi"
                    sub={
                        pending
                            ? `${pending} aktivitas menunggu kirim`
                            : online
                              ? "Semua terkirim"
                              : "Offline • antrean disimpan di perangkat"
                    }
                    status={
                        pending
                            ? { tone: "warn", label: `${pending} tertunda` }
                            : undefined
                    }
                    onClick={() => setSub("queue")}
                />
                <ListRow
                    icon="clock"
                    title="Riwayat aktivitas"
                    sub="Terkirim, ditolak, diposting"
                    onClick={() => setSub("activity")}
                    divider
                />
                <ListRow
                    icon="receipt"
                    title="Riwayat pengajuan"
                    sub="Diskon & approval"
                    status={
                        waiting
                            ? { tone: "warn", label: `${waiting} menunggu` }
                            : undefined
                    }
                    onClick={() => setSub("requests")}
                    divider
                />
                <ListRow
                    icon="wallet"
                    title="Uang lapangan"
                    sub="Realisasi & saldo"
                    onClick={onExpenses}
                    divider
                />
            </Card>
            <p class="ui-sectionlabel">Akun</p>
            <Card>
                <ListRow
                    icon="user"
                    title={identity.name}
                    sub={identity.title}
                    onClick={() => setAccount((v) => !v)}
                />
                {account ? (
                    <div class="pos-retry">
                        <a
                            class="ui-btn ui-btn--sec"
                            href="/web/login?redirect=/field/"
                        >
                            Ganti akun Odoo
                        </a>
                    </div>
                ) : null}
                <a
                    class="ui-row ui-row--div ui-row--danger"
                    href="/web/session/logout?redirect=/field/"
                >
                    <span class="ui-row__body">
                        <span class="ui-row__title">Keluar</span>
                    </span>
                </a>
            </Card>
            <p class="ui-sectionlabel">Tentang</p>
            <Card>
                <ListRow
                    icon="signal"
                    title="Versi aplikasi"
                    sub={`0.1 · ${online ? "online" : "offline"}`}
                />
                <ListRow
                    icon="check"
                    title="Status integrasi"
                    sub={online ? "Odoo terhubung" : "Menunggu koneksi"}
                    status={{
                        tone: online ? "ok" : "warn",
                        label: online ? "OK" : "Offline",
                    }}
                    divider
                />
                <div class="running-mode-section">
                    <div class="running-mode-header">
                        <label>Mode Operasi Aplikasi</label>
                        <span class={`mode-tag ${runningMode}`}>
                            {runningMode.toUpperCase()}
                        </span>
                    </div>
                    <div
                        class="running-mode-toggle"
                        role="group"
                        aria-label="Pilih mode operasi"
                    >
                        {(["demo", "live"] as const).map((m) => (
                            <button
                                key={m}
                                type="button"
                                class={`mode-choice ${runningMode === m ? "active" : ""}`}
                                onClick={() => setRunningMode(m)}
                            >
                                {m.toUpperCase()}
                            </button>
                        ))}
                    </div>
                    <p class="mode-desc">
                        {runningMode === "demo"
                            ? "Mode DEMO: Validasi geofence, waktu, dan foto diabaikan. Transaksi dapat diinput dari mana saja."
                            : "Mode LIVE: Validasi ketat geofence, waktu GPS, dan foto resmi diberlakukan."}
                    </p>
                </div>
            </Card>
            {qaTools}
            {sub === "queue" ? (
                <QueueScreen
                    store={store}
                    owner={owner}
                    queue={queue}
                    online={online}
                    syncing={syncing}
                    onSync={onSync}
                    onClose={() => setSub(null)}
                />
            ) : null}
            {sub === "activity" ? (
                <ActivityScreen
                    store={store}
                    owner={owner}
                    queue={queue}
                    online={online}
                    onClose={() => setSub(null)}
                />
            ) : null}
            {sub === "requests" ? (
                <RequestsScreen queue={queue} onClose={() => setSub(null)}>
                    {corrections}
                </RequestsScreen>
            ) : null}
        </>
    );
}
