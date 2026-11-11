import { useRef, useState } from "preact/hooks";
import { submitPending } from "../domain/outlet-expense";
import type { Snapshot } from "../domain/contracts";
import {
    OUTLET_EXPENSE_UNSUPPORTED,
    outletExpenseEnabled,
    validateExpense,
} from "../domain/expense";
import { money } from "../domain/format";
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

/** Layar penuh Biaya operasional toko (DS: Biaya_toko). Satu pengajuan `field_expense.request` scope outlet per komponen terisi. */
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
    submit: (
        type: "field_expense.request",
        payload: Record<string, unknown>,
        label: string,
        keepOpen?: boolean,
    ) => Promise<unknown>;
    close: () => void;
}) {
    useBackLayer(true, close);
    const [amounts, setAmounts] = useState<Record<PartKey, string>>({
        store_parking: "",
        store_unloading: "",
        store_levy: "",
        store_other: "",
    });
    const [otherNote, setOtherNote] = useState("");
    const [evidence, setEvidence] = useState<EvidenceRef>();
    /** Komponen yang sudah masuk antrean: retry setelah gagal tidak menggandakannya. */
    const saved = useRef(new Set<string>());
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const supported = outletExpenseEnabled(snapshot);
    const total = PARTS.reduce((a, p) => a + Number(amounts[p.key] || 0), 0);
    const tripId = snapshot.deliveries[0]?.trip ?? `FIELD-${businessDate}`;
    async function send() {
        if (busy) return;
        setError("");
        if (!supported) {
            setError(OUTLET_EXPENSE_UNSUPPORTED);
            return;
        }
        const filled = PARTS.filter((p) => Number(amounts[p.key]) > 0);
        if (!filled.length) {
            setError("Isi nominal minimal satu komponen biaya.");
            return;
        }
        if (
            amounts.store_other &&
            Number(amounts.store_other) > 0 &&
            !otherNote.trim()
        ) {
            setError("Keterangan lainnya wajib diisi.");
            return;
        }
        setBusy(true);
        try {
            const items = filled.map((p) => ({
                key: p.key,
                payload: validateExpense(
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
                ),
            }));
            await submitPending(items, saved.current, async (item, last) => {
                await submit(
                    "field_expense.request",
                    item.payload,
                    `Biaya toko • ${outlet.name} • ${money(Number(item.payload.amount))}`,
                    !last,
                );
            });
            close();
        } catch (e) {
            setError(e instanceof Error ? e.message : "Gagal menyimpan.");
        } finally {
            setBusy(false);
        }
    }
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
                    disabled={busy || !supported}
                    onClick={() => void send()}
                >
                    {busy ? "Menyimpan…" : `Simpan biaya · ${money(total)}`}
                </Button>
            }
        >
            <Chip tone="neu">Scope: toko</Chip>
            {PARTS.map((p) => (
                <Field
                    key={p.key}
                    label={p.label}
                    value={amounts[p.key]}
                    inputMode="numeric"
                    maxLength={9}
                    placeholder="Rp 0"
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
                onInput={setOtherNote}
            />
            <Card>
                <EvidenceCapture
                    store={store}
                    owner={owner}
                    onChange={setEvidence}
                />
            </Card>
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
