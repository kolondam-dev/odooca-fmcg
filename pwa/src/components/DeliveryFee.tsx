import { useEffect, useRef, useState } from "preact/hooks";
import type { DeliveryTask } from "../domain/delivery-contracts";
import type { FieldStore } from "../storage/store";
import type { Outbox } from "../domain/outbox";
import { validateExpense } from "../domain/expense";
export function DeliveryFee({
    task,
    scope,
    store,
    owner,
    engine,
    changed,
}: {
    task: DeliveryTask;
    scope: "delivery" | "outlet";
    store: FieldStore;
    owner: string;
    engine: Outbox;
    changed: () => void;
}) {
    const source = JSON.stringify([
        task.trip,
        task.business_date,
        scope,
        scope === "delivery" ? task.id : task.outlet_id,
    ]);
    const key = `delivery-fee-v1:${source}`;
    const formKey = `${key}:form`,
        requestKey = `${key}:request`;
    const [amount, setAmount] = useState(""),
        [note, setNote] = useState(""),
        [sent, setSent] = useState(false),
        [ready, setReady] = useState(false),
        [busy, setBusy] = useState(false),
        [error, setError] = useState("");
    const running = useRef(false);
    useEffect(() => {
        let active = true;
        void Promise.all([
            store.draft(owner, formKey),
            store.draft(owner, requestKey),
        ])
            .then(([draft, request]) => {
                const raw = request ?? draft;
                if (!active) return;
                const value = raw as
                    | {
                          source?: string;
                          amount?: string;
                          note?: string;
                          client_uuid?: string;
                      }
                    | undefined;
                if (value && value.source !== source)
                    throw new Error("Scope biaya berubah; perlu review.");
                setAmount(value?.amount ?? "");
                setNote(value?.note ?? "");
                setSent(!!value?.client_uuid);
                setReady(true);
            })
            .catch((e) => {
                if (active) setError(e.message);
            });
        return () => {
            active = false;
        };
    }, [key, owner]);
    useEffect(() => {
        if (ready && !sent && !busy)
            void store
                .draft(owner, formKey, { source, amount, note })
                .catch(() => setError("Draft biaya gagal disimpan."));
    }, [ready, sent, amount, note]);
    async function send() {
        if (running.current) return;
        running.current = true;
        setBusy(true);
        setError("");
        try {
            const value = validateExpense(
                {
                    category: "delivery_fee",
                    amount,
                    expense_scope: scope,
                    trip_id: task.trip,
                    delivery_id: scope === "delivery" ? task.id : null,
                    ...(scope === "outlet"
                        ? { outlet_id: task.outlet_id }
                        : {}),
                    scheduled_date: task.business_date,
                    odometer: null,
                    reason: note,
                    evidence: null,
                },
                task.business_date,
            );
            const current = (await store.draft(owner, requestKey)) as
                | { client_uuid?: string }
                | undefined;
            if (current?.client_uuid) {
                setSent(true);
                throw new Error(
                    "Biaya sudah diajukan; periksa approval di Lainnya.",
                );
            }
            const id = crypto.randomUUID();
            await engine.enqueue(
                "field_expense.request",
                value,
                `Biaya ${scope === "delivery" ? task.id : task.outlet}`,
                id,
                {
                    key: requestKey,
                    value: { source, amount, note, client_uuid: id },
                    expected: undefined,
                },
            );
            setSent(true);
            changed();
            if (navigator.onLine) void engine.flush();
        } catch (e) {
            setError(e instanceof Error ? e.message : "Biaya gagal diajukan.");
        } finally {
            running.current = false;
            setBusy(false);
        }
    }
    return (
        <fieldset class="delivery-fee" disabled={!ready || busy || sent}>
            <legend>{scope === "delivery" ? "Biaya DO" : "Biaya toko"}</legend>
            <label>
                Nominal {scope === "delivery" ? "DO" : "toko"} (Rp)
                <input
                    inputMode="numeric"
                    value={amount}
                    onInput={(e) => setAmount(e.currentTarget.value)}
                />
            </label>
            <label>
                Catatan biaya {scope === "delivery" ? "DO" : "toko"}
                <input
                    value={note}
                    maxLength={500}
                    onInput={(e) => setNote(e.currentTarget.value)}
                />
            </label>
            <button
                type="button"
                class="secondary"
                onClick={() => void send()}
                disabled={!amount || !note.trim()}
            >
                {sent ? "Biaya diajukan • menunggu approval" : "Ajukan biaya"}
            </button>
            {error && <p role="alert">{error}</p>}
        </fieldset>
    );
}
