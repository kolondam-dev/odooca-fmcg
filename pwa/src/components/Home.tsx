import type { ComponentChildren } from "preact";
import { Button, Card, CardHead, Chip, ListRow, Stats } from "../ui";
import type { Snapshot } from "../domain/contracts";
import {
    loadSummary,
    navigationUrl,
    type DeliveryProgress,
} from "../domain/delivery-progress";
import { Icon } from "./Icon";

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
    delivery,
    pendingExpense,
    onOpenVisit,
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
    /** Progres manifest pengiriman dari sesi pagi (kosong bila belum sinkron). */
    delivery?: DeliveryProgress;
    pendingExpense: number;
    onOpenVisit: (id: string) => void;
    onDelivery: () => void;
    onExpense: () => void;
}) {
    const next = outlets.find((o) => !doneIds.has(o.id));
    const done = outlets.filter((o) => doneIds.has(o.id)).length;
    const dp = delivery;
    const dNext = dp?.nextTask;
    const showVisit = isSales && canWork && !!next;
    const showSend = isDelivery && canWork && !!dNext;
    const tripStatus = dp?.nextTrip
        ? dp.nextTrip.finished
            ? { tone: "info" as const, label: "Berjalan" }
            : { tone: "neu" as const, label: "Belum mulai" }
        : undefined;
    const navLink = (latitude: number, longitude: number, label: string) => (
        <a
            class="ui-btn ui-btn--sec ui-btn--md"
            href={navigationUrl(latitude, longitude)}
            target="_blank"
            rel="noopener noreferrer"
        >
            <Icon name="send" size={22} />
            {label}
        </a>
    );
    const distanceLine = (o: Snapshot["outlets"][number]) => (
        <div class="ui-meta">
            <span class="ui-meta__i">
                <Icon name="clock" size={18} />
                {o.time}
            </span>
            {o.distance && (
                <span class="ui-meta__i">
                    <Icon name="pin" size={18} />
                    {o.distance}
                </span>
            )}
        </div>
    );
    const stats = isSales
        ? [
              {
                  value: outlets.length ? `${done}/${outlets.length}` : "–",
                  label: "Outlet selesai",
              },
              ...(isDelivery
                  ? [
                        {
                            value: dp ? `${dp.done}/${dp.total}` : "–",
                            label: "DO selesai",
                        },
                        {
                            value: outlets.length ? orders : "–",
                            label: "Order",
                        },
                    ]
                  : [
                        {
                            value: outlets.length ? orders : "–",
                            label: "Order",
                        },
                        {
                            value: outlets.length ? confirmedOrders : "–",
                            label: "Order terkonfirmasi",
                        },
                    ]),
          ]
        : [
              { value: dp ? dp.total : "–", label: "DO hari ini" },
              { value: dp ? dp.stores : "–", label: "Toko" },
              {
                  value: dp ? `${dp.done}/${dp.total}` : "–",
                  label: "Selesai",
              },
          ];
    return (
        <div class="ui-stack ui-home">
            {day}
            {(isSales || isDelivery) && <Stats items={stats} />}
            {showVisit && showSend && (
                <span class="ui-section">Berikutnya</span>
            )}
            {showVisit && !showSend && (
                <>
                    <span class="ui-section">
                        Outlet berikutnya · {done + 1} dari {outlets.length}
                    </span>
                    <Card>
                        <CardHead title={next.name} />
                        <span class="ui-row__sub">{next.address}</span>
                        {distanceLine(next)}
                        {navLink(
                            next.latitude,
                            next.longitude,
                            "Navigasi ke outlet",
                        )}
                    </Card>
                </>
            )}
            {showVisit && showSend && (
                <Card>
                    <div class="ui-meta ui-meta--between">
                        <span class="ui-kind">
                            <Icon name="store" size={18} />
                            Kunjungan Sales
                        </span>
                        <span class="ui-row__sub">{next.time}</span>
                    </div>
                    <CardHead title={next.name} />
                    <span class="ui-row__sub">
                        {[next.distance, next.address]
                            .filter(Boolean)
                            .join(" · ")}
                    </span>
                </Card>
            )}
            {showSend && !showVisit && (
                <>
                    <span class="ui-section">Pengiriman berikutnya</span>
                    <Card>
                        <CardHead
                            title={dNext.outlet}
                            status={{ tone: "info", label: dNext.id }}
                        />
                        <span class="ui-row__sub">{dNext.address}</span>
                        <div class="ui-meta">
                            <span class="ui-meta__i">
                                <Icon name="truck" size={18} />
                                {loadSummary([dNext])}
                            </span>
                        </div>
                        {navLink(
                            dNext.site.latitude,
                            dNext.site.longitude,
                            "Navigasi",
                        )}
                    </Card>
                </>
            )}
            {showSend && showVisit && dp?.nextTrip && tripStatus && (
                <Card>
                    <div class="ui-meta ui-meta--between">
                        <span class="ui-kind">
                            <Icon name="truck" size={18} />
                            Pengiriman {dNext.id}
                        </span>
                        <Chip tone={tripStatus.tone}>{tripStatus.label}</Chip>
                    </div>
                    <CardHead
                        title={`${new Set(dp.nextTrip.tasks.map((t) => t.outlet_id)).size} toko · ${loadSummary(dp.nextTrip.tasks)}`}
                    />
                    <span class="ui-row__sub">{dp.nextTrip.name}</span>
                </Card>
            )}
            {(showVisit || showSend) && (
                <div class="ui-home__actions">
                    {showVisit && (
                        <Button onClick={() => onOpenVisit(next.id)}>
                            {showSend
                                ? "Mulai kunjungan"
                                : `Mulai kunjungan · ${next.name}`}
                        </Button>
                    )}
                    {showSend && (
                        <Button
                            variant={showVisit ? "sec" : "pri"}
                            icon={showVisit ? undefined : "truck"}
                            onClick={onDelivery}
                        >
                            {showVisit ? "Mulai kirim" : "Mulai pengiriman"}
                        </Button>
                    )}
                </div>
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
