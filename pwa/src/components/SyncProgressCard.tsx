import { Button, Card, Chip, Progress } from "../ui";
import { Icon } from "./Icon";

/** Tahap nyata `MorningSimulation.open()`; dipakai untuk progres Sinkron (DS). */
export type SyncStage = "check" | "download" | "validate" | "save";

const PROGRESS: Record<SyncStage, number> = {
    check: 10,
    download: 45,
    validate: 80,
    save: 95,
};

type RowState = "pending" | "active" | "error" | "soon";
const ROWS: {
    id: string;
    title: string;
    /** Bagian snapshot tunggal (outlet, produk) atau menunggu backend (K2). */
    source: "snapshot" | "later";
}[] = [
    { id: "outlet", title: "Outlet & PJP hari ini", source: "snapshot" },
    { id: "produk", title: "Produk, harga & stok sistem", source: "snapshot" },
    { id: "ar", title: "Tagihan (AR) outlet", source: "later" },
    { id: "riwayat", title: "SKU riwayat order per toko", source: "later" },
    { id: "diskon", title: "Program diskon & budget", source: "later" },
];

function rowState(
    source: "snapshot" | "later",
    index: number,
    stage: SyncStage | undefined,
    failed: boolean,
): RowState {
    if (source === "later") return "soon";
    if (failed) return index === 0 ? "error" : "pending";
    return stage ? "active" : "pending";
}

/**
 * Kartu "Sinkron data harian" (Sinkron_jalan / Sinkron_gagal). Paket outlet dan
 * produk datang dalam satu snapshot, jadi keduanya aktif dan gagal bersama;
 * tagihan, riwayat dan diskon tampil "Segera tersedia" sampai backend
 * menyediakan bagiannya (K2, K24).
 */
export function SyncProgressCard({
    stage,
    failed,
    online,
    onRetry,
}: {
    stage?: SyncStage;
    failed: boolean;
    online: boolean;
    onRetry: () => void;
}) {
    const value = failed ? 25 : stage ? PROGRESS[stage] : 0;
    return (
        <Card>
            <div class="ui-sync__head">
                <h2 class="ui-sync__title">
                    {failed ? "Sync belum selesai" : "Menyiapkan data kerja"}
                </h2>
                {failed ? (
                    <Chip tone="bad">Gagal</Chip>
                ) : online ? (
                    <Chip tone="ok">Online</Chip>
                ) : (
                    <Chip tone="warn">Offline</Chip>
                )}
            </div>
            <Progress
                value={value}
                tone={failed ? "bad" : "pri"}
                label="Kemajuan sinkron"
            />
            <ul class="ui-sync__list">
                {ROWS.map((row, i) => {
                    const state = rowState(row.source, i, stage, failed);
                    return (
                        <li
                            key={row.id}
                            class={`ui-sync__row is-${state}`}
                            data-sync-row={row.id}
                            data-state={state}
                        >
                            <span class="ui-sync__ico" aria-hidden="true">
                                {state === "active" ? (
                                    <Icon name="sync" size={22} />
                                ) : state === "error" ? (
                                    <Icon name="close" size={22} />
                                ) : state === "soon" ? (
                                    <Icon name="clock" size={22} />
                                ) : (
                                    <i class="ui-sync__ring" />
                                )}
                            </span>
                            <span class="ui-sync__txt">
                                <span class="ui-sync__name">{row.title}</span>
                                {state === "active" ? (
                                    <span class="ui-sync__sub">Mengunduh…</span>
                                ) : state === "error" ? (
                                    <span class="ui-sync__sub is-bad">
                                        Belum terunduh
                                    </span>
                                ) : state === "soon" ? (
                                    <span class="ui-sync__sub">
                                        Segera tersedia
                                    </span>
                                ) : null}
                            </span>
                        </li>
                    );
                })}
            </ul>
            {failed ? (
                <>
                    <Button icon="sync" onClick={onRetry}>
                        Ulangi sinkron
                    </Button>
                    <Button variant="sec" icon="lock" disabled>
                        Lanjut offline
                    </Button>
                    <span class="ui-sync__cap">
                        Lanjut offline tersedia setelah outlet, produk, harga
                        dan stok selesai diunduh.
                    </span>
                </>
            ) : (
                <>
                    <Button disabled>Mulai kunjungan</Button>
                    <span class="ui-sync__cap">
                        Terbuka setelah sync selesai.
                    </span>
                </>
            )}
        </Card>
    );
}
