import { useEffect, useState } from "preact/hooks";
import type { Snapshot } from "../domain/contracts";
import {
    OUTLET_EXPENSE_UNSUPPORTED,
    outletExpenseEnabled,
    validateExpense,
} from "../domain/expense";
import { money } from "../domain/format";
import {
    isStoreBatch,
    storeBatchKey,
    submitPending,
    type StoreBatch,
} from "../domain/outlet-expense";
import type { FieldStore } from "../storage/store";
import {
    Button,
    Callout,
    Card,
    Chip,
    Field,
    Screen,
    ScreenHeader,
} from "../ui";
import { useBackLayer } from "../ui/navigation";
import { EvidenceCapture, type EvidenceRef } from "./Evidence";

const PARTS = [
    { key: "store_parking", label: "Parkir" },
    { key: "store_unloading", label: "Kuli bongkar" },
    { key: "store_levy", label: "Retribusi" },
    { key: "store_other", label: "Lainnya" },
] as const;
type PartKey = (typeof PARTS)[number]["key"];
const EMPTY: Record<PartKey, string> = {
    store_parking: "",
    store_unloading: "",
    store_levy: "",
    store_other: "",
};

/** Penyerahan perintah ke antrean (App.submit), dipakai Biaya toko dari layar mana pun. */
export type ExpenseSubmit = (
    type: "field_expense.request",
    payload: Record<string, unknown>,
    label: string,
    keepOpen?: boolean,
    uuid?: string,
) => Promise<unknown>;

/**
 * Layar penuh Biaya operasional toko (DS: Biaya_toko). Satu `field_expense.request` scope outlet per
 * komponen terisi. Rencana batch (UUID tetap per komponen) disimpan di draft lokal sebelum kirim, sehingga
 * kegagalan di tengah, tutup formulir, atau muat ulang tidak menggandakan komponen yang sudah masuk antrean.
 */
