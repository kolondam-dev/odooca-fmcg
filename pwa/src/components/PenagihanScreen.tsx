import { useState } from "preact/hooks";
import type { CollectionTask } from "../domain/collection-contracts";
import {
    COLLECTION_V2_UNSUPPORTED,
    CollectionSettlementSchema,
    UnpaidReasonSchema,
    collectionV2Enabled,
    settledReceivables,
} from "../domain/collection-settlement";
import { normalizedReference } from "../domain/collection-contracts";
import { money } from "../domain/format";
import type { Snapshot } from "../domain/contracts";
import type { FieldStore, QueueItem } from "../storage/store";
import {
    Button,
    Callout,
    Card,
    Checkbox,
    Field,
    Screen,
    ScreenHeader,
    Segmented,
    Select,
} from "../ui";
import { useBackLayer } from "../ui/navigation";
import { EvidenceCapture, type EvidenceRef } from "./Evidence";

type Method = "cash" | "transfer" | "giro";
const REASONS = UnpaidReasonSchema.options.map((v) => ({
    value: v,
    label: v,
}));
type Row = { on: boolean; amount: string; reason: string; promise: string };

/**
 * Penagihan satu toko (DS: Penagihan_toko, Penagihan_bukti, Tidak_tertagih).
 * Satu bukti dapat melunasi banyak faktur; faktur yang dibayar sebagian wajib alasan sisa + janji bayar.
 * Dikirim sebagai satu perintah `collection.settlement.submit`; terkunci bila server belum mendukung.
 */
