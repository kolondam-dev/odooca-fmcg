import { useEffect, useState } from "preact/hooks";
import { z } from "zod";
import {
    DeliveryTaskSchema,
    DeliveryPodSchema,
    podKey,
    type DeliveryTask,
} from "../domain/delivery-contracts";
import { validatePod, validatePodMedia } from "../domain/delivery";
import { assertLocalEvidence } from "../domain/evidence-package";
import { Icon } from "./Icon";
import { EvidenceCapture, type EvidenceRef } from "./Evidence";
import type { Outbox } from "../domain/outbox";
import type { FieldStore, QueueItem } from "../storage/store";
import type { FieldProvider, Identity } from "../domain/contracts";
import { ownerKey } from "../domain/contracts";
export function DeliveryWorkspace({
    store,
    identity,
    provider,
    engine,
    changed,
}: {
    store: FieldStore;
    identity: Identity;
    provider: FieldProvider;
    engine: Outbox;
    changed: () => void;
}) {
    const owner = ownerKey(identity),
        cache = `delivery-manifest-v1:${identity.businessDate}`;
    const [tasks, setTasks] = useState<DeliveryTask[]>(),
        [error, setError] = useState("");
    useEffect(() => {
        let active = true;
        void (async () => {
            let value = await store.draft(owner, cache);
            if (value === undefined) {
                if (!navigator.onLine || !provider.deliveryTasks)
                    throw new Error(
                        "Manifest belum tersedia. Hubungkan jaringan untuk memuat tugas.",
                    );
                value = await store.createDraftIfAbsent(
                    owner,
                    cache,
                    await provider.deliveryTasks(),
                );
            }
            const parsed = z.array(DeliveryTaskSchema).min(1).parse(value);
            if (
                parsed.some(
                    (s) =>
                        s.owner !== owner ||
                        s.business_date !== identity.businessDate,
                ) ||
                new Set(parsed.map(podKey)).size !== parsed.length
            )
                throw new Error(
                    "Manifest tidak cocok dengan petugas/hari ini.",
                );
            if (active) setTasks(parsed);
        })().catch((e) => {
            if (active) setError(e.message);
        });
        return () => {
            active = false;
        };
    }, [owner, cache]);
    return (
        <section>
            <h2>Serah terima pengiriman</h2>
            <p class="notice">
                Simulasi POD · manifest contoh satu item per DO. Tidak
                memposting stok, picking, retur atau penerimaan uang.
            </p>
            {error && <p role="alert">{error}</p>}
            {tasks?.map((task) => (
                <PodForm
                    key={JSON.stringify(task)}
                    {...{ task, store, owner, engine, changed }}
                />
            ))}
        </section>
    );
}
function PodForm({
    task,
    store,
    owner,
    engine,
    changed,
}: {
    task: DeliveryTask;
    store: FieldStore;
    owner: string;
    engine: Outbox;
    changed: () => void;
}) {
    const key = podKey(task),
        draftKey = `${key}:form`;
    const [recipient, setRecipient] = useState(""),
        [outcome, setOutcome] = useState<"delivered" | "partial" | "rejected">(
            "delivered",
        ),
        [reason, setReason] = useState("");
    const [lines, setLines] = useState(
            task.lines.map((l) => ({ id: l.id, received: l.quantity })),
        ),
        [photo, setPhoto] = useState<EvidenceRef>();
    const [saved, setSaved] = useState<QueueItem>(),
        [ready, setReady] = useState(false),
        [busy, setBusy] = useState(false),
        [message, setMessage] = useState("");
    useEffect(() => {
        let active = true;
        void (async () => {
            const command = await store.draft(owner, key);
            if (command) {
                const row = (await store.list(owner)).find(
                    (r) =>
                        r.command.client_uuid ===
                        (command as { client_uuid: string }).client_uuid,
                );
                if (!row)
                    throw new Error("POD kehilangan antrean. Perlu review.");
                await validatePodMedia(row, owner, store);
                if (active) setSaved(row);
            } else {
                const d = await store.draft(owner, draftKey);
                if (d) {
                    const p = DeliveryPodSchema.parse(d);
                    if (JSON.stringify(p.source) !== JSON.stringify(task))
                        throw new Error("Sumber draft berubah.");
                    await assertLocalEvidence(
                        await store.getEvidence(owner, p.evidence.id),
                        p.evidence,
                        owner,
                    );
                    if (active) {
                        setRecipient(p.recipient);
                        setOutcome(p.outcome);
                        setReason(p.reason);
                        setLines(p.lines);
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
    async function action(send: boolean) {
        setBusy(true);
        setMessage("");
        try {
            const p = DeliveryPodSchema.parse({
                pod_version: 1,
                source: task,
                recipient,
                outcome,
                reason,
                lines,
                evidence: photo,
            });
            await assertLocalEvidence(
                await store.getEvidence(owner, p.evidence.id),
                p.evidence,
                owner,
            );
            if (send) {
                const at = new Date().toISOString();
                validatePod(p, owner, at);
                const uuid = crypto.randomUUID();
                const row = await engine.enqueue(
                    "delivery.pod.submit",
                    p,
                    `POD • ${task.id}`,
                    uuid,
                    {
                        key,
                        value: {
                            schema_version: 1,
                            client_uuid: uuid,
                            type: "delivery.pod.submit",
                            occurred_at: at,
                            payload: p,
                        },
                        expected: undefined,
                        occurredAt: at,
                    },
                );
                setSaved(row);
                changed();
                void engine.flush();
                setMessage(
                    "POD masuk antrean. Belum diverifikasi/ditutup oleh Odoo.",
                );
            } else {
                await store.draft(owner, draftKey, p);
                setMessage(
                    "Draft POD tersimpan offline. Foto harus tetap segar saat diajukan.",
                );
            }
        } catch (e) {
            setMessage(e instanceof Error ? e.message : "Gagal menyimpan POD.");
        } finally {
            setBusy(false);
        }
    }
    return (
        <details class="delivery-task">
            <summary>
                <Icon name="truck" size={20} /> {task.id} · {task.outlet}
            </summary>
            <p>
                {task.trip} · {task.vehicle} · {task.business_date}
            </p>
            <p>
                {task.address} · radius {task.site.radius} m
            </p>
            {message && <p role="status">{message}</p>}
            {saved ? (
                <>
                    <p>
                        POD tersimpan · {saved.command.client_uuid.slice(0, 8)}.
                        Status terbaru ada di Lainnya. Menunggu review; bukan
                        picking selesai.
                    </p>
                    {saved.command.type === "delivery.pod.submit" && (
                        <>
                            <p>
                                Penerima: {saved.command.payload.recipient} ·
                                Hasil:{" "}
                                {
                                    {
                                        delivered: "Diterima penuh",
                                        partial: "Diterima sebagian",
                                        rejected: "Ditolak seluruhnya",
                                    }[saved.command.payload.outcome]
                                }
                            </p>
                            <ul>
                                {saved.command.payload.lines.map((line) => (
                                    <li key={line.id}>
                                        {
                                            task.lines.find(
                                                (l) => l.id === line.id,
                                            )?.name
                                        }
                                        : {line.received} /{" "}
                                        {
                                            task.lines.find(
                                                (l) => l.id === line.id,
                                            )?.quantity
                                        }{" "}
                                        karton
                                    </li>
                                ))}
                            </ul>
                            {saved.command.payload.reason && (
                                <p>Catatan: {saved.command.payload.reason}</p>
                            )}
                            <EvidenceCapture
                                store={store}
                                owner={owner}
                                existingRef={saved.command.payload.evidence}
                                readOnly
                                onChange={() => {}}
                            />
                        </>
                    )}
                </>
            ) : ready ? (
                <fieldset disabled={busy}>
                    <label>
                        Penerima
                        <input
                            value={recipient}
                            maxLength={100}
                            onInput={(e) => setRecipient(e.currentTarget.value)}
                        />
                    </label>
                    <label>
                        Hasil serah terima
                        <select
                            value={outcome}
                            onChange={(e) =>
                                setOutcome(
                                    e.currentTarget.value as typeof outcome,
                                )
                            }
                        >
                            <option value="delivered">Diterima penuh</option>
                            <option value="partial">Diterima sebagian</option>
                            <option value="rejected">Ditolak seluruhnya</option>
                        </select>
                    </label>
                    {task.lines.map((l, i) => (
                        <label key={l.id}>
                            {l.name} · dikirim {l.quantity} {l.unit}
                            <input
                                aria-label={`Diterima ${l.name}`}
                                type="number"
                                min={0}
                                max={l.quantity}
                                value={lines[i].received}
                                onInput={(e) =>
                                    setLines(
                                        lines.map((a, j) =>
                                            j === i
                                                ? {
                                                      ...a,
                                                      received: Number(
                                                          e.currentTarget.value,
                                                      ),
                                                  }
                                                : a,
                                        ),
                                    )
                                }
                            />
                        </label>
                    ))}
                    <label>
                        Alasan / catatan
                        <textarea
                            value={reason}
                            maxLength={500}
                            onInput={(e) => setReason(e.currentTarget.value)}
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
                        Simpan draft POD
                    </button>
                    <button
                        class="primary"
                        disabled={!photo}
                        onClick={() => void action(true)}
                    >
                        Ajukan POD untuk review
                    </button>
                </fieldset>
            ) : (
                <p>Memulihkan data…</p>
            )}
        </details>
    );
}
