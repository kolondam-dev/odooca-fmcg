import type { ComponentChildren } from "preact";
import { Button, Card, CardHead, ListRow, Stats } from "../ui";
import type { Snapshot } from "../domain/contracts";

/** Isi Beranda sesuai DS: kartu hari kerja (slot), angka ringkas, kunjungan berikutnya. */
export function Home({
    day,
    outlets,
    doneIds,
    orders,
    confirmedOrders,
    canWork,
    isSales,
    isDelivery,
    deliveries,
    pendingExpense,
    onOpenVisit,
    onSales,
    onDelivery,
    onExpense,
}: {
    /** Kartu absen/sinkron (MorningSession). */
    day: ComponentChildren;
    outlets: Snapshot["outlets"];
    doneIds: Set<string>;
    orders: number;
    /** Order yang sudah diterima server (status antrean "accepted"). */
    confirmedOrders: number;
    /** Sesi aktif dan belum absen pulang. */
    canWork: boolean;
    isSales: boolean;
    isDelivery: boolean;
    deliveries: number;
    pendingExpense: number;
    onOpenVisit: (id: string) => void;
    onSales: () => void;
    onDelivery: () => void;
    onExpense: () => void;
}) {
    const next = outlets.find((o) => !doneIds.has(o.id));
    const done = outlets.filter((o) => doneIds.has(o.id)).length;
    return (
        <div class="ui-stack ui-home">
            {day}
            {isSales && (
                <Stats
                    items={[
                        {
                            value: outlets.length
                                ? `${done}/${outlets.length}`
                                : "–",
                            label: "Outlet selesai",
                        },
                        {
                            value: outlets.length ? orders : "–",
                            label: "Order",
                        },
                        {
                            value: outlets.length ? confirmedOrders : "–",
                            label: "Order terkonfirmasi",
                        },
                    ]}
                />
            )}
            {isSales && canWork && next && (
                <>
                    <span class="ui-section">
                        Outlet berikutnya · {done + 1} dari {outlets.length}
                    </span>
                    <Card>
                        <CardHead title={next.name} />
                        <span class="ui-row__sub">{next.address}</span>
                        <span class="ui-row__sub">{next.time}</span>
                        <Button onClick={() => onOpenVisit(next.id)}>
                            Mulai kunjungan · {next.name}
                        </Button>
                        <Button variant="sec" onClick={onSales}>
                            Lihat semua outlet
                        </Button>
                    </Card>
                </>
            )}
            {isDelivery && canWork && (
                <Card>
                    <CardHead title="Pengiriman" />
                    <span class="ui-row__sub">
                        {deliveries} manifest hari ini
                    </span>
                    <Button onClick={onDelivery}>Buka pengiriman</Button>
                </Card>
            )}
            {canWork && (
                <Card tight>
                    <ListRow
                        icon="wallet"
                        title="Uang lapangan"
                        sub={`${pendingExpense} pending`}
                        onClick={onExpense}
                    />
                </Card>
            )}
        </div>
    );
}