export function PenagihanScreen({
    outlet,
    tripId,
    businessDate,
    receivables,
    owner,
    store,
    queue,
    snapshot,
    submit,
    close,
}: {
    outlet: { id: string; name: string };
    tripId: string;
    businessDate: string;
    receivables: CollectionTask[];
    owner: string;
    store: FieldStore;
    queue: QueueItem[];
    snapshot: Pick<Snapshot, "features">;
    submit: (
        type: "collection.settlement.submit",
        payload: Record<string, unknown>,
        label: string,
        keepOpen?: boolean,
    ) => Promise<unknown>;
    close: () => void;
}) {
    useBackLayer(true, close);
    const settled = settledReceivables(queue);
    const open = receivables.filter(
        (r) => !settled.has(normalizedReference(r.receivable_reference)),
    );
    const [rows, setRows] = useState<Record<string, Row>>(() =>
        Object.fromEntries(
            open.map((r) => [
                r.receivable_reference,
                { on: true, amount: r.amount_due, reason: "", promise: "" },
            ]),
        ),
    );
    const [method, setMethod] = useState<Method>("cash");
    const [payer, setPayer] = useState("");
    const [receipt, setReceipt] = useState("");
    const [transferRef, setTransferRef] = useState("");
    const [notes, setNotes] = useState("");
    const [evidence, setEvidence] = useState<EvidenceRef>();
    const [step, setStep] = useState<"pilih" | "bukti">("pilih");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const supported = collectionV2Enabled(snapshot);
    const patch = (ref: string, p: Partial<Row>) =>
        setRows((prev) => ({ ...prev, [ref]: { ...prev[ref], ...p } }));
    const chosen = open.filter((r) => rows[r.receivable_reference]?.on);
    const total = chosen.reduce(
        (a, r) => a + Number(rows[r.receivable_reference].amount || 0),
        0,
    );
    const isPartial = (r: CollectionTask) =>
        BigInt(rows[r.receivable_reference]?.amount || "0") <
        BigInt(r.amount_due);

    function toBukti() {
        setError("");
        if (!chosen.length) {
            setError("Pilih minimal satu faktur.");
            return;
        }
        for (const r of chosen) {
            const row = rows[r.receivable_reference];
            if (!/^[1-9]\d{0,11}$/.test(row.amount)) {
                setError(
                    `Nominal ${r.receivable_reference} harus rupiah bulat lebih dari nol.`,
                );
                return;
            }
            if (isPartial(r) && (!row.reason || !row.promise)) {
                setError(
                    `${r.receivable_reference}: isi alasan sisa tidak tertagih dan janji bayar.`,
                );
                return;
            }
        }
        setStep("bukti");
    }
    async function send() {
        if (busy) return;
        setError("");
        if (!supported) {
            setError(COLLECTION_V2_UNSUPPORTED);
            return;
        }
        const parsed = CollectionSettlementSchema.safeParse({
            settlement_version: 1,
            outlet_id: outlet.id,
            outlet: outlet.name,
            trip_id: tripId,
            business_date: businessDate,
            method: method === "giro" ? "cash" : method,
            payer: payer.trim(),
            receipt_number: receipt.trim(),
            ...(method === "transfer"
                ? { transfer_reference: transferRef.trim() }
                : {}),
            notes: notes.trim(),
            evidence,
            allocations: chosen.map((r) => ({
                receivable_reference: r.receivable_reference,
                amount_due: r.amount_due,
                amount: rows[r.receivable_reference].amount,
            })),
            remainders: chosen.filter(isPartial).map((r) => ({
                receivable_reference: r.receivable_reference,
                reason: rows[r.receivable_reference].reason,
                promise_date: rows[r.receivable_reference].promise,
            })),
        });
        if (!parsed.success) {
            const p = parsed.error.issues[0]?.path[0];
            setError(
                p === "evidence"
                    ? "Foto bukti wajib disimpan dahulu."
                    : p === "payer"
                      ? "Nama pembayar wajib diisi."
                      : p === "receipt_number"
                        ? "Nomor tanda terima wajib diisi."
                        : p === "transfer_reference"
                          ? "Referensi transfer wajib untuk pembayaran transfer."
                          : (parsed.error.issues[0]?.message ??
                            "Data belum lengkap."),
            );
            return;
        }
        setBusy(true);
        try {
            await submit(
                "collection.settlement.submit",
                parsed.data,
                `Penagihan • ${outlet.name} • ${money(total)}`,
            );
            close();
        } catch (e) {
            setError(e instanceof Error ? e.message : "Gagal menyimpan.");
        } finally {
            setBusy(false);
        }
    }

    const warn = !supported ? (
        <Callout tone="warn" alert>
            {COLLECTION_V2_UNSUPPORTED}
        </Callout>
    ) : null;
    const err = error ? (
        <Callout tone="bad" alert>
            {error}
        </Callout>
    ) : null;

    if (!open.length)
        return (
            <Screen
                label={`Penagihan ${outlet.name}`}
                class="ui-screen--over ui-screen--top"
                header={<ScreenHeader title="Penagihan" onBack={close} />}
            >
                <Callout tone="info">
                    Semua tagihan {outlet.name} sudah dicatat.
                </Callout>
            </Screen>
        );

    return (
        <>
            <Screen
                label={`Penagihan ${outlet.name}`}
                class="ui-screen--over ui-screen--top"
                header={
                    <ScreenHeader
                        title={`Penagihan · ${outlet.name}`}
                        onBack={close}
                    />
                }
                footer={
                    <Button icon="arrow" onClick={toBukti}>
                        Lanjut ke bukti · {money(total)}
                    </Button>
                }
            >
                {warn}
                <Card>
                    <span class="exp-saldo__label">Faktur belum tertagih</span>
                    {open.map((r) => {
                        const ref = r.receivable_reference;
                        const row = rows[ref];
                        return (
                            <div key={ref}>
                                <Checkbox
                                    checked={row.on}
                                    onChange={(on) => patch(ref, { on })}
                                >
                                    {ref} · saldo {money(Number(r.amount_due))}
                                </Checkbox>
                                {row.on ? (
                                    <>
                                        <Field
                                            label={`Nominal ${ref}`}
                                            value={row.amount}
                                            inputMode="numeric"
                                            maxLength={12}
                                            onInput={(v) =>
                                                patch(ref, {
                                                    amount: v.replace(
                                                        /\D/g,
                                                        "",
                                                    ),
                                                })
                                            }
                                            hint={
                                                row.amount
                                                    ? money(Number(row.amount))
                                                    : undefined
                                            }
                                        />
                                        {isPartial(r) ? (
                                            <>
                                                <Select
                                                    label={`Alasan sisa ${ref}`}
                                                    placeholder="Pilih alasan"
                                                    options={REASONS}
                                                    value={row.reason}
                                                    onChange={(v) =>
                                                        patch(ref, {
                                                            reason: v,
                                                        })
                                                    }
                                                />
                                                <Field
                                                    label={`Janji bayar ${ref}`}
                                                    type="date"
                                                    value={row.promise}
                                                    onInput={(v) =>
                                                        patch(ref, {
                                                            promise: v,
                                                        })
                                                    }
                                                />
                                            </>
                                        ) : null}
                                    </>
                                ) : null}
                            </div>
                        );
                    })}
                </Card>
                {err}
            </Screen>
            {step === "bukti" ? (
                <BuktiStep
                    {...{
                        method,
                        setMethod,
                        payer,
                        setPayer,
                        receipt,
                        setReceipt,
                        transferRef,
                        setTransferRef,
                        notes,
                        setNotes,
                        store,
                        owner,
                        setEvidence,
                        busy,
                        supported,
                        total,
                        warn,
                        err,
                    }}
                    back={() => setStep("pilih")}
                    send={() => void send()}
                />
            ) : null}
        </>
    );
}

