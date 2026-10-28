import { useEffect, useState } from "preact/hooks";
import { z } from "zod";
import {
    CollectionReceiptSchema,
    CollectionTaskSchema,
    collectionKey,
    type CollectionTask,
} from "../domain/collection-contracts";
import {
    validateCollection,
    validateCollectionMedia,
} from "../domain/collection";
import { assertLocalEvidence } from "../domain/evidence-package";
import { EvidenceCapture, type EvidenceRef } from "./Evidence";
import { Icon } from "./Icon";
import { money } from "../domain/format";
import {
    ownerKey,
    type Identity,
    type FieldProvider,
} from "../domain/contracts";
import type { FieldStore, QueueItem } from "../storage/store";
import type { Outbox } from "../domain/outbox";
export function CollectionWorkspace({
    identity,
    provider,
    store,
    engine,
    queue,
    changed,
}: {
    identity: Identity;
    provider: FieldProvider;
    store: FieldStore;
    engine: Outbox;
    queue: QueueItem[];
    changed: () => void;
}) {
    const owner = ownerKey(identity),
        key = `collection-manifest-v1:${identity.businessDate}`;
    const [tasks, setTasks] = useState<CollectionTask[]>(),
        [error, setError] = useState("");
    useEffect(() => {
        let active = true;
        void (async () => {
            if (!identity.capabilities?.includes("collection.capture"))
                throw new Error(
                    "Kewenangan pencatatan tagihan belum tersedia.",
                );
            let data = await store.draft(owner, key);
            if (data === undefined) {
                if (!navigator.onLine || !provider.collectionTasks)
                    throw new Error(
                        "Hubungkan jaringan untuk memuat penugasan tagihan contoh.",
                    );
                data = await store.createDraftIfAbsent(
                    owner,
                    key,
                    await provider.collectionTasks(),
                );
            }
            const parsed = z.array(CollectionTaskSchema).min(1).parse(data);
            if (
                parsed.some(
                    (s) =>
                        s.delivery.owner !== owner ||
                        s.delivery.business_date !== identity.businessDate,
                ) ||
                new Set(parsed.map(collectionKey)).size !== parsed.length
            )
                throw new Error("Penugasan collection tidak cocok.");
            if (active) setTasks(parsed);
        })().catch((e) => {
            if (active) setError(e.message);
        });
        return () => {
            active = false;
        };
    }, [owner, key]);
    if (!identity.capabilities?.includes("collection.capture")) return null;
    return (
        <section>
            <h2>Penerimaan uang · simulasi</h2>
            <p class="notice">
                Saldo tagihan contoh, bukan saldo piutang Odoo. Foto transfer
                belum diverifikasi bank. Satu pencatatan per tagihan; tidak
                memposting pembayaran atau melunasi piutang.
            </p>
            {error && <p role="alert">{error}</p>}
            {tasks?.map((task) => (
                <CollectionForm
                    key={JSON.stringify(task)}
                    {...{ task, store, engine, owner, queue, changed }}
                />
            ))}
        </section>
    );
}
function CollectionForm({
    task,
    store,
    engine,
    owner,
    queue,
    changed,
}: {
    task: CollectionTask;
    store: FieldStore;
    engine: Outbox;
    owner: string;
    queue: QueueItem[];
    changed: () => void;
}) {
    const key = collectionKey(task),
        draftKey = `${key}:form`;
    const [payer, setPayer] = useState(""),
        [amount, setAmount] = useState(""),
        [method, setMethod] = useState<"cash" | "transfer">("cash"),
        [receipt, setReceipt] = useState(""),
        [transfer, setTransfer] = useState(""),
        [notes, setNotes] = useState("");
    const [photo, setPhoto] = useState<EvidenceRef>(),
        [saved, setSaved] = useState<QueueItem>(),
        [ready, setReady] = useState(false),
        [busy, setBusy] = useState(false),
        [message, setMessage] = useState("");
    useEffect(() => {
        let active = true;
        void (async () => {
            const c = await store.draft(owner, key);
            if (c) {
                const row = (await store.list(owner)).find(
                    (r) =>
                        r.command.client_uuid ===
                        (c as { client_uuid: string }).client_uuid,
                );
                if (!row)
                    throw new Error("Antrean collection hilang. Perlu review.");
                await validateCollectionMedia(row, owner, store);
                if (
                    row.command.type !== "collection.receipt.submit" ||
                    JSON.stringify(row.command.payload.source) !==
                        JSON.stringify(task)
                )
                    throw new Error(
                        "Tagihan pernah dicatat dengan snapshot berbeda. Perlu review; pencatatan lama tetap utuh di Lainnya.",
                    );
                if (active) setSaved(row);
            } else {
                const draft = await store.draft(owner, draftKey);
                if (draft) {
                    const p = CollectionReceiptSchema.parse(draft);
                    if (JSON.stringify(p.source) !== JSON.stringify(task))
                        throw new Error("Sumber draft collection berubah.");
                    await assertLocalEvidence(
                        await store.getEvidence(owner, p.evidence.id),
                        p.evidence,
                        owner,
                    );
                    if (active) {
                        setPayer(p.payer);
                        setAmount(p.amount);
                        setMethod(p.method);
                        setReceipt(p.receipt_number);
                        setTransfer(p.transfer_reference ?? "");
                        setNotes(p.notes);
                        setPhoto(p.evidence);
                    }
                }
            }
            if (active) setReady(true);
        })().catch((e) => {
            if (active) setMessage(e.message);
        });
        return () => {
            active = false;
        };
    }, [owner, key]);
    useEffect(() => {
        if (saved) {
            const row = queue.find((q) => q.key === saved.key);
            if (row) setSaved(row);
        }
    }, [queue, saved?.key]);
    async function action(send: boolean) {
        setBusy(true);
        setMessage("");
        try {
            const p = CollectionReceiptSchema.parse({
                collection_version: 1,
                source: task,
                payer,
                method,
                amount,
                receipt_number: receipt,
                ...(method === "transfer"
                    ? { transfer_reference: transfer }
                    : {}),
                notes,
                evidence: photo,
            });
            await assertLocalEvidence(
                await store.getEvidence(owner, p.evidence.id),
                p.evidence,
                owner,
            );
            if (send) {
                const at = new Date().toISOString();
                validateCollection(p, owner, at);
                const uuid = crypto.randomUUID();
                const row = await engine.enqueue(
                    "collection.receipt.submit",
                    p,
                    `Collection • ${task.receivable_reference}`,
                    uuid,
                    {
                        key,
                        expected: undefined,
                        occurredAt: at,
                        value: {
                            schema_version: 1,
                            client_uuid: uuid,
                            type: "collection.receipt.submit",
                            occurred_at: at,
                            payload: p,
                        },
                    },
                );
                setSaved(row);
                changed();
                void engine.flush();
                setMessage(
                    "Pencatatan masuk antrean review. Pembayaran Odoo belum diposting.",
                );
            } else {
                await store.draft(owner, draftKey, p);
                setMessage(
                    "Draft collection tersimpan offline. Perbarui foto/lokasi bila kedaluwarsa.",
                );
            }
        } catch (e) {
            setMessage(
                e instanceof z.ZodError
                    ? "Periksa pembayar, nominal Rupiah bulat, nomor tanda terima, referensi transfer dan foto wajib."
                    : e instanceof Error
                      ? e.message
                      : "Gagal menyimpan collection.",
            );
        } finally {
            setBusy(false);
        }
    }
    const value =
        saved?.command.type === "collection.receipt.submit"
            ? saved.command.payload
            : undefined;
    return (
        <details class="collection-task">
            <summary>
                <Icon name="wallet" size={20} /> {task.receivable_reference} ·{" "}
                {task.delivery.outlet}
            </summary>
            <p>
                {task.delivery.id} · {task.delivery.trip} ·{" "}
                {task.delivery.business_date}
            </p>
            <p>
                Saldo contoh {money(Number(task.amount_due))} · snapshot{" "}
                {new Date(task.issued_at).toLocaleString("id-ID", {
                    timeZone: "Asia/Makassar",
                })}{" "}
                WITA
            </p>
            {message && <p role="status">{message}</p>}
            {saved && value ? (
                <>
                    <p>
                        Pencatatan tersimpan ·{" "}
                        {saved.command.client_uuid.slice(0, 8)}. Status terbaru
                        di Lainnya; bukan AR lunas.
                    </p>
                    <p>
                        Pembayar: {value.payer} ·{" "}
                        {value.method === "cash"
                            ? "Tunai"
                            : "Bukti transfer (belum verifikasi bank)"}{" "}
                        · {money(Number(value.amount))}
                    </p>
                    <p>
                        Nomor tanda terima: {value.receipt_number}
                        {value.transfer_reference
                            ? ` · Referensi transfer: ${value.transfer_reference}`
                            : ""}
                    </p>
                    {value.notes && <p>Catatan: {value.notes}</p>}
                    <EvidenceCapture
                        store={store}
                        owner={owner}
                        existingRef={value.evidence}
                        readOnly
                        onChange={() => {}}
                    />
                </>
            ) : ready ? (
                <fieldset disabled={busy}>
                    <label>
                        Pembayar
                        <input
                            value={payer}
                            maxLength={100}
                            onInput={(e) => setPayer(e.currentTarget.value)}
                        />
                    </label>
                    <label>
                        Metode penerimaan
                        <select
                            value={method}
                            onChange={(e) =>
                                setMethod(
                                    e.currentTarget.value as typeof method,
                                )
                            }
                        >
                            <option value="cash">Tunai</option>
                            <option value="transfer">
                                Bukti transfer · belum verifikasi bank
                            </option>
                        </select>
                    </label>
                    <label>
                        Nominal diterima (Rupiah bulat)
                        <input
                            value={amount}
                            inputMode="numeric"
                            maxLength={12}
                            onInput={(e) => setAmount(e.currentTarget.value)}
                        />
                    </label>
                    <label>
                        Nomor tanda terima
                        <input
                            value={receipt}
                            maxLength={80}
                            onInput={(e) => setReceipt(e.currentTarget.value)}
                        />
                    </label>
                    {method === "transfer" && (
                        <label>
                            Referensi transfer
                            <input
                                value={transfer}
                                maxLength={80}
                                onInput={(e) =>
                                    setTransfer(e.currentTarget.value)
                                }
                            />
                        </label>
                    )}
                    <label>
                        Catatan penerimaan
                        <textarea
                            value={notes}
                            maxLength={500}
                            onInput={(e) => setNotes(e.currentTarget.value)}
                        />
                    </label>
                    <EvidenceCapture
                        store={store}
                        owner={owner}
                        existingRef={photo}
                        onChange={setPhoto}
                    />
                    <button
                        class="secondary"
                        disabled={!photo}
                        onClick={() => void action(false)}
                    >
                        Simpan draft collection
                    </button>
                    <button
                        class="primary"
                        disabled={!photo}
                        onClick={() => void action(true)}
                    >
                        Ajukan penerimaan untuk review
                    </button>
                </fieldset>
            ) : (
                <p>Memulihkan data collection…</p>
            )}
        </details>
    );
}