export function BiayaTokoScreen({
    snapshot,
    outlet,
    businessDate,
    owner,
    store,
    submit,
    close,
}: {
    snapshot: Snapshot;
    outlet: { id: string; name: string };
    businessDate: string;
    owner: string;
    store: FieldStore;
    submit: ExpenseSubmit;
    close: () => void;
}) {
    useBackLayer(true, close);
    const [amounts, setAmounts] = useState<Record<PartKey, string>>(EMPTY);
    const [otherNote, setOtherNote] = useState("");
    const [evidence, setEvidence] = useState<EvidenceRef>();
    /** Rencana batch yang sudah dikunci: input read-only, retry memakai UUID yang sama. */
    const [batch, setBatch] = useState<StoreBatch>();
    const [ready, setReady] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const supported = outletExpenseEnabled(snapshot);
    const draftKey = storeBatchKey(outlet.id, businessDate);
    const tripId = snapshot.deliveries[0]?.trip ?? `FIELD-${businessDate}`;
    useEffect(() => {
        let active = true;
        void store.draft(owner, draftKey).then((value) => {
            if (!active) return;
            if (isStoreBatch(value)) {
                const next = { ...EMPTY };
                for (const item of value.items)
                    next[item.key as PartKey] = String(item.payload.amount);
                setAmounts(next);
                const other = value.items.find((i) => i.key === "store_other");
                if (other) setOtherNote(String(other.payload.reason ?? ""));
                setBatch(value);
            }
            setReady(true);
        });
        return () => {
            active = false;
        };
    }, [store, owner, draftKey]);
    const total = PARTS.reduce((a, p) => a + Number(amounts[p.key] || 0), 0);
    async function send() {
        if (busy || !ready) return;
        setError("");
        if (!supported) {
            setError(OUTLET_EXPENSE_UNSUPPORTED);
            return;
        }
        setBusy(true);
        try {
            let plan = batch;
            if (!plan) {
                const filled = PARTS.filter((p) => Number(amounts[p.key]) > 0);
                if (!filled.length) {
                    setError("Isi nominal minimal satu komponen biaya.");
                    return;
                }
                if (amounts.store_other && !otherNote.trim()) {
                    setError("Keterangan lainnya wajib diisi.");
                    return;
                }
                plan = {
                    batch_id: crypto.randomUUID(),
                    items: filled.map((p) => {
                        const payload = validateExpense(
                            {
                                category: p.key,
                                amount: String(Number(amounts[p.key])),
                                expense_scope: "outlet",
                                trip_id: tripId,
                                delivery_id: null,
                                outlet_id: outlet.id,
                                scheduled_date: businessDate,
                                odometer: null,
                                reason:
                                    p.key === "store_other"
                                        ? otherNote.trim()
                                        : `${p.label} • ${outlet.name}`,
                                evidence: evidence ?? null,
                            },
                            businessDate,
                        );
                        return {
                            key: p.key,
                            uuid: crypto.randomUUID(),
                            payload,
                            label: `Biaya toko • ${outlet.name} • ${money(Number(payload.amount))}`,
                        };
                    }),
                };
                // Rencana disimpan SEBELUM kirim: buka ulang/muat ulang melanjutkan UUID yang sama.
                await store.draft(owner, draftKey, plan);
                setBatch(plan);
            }
            const queued = new Set(
                (await store.list(owner)).map((q) => q.command.client_uuid),
            );
            await submitPending(plan.items, queued, async (item, last) => {
                await submit(
                    "field_expense.request",
                    item.payload,
                    item.label,
                    !last,
                    item.uuid,
                );
            });
            await store.removeDraft(owner, draftKey);
            close();
        } catch (e) {
            setError(e instanceof Error ? e.message : "Gagal menyimpan.");
        } finally {
            setBusy(false);
        }
    }
    const locked = !!batch;
    return (
        <Screen
            label="Biaya toko"
            class="ui-screen--over ui-screen--top"
            header={
                <ScreenHeader title={`Biaya · ${outlet.name}`} onBack={close} />
            }
            footer={
                <Button
                    icon="check"
                    disabled={busy || !supported || !ready}
                    onClick={() => void send()}
                >
                    {busy
                        ? "Menyimpan…"
                        : locked
                          ? "Lanjutkan simpan biaya"
                          : `Simpan biaya · ${money(total)}`}
                </Button>
            }
        >
            <Chip tone="neu">Scope: toko</Chip>
            {locked ? (
                <Callout tone="warn">
                    Penyimpanan sebelumnya belum selesai. Isian dikunci; tekan
                    Lanjutkan agar komponen yang tersisa disimpan tanpa
                    menggandakan yang sudah masuk antrean.
                </Callout>
            ) : null}
            {PARTS.map((p) => (
                <Field
                    key={p.key}
                    label={p.label}
                    value={amounts[p.key]}
                    inputMode="numeric"
                    maxLength={9}
                    placeholder="Rp 0"
                    readOnly={locked}
                    onInput={(v) =>
                        setAmounts({
                            ...amounts,
                            [p.key]: v.replace(/\D/g, ""),
                        })
                    }
                    hint={
                        amounts[p.key]
                            ? money(Number(amounts[p.key]))
                            : undefined
                    }
                />
            ))}
            <Field
                label="Keterangan lainnya (wajib)"
                value={otherNote}
                maxLength={500}
                readOnly={locked}
                onInput={setOtherNote}
            />
            {!locked ? (
                <Card>
                    <EvidenceCapture
                        store={store}
                        owner={owner}
                        onChange={setEvidence}
                    />
                </Card>
            ) : null}
            {!supported && (
                <Callout tone="warn" alert>
                    {OUTLET_EXPENSE_UNSUPPORTED}
                </Callout>
            )}
            {error ? (
                <Callout tone="bad" alert>
                    {error}
                </Callout>
            ) : null}
        </Screen>
    );
}