function BuktiStep(p: {
    method: Method;
    setMethod: (m: Method) => void;
    payer: string;
    setPayer: (v: string) => void;
    receipt: string;
    setReceipt: (v: string) => void;
    transferRef: string;
    setTransferRef: (v: string) => void;
    notes: string;
    setNotes: (v: string) => void;
    store: FieldStore;
    owner: string;
    setEvidence: (e?: EvidenceRef) => void;
    busy: boolean;
    supported: boolean;
    total: number;
    warn: preact.ComponentChildren;
    err: preact.ComponentChildren;
    back: () => void;
    send: () => void;
}) {
    useBackLayer(true, p.back);
    return (
        <Screen
            label="Bukti penagihan"
            class="ui-screen--over ui-screen--top"
            header={<ScreenHeader title="Bukti penagihan" onBack={p.back} />}
            footer={
                <Button
                    icon="check"
                    disabled={p.busy || !p.supported}
                    onClick={p.send}
                >
                    {p.busy
                        ? "Menyimpan…"
                        : `Simpan penagihan · ${money(p.total)}`}
                </Button>
            }
        >
            <Segmented<Method>
                label="Metode bayar"
                value={p.method}
                onChange={p.setMethod}
                items={[
                    { value: "cash", label: "Tunai" },
                    { value: "transfer", label: "Transfer" },
                    { value: "giro", label: "Giro", disabled: true },
                ]}
            />
            <Field
                label="Nama pembayar"
                value={p.payer}
                maxLength={100}
                onInput={p.setPayer}
            />
            <Field
                label="Nomor tanda terima"
                value={p.receipt}
                maxLength={80}
                onInput={p.setReceipt}
            />
            {p.method === "transfer" ? (
                <Field
                    label="Referensi transfer"
                    value={p.transferRef}
                    maxLength={80}
                    onInput={p.setTransferRef}
                />
            ) : null}
            <Field
                label="Catatan (opsional)"
                value={p.notes}
                maxLength={500}
                onInput={p.setNotes}
            />
            <Card>
                <EvidenceCapture
                    store={p.store}
                    owner={p.owner}
                    onChange={p.setEvidence}
                />
            </Card>
            {p.warn}
            {p.err}
        </Screen>
    );
}
