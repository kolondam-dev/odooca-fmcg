import { useEffect, useRef } from "preact/hooks";
import { money } from "../domain/format";
import type { QueueItem } from "../storage/store";
import { Button, Card, Screen } from "../ui";
import { Icon } from "./Icon";

type StepState = "done" | "active" | "wait" | "bad";

function Step({
    state,
    title,
    sub,
}: {
    state: StepState;
    title: string;
    sub: string;
}) {
    return (
        <li class={`pos-step is-${state}`}>
            <span class="pos-step__icon" aria-hidden="true">
                <Icon
                    name={
                        state === "done"
                            ? "check"
                            : state === "active"
                              ? "sync"
                              : state === "bad"
                                ? "warning"
                                : "clock"
                    }
                    size={22}
                />
            </span>
            <span class="pos-step__body">
                <strong>{title}</strong>
                <span class="ui-row__sub">{sub}</span>
            </span>
        </li>
    );
}

const wita = (date = new Date()) =>
    new Intl.DateTimeFormat("id-ID", {
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Asia/Makassar",
        hourCycle: "h23",
    })
        .format(date)
        .replace(":", ".") + " WITA";

/** Layar "Order tersimpan" (DS: Hasil_kirim); status mengikuti item antrean. */
export function OrderResult({
    item,
    outletName,
    total,
    skuCount,
    approvalReasons,
    close,
    finishVisit,
}: {
    item: QueueItem;
    outletName: string;
    total: number;
    skuCount: number;
    approvalReasons: string[];
    close: () => void;
    finishVisit: () => void;
}) {
    const savedAt = useRef(wita());
    const heading = useRef<HTMLHeadingElement>(null);
    useEffect(() => heading.current?.focus(), []);
    const receipt = item.receipt;
    const rejected =
        receipt?.status === "rejected" || item.state === "rejected";
    const sent =
        !!receipt ||
        ["accepted", "needs_approval", "rejected"].includes(item.state);
    // Status approval hanya dari receipt/antrean server; alasan lokal hanyalah indikasi.
    const needsApproval =
        receipt?.status === "needs_approval" || item.state === "needs_approval";
    const expectApproval = !sent && approvalReasons.length > 0;
    return (
        <Screen
            label="Hasil kirim order"
            class="ui-screen--over"
            header={
                <header class="ui-hdr">
                    <h1 class="ui-hdr__title">Order tersimpan</h1>
                </header>
            }
            footer={
                <>
                    <Button onClick={finishVisit}>
                        Lanjut ke selesai kunjungan
                    </Button>
                    <Button variant="sec" onClick={close}>
                        Lihat order
                    </Button>
                </>
            }
        >
            <div class="pos-done">
                <span
                    class={`pos-done__badge${rejected ? " is-bad" : ""}`}
                    aria-hidden="true"
                >
                    <Icon name={rejected ? "warning" : "check"} size={44} />
                </span>
                <h2 ref={heading} tabIndex={-1} class="pos-done__title">
                    {rejected ? "Order ditolak" : "Order tersimpan"}
                </h2>
                <p class="ui-row__sub">
                    {money(total)} · {skuCount} SKU · {outletName}
                </p>
            </div>
            <Card>
                <ol class="pos-steps" aria-label="Status order">
                    <Step
                        state="done"
                        title="Tersimpan di perangkat"
                        sub={savedAt.current}
                    />
                    <Step
                        state={sent ? "done" : "active"}
                        title="Terkirim ke server"
                        sub={
                            sent
                                ? (receipt?.reference ?? "Diterima server")
                                : "Dikirim saat koneksi tersedia"
                        }
                    />
                    {needsApproval || expectApproval ? (
                        <Step
                            state={
                                rejected
                                    ? "bad"
                                    : needsApproval
                                      ? "active"
                                      : "wait"
                            }
                            title="Approval supervisor"
                            sub={
                                rejected
                                    ? (receipt?.message ?? "Ditolak")
                                    : needsApproval
                                      ? (receipt?.message ??
                                        (approvalReasons.length
                                            ? approvalReasons.join(" + ")
                                            : "Menunggu keputusan"))
                                      : `Kemungkinan perlu approval: ${approvalReasons.join(" + ")}`
                            }
                        />
                    ) : null}
                </ol>
            </Card>
            {needsApproval && !rejected ? (
                <Card>
                    <span class="ui-row__sub">
                        Order menunggu approval. Pantau statusnya di Antrean;
                        hubungi supervisor bila mendesak.
                    </span>
                </Card>
            ) : null}
        </Screen>
    );
}
