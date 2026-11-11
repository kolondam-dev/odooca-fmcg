import { useState } from "preact/hooks";
import type { Snapshot } from "../domain/contracts";
import {
    FIELD_EXPENSE_V2_UNSUPPORTED,
    fieldExpenseV2Enabled,
    validateExpense,
} from "../domain/expense";
import { money } from "../domain/format";
import type { FieldStore } from "../storage/store";
import {
    Button,
    Callout,
    Card,
    Field,
    Screen,
    ScreenHeader,
    Segmented,
    Textarea,
} from "../ui";
import { useBackLayer } from "../ui/navigation";
import { EvidenceCapture, type EvidenceRef } from "./Evidence";

/** Kategori mockup (Ajukan_uang) → kategori kontrak. */
export const EXPENSE_KINDS = [
    { value: "fuel", label: "BBM" },
    { value: "meal", label: "Makan" },
    { value: "lodging", label: "Nginap" },
    { value: "emergency", label: "Darurat" },
] as const;

/** Layar penuh Ajukan uang lapangan (DS: Ajukan_uang). */
export function AjukanUangScreen({
    snapshot,
    businessDate,
    owner,
    store,
    trip,
    submit,
    close,
}: {
    snapshot: Snapshot;
    businessDate: string;
    owner: string;
    store: FieldStore;
    trip?: string;
    submit: (
        type: "field_expense.request",
        payload: Record<string, unknown>,
        label: string,
    ) => Promise<unknown>;
    close: () => void;
}) {
    useBackLayer(true, close);
    const [kind, setKind] =
        useState<(typeof EXPENSE_KINDS)[number]["value"]>("fuel");
    const [amount, setAmount] = useState("");
    const [reason, setReason] = useState("");
    const [evidence, setEvidence] = useState<EvidenceRef>();
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const tripId =
        trip ?? snapshot.deliveries[0]?.trip ?? `FIELD-${businessDate}`;
    const supported = fieldExpenseV2Enabled(snapshot);
    async function send() {
        if (busy) return;
        setError("");
        if (!supported) {
            setError(FIELD_EXPENSE_V2_UNSUPPORTED);
            return;
        }
        const n = Number(amount);
        if (!Number.isInteger(n) || n < 1) {
            setError("Nominal harus bilangan bulat rupiah lebih dari nol.");
            return;
        }
        setBusy(true);
        try {
            const payload = validateExpense(
                {
                    category: kind,
                    amount: String(n),
                    expense_scope: "trip",
                    trip_id: tripId,
                    delivery_id: null,
                    scheduled_date: businessDate,
                    odometer: null,
                    reason: reason.trim(),
                    evidence: evidence ?? null,
                },
                businessDate,
            );
            await submit(
                "field_expense.request",
                payload,
                `Petty cash • ${money(n)}`,
            );
            close();
        } catch (e) {
            setError(e instanceof Error ? e.message : "Gagal menyimpan.");
        } finally {
            setBusy(false);
        }
    }
    return (
        <Screen
            label="Ajukan uang lapangan"
            class="ui-screen--over ui-screen--top"
            header={
                <ScreenHeader title="Ajukan uang lapangan" onBack={close} />
            }
            footer={
                <Button
                    icon="check"
                    disabled={busy || !supported}
                    onClick={() => void send()}
                >
                    {busy ? "Menyimpan…" : "Kirim pengajuan"}
                </Button>
            }
        >
            <Segmented
                label="Kategori"
                value={kind}
                onChange={(v) => setKind(v as typeof kind)}
                items={EXPENSE_KINDS.map((k) => ({
                    value: k.value,
                    label: k.label,
                }))}
            />
            <Field
                label="Nominal"
                value={amount}
                inputMode="numeric"
                placeholder="Rp 150.000"
                maxLength={9}
                onInput={(v) => setAmount(v.replace(/\D/g, ""))}
                hint={amount ? money(Number(amount)) : undefined}
            />
            <Textarea
                label="Keterangan"
                value={reason}
                onInput={setReason}
                required
                maxLength={500}
                placeholder="Contoh: Isi BBM rute Wenang"
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
                    {FIELD_EXPENSE_V2_UNSUPPORTED}
                </Callout>
            )}
            <Callout tone="info">
                Foto nota opsional. Pengajuan menunggu approval supervisor; di
                atas limit kewenangan diteruskan ke Branch Manager.
            </Callout>
            {error ? (
                <Callout tone="bad" alert>
                    {error}
                </Callout>
            ) : null}
        </Screen>
    );
}
