import { useState } from "preact/hooks";
import type { Snapshot } from "../domain/contracts";
import {
    CASH_DEPOSIT_UNSUPPORTED,
    CashDepositSchema,
    cashDepositEnabled,
} from "../domain/cash-deposit";
import { money } from "../domain/format";
import type { FieldStore } from "../storage/store";
import { Button, Callout, Card, Field, Screen, ScreenHeader } from "../ui";
import { useBackLayer } from "../ui/navigation";
import { EvidenceCapture, type EvidenceRef } from "./Evidence";

/** Layar penuh Setor uang ke kasir (DS: Setor_uang). Tombol kirim terkunci sampai server menyatakan dukungan. */
export function SetorUangScreen({
    snapshot,
    trip,
    businessDate,
    owner,
    store,
    cash,
    transfer,
    receiptUuids,
    submit,
    close,
}: {
    snapshot: Pick<Snapshot, "features">;
    trip: string;
    businessDate: string;
    owner: string;
    store: FieldStore;
    cash: number;
    transfer: number;
    receiptUuids: string[];
    submit: (
        type: "delivery.cash_deposit.submit",
        payload: Record<string, unknown>,
        label: string,
        keepOpen?: boolean,
    ) => Promise<unknown>;
    close: () => void;
}) {
    useBackLayer(true, close);
    const [deposited, setDeposited] = useState(cash > 0 ? String(cash) : "");
    const [note, setNote] = useState("");
    const [evidence, setEvidence] = useState<EvidenceRef>();
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const supported = cashDepositEnabled(snapshot);
    async function send() {
        if (busy) return;
        setError("");
        if (!supported) {
            setError(CASH_DEPOSIT_UNSUPPORTED);
            return;
        }
        const parsed = CashDepositSchema.safeParse({
            deposit_version: 1,
            trip_id: trip,
            business_date: businessDate,
            cash_expected: String(cash),
            cash_deposited: deposited,
            ...(note.trim() ? { difference_note: note.trim() } : {}),
            receipt_uuids: receiptUuids,
            evidence,
        });
        if (!parsed.success) {
            const first = parsed.error.issues[0];
            setError(
                first?.path[0] === "evidence" ||
                    first?.path[0] === "difference_note"
                    ? first.message
                    : "Tunai disetor harus bilangan bulat rupiah lebih dari nol.",
            );
            return;
        }
        setBusy(true);
        try {
            await submit(
                "delivery.cash_deposit.submit",
                parsed.data,
                `Setor uang • ${trip} • ${money(Number(deposited))}`,
            );
            close();
        } catch (e) {
            setError(e instanceof Error ? e.message : "Gagal menyimpan.");
        } finally {
            setBusy(false);
        }
    }
    const diff = Number(deposited || 0) - cash;
    return (
        <Screen
            label="Setor uang"
            class="ui-screen--over ui-screen--top"
            header={<ScreenHeader title="Setor uang" onBack={close} />}
            footer={
                <Button
                    icon="check"
                    disabled={busy || !supported}
                    onClick={() => void send()}
                >
                    {busy ? "Menyimpan…" : "Simpan setoran"}
                </Button>
            }
        >
            <Card>
                <span class="exp-saldo__label">
                    Penerimaan uang trip {trip}
                </span>
                <strong class="exp-saldo__amt">{money(cash + transfer)}</strong>
                <div class="ui-kv">
                    <span>Tunai</span>
                    <strong>{money(cash)}</strong>
                </div>
                <div class="ui-kv">
                    <span>Transfer (sudah masuk rekening)</span>
                    <strong>{money(transfer)}</strong>
                </div>
            </Card>
            <Field
                label="Tunai disetor"
                value={deposited}
                inputMode="numeric"
                maxLength={12}
                onInput={(v) => setDeposited(v.replace(/\D/g, ""))}
                hint={deposited ? money(Number(deposited)) : undefined}
            />
            <Field
                label="Catatan selisih (bila ada)"
                value={note}
                maxLength={500}
                onInput={setNote}
                hint={
                    deposited && diff !== 0
                        ? `Selisih ${money(Math.abs(diff))} ${diff < 0 ? "kurang" : "lebih"} dari penerimaan tunai`
                        : undefined
                }
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
                    {CASH_DEPOSIT_UNSUPPORTED}
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
