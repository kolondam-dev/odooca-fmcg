import { useEffect, useState } from "preact/hooks";
import { z } from "zod";
import {
    DeliveryTaskSchema,
    DeliveryPodSchema,
    podKey,
    type DeliveryTask,
} from "../domain/delivery-contracts";
import { businessRejected } from "../domain/outbox-state";
import { validatePod, validatePodMedia, podLineage } from "../domain/delivery";
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
    queue,
}: {
    store: FieldStore;
    identity: Identity;
    provider: FieldProvider;
    engine: Outbox;
    changed: () => void;
    queue: QueueItem[];
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
                    {...{ task, store, owner, engine, changed, queue }}
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
    queue,
}: {
    task: DeliveryTask;
    store: FieldStore;
    owner: string;
    engine: Outbox;
    changed: () => void;
    queue: QueueItem[];
}) {
    const key = podKey(task);
    const [revision, setRevision] = useState<QueueItem>();
    const [correctionReason, setCorrectionReason] = useState("");
    const [history, setHistory] = useState<QueueItem[]>([]);
    const draftKey = `${key}:form${revision ? `:${revision.command.client_uuid}` : ""}`;
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
                if (active) {
                    setSaved(row);
                    setHistory(
                        podLineage(await store.list(owner), owner, task.id),
                    );
                }
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
    useEffect(() => {
        if (saved) {
            const latest = queue.find((r) => r.key === saved.key);
            if (latest) setSaved(latest);
            setHistory((previous) =>
                previous.map((h) => queue.find((r) => r.key === h.key) ?? h),
            );
        }
    }, [queue, saved?.key]);
    async function startCorrection() {
        if (!saved) return;
        setBusy(true);
        try {
            const current = (await store.list(owner)).find(
                (r) => r.key === saved.key,
            );
            if (
                !current ||
                !businessRejected(current) ||
                current.command.type !== "delivery.pod.submit"
            )
                throw new Error("Belum ada penolakan bisnis yang cocok.");
            await validatePodMedia(current, owner, store);
            let p = current.command.payload;
            const draft = await store.draft(
                owner,
                `${key}:form:${current.command.client_uuid}`,
            );
            if (draft !== undefined) {
                const d = DeliveryPodSchema.parse(draft);
                if (
                    d.supersedes_uuid !== current.command.client_uuid ||
                    JSON.stringify(d.source) !== JSON.stringify(task)
                )
                    throw new Error("Draft koreksi tidak cocok dengan parent.");
                await assertLocalEvidence(
                    await store.getEvidence(owner, d.evidence.id),
                    d.evidence,
                    owner,
                );
                p = d;
            }
            setRecipient(p.recipient);
            setOutcome(p.outcome);
            setLines(p.lines);
            setReason(p.reason);
            setPhoto(draft ? p.evidence : undefined);
            setCorrectionReason(draft ? (p.correction_reason ?? "") : "");
            setRevision(current);
            setReady(true);
            setMessage("");
        } catch (e) {
            setMessage(
                e instanceof Error ? e.message : "Koreksi gagal dibuka.",
            );
        } finally {
            setBusy(false);
        }
    }
    async function action(send: boolean) {
        setBusy(true);
        setMessage("");
        try {
            const p = DeliveryPodSchema.parse({
                pod_version: 1,
                ...(revision
                    ? {
                          supersedes_uuid: revision.command.client_uuid,
                          correction_reason: correctionReason,
                      }
                    : {}),
                source: task,
                recipient,
                outcome,
                reason,
                lines,
                evidence: photo,
            });
            if (revision) await validatePodMedia(revision, owner, store);
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
                        expected: revision?.command,
                        ...(revision ? { guards: { source: revision } } : {}),
                        occurredAt: at,
                    },
                );
                setSaved(row);
                setRevision(undefined);
                setHistory(podLineage(await store.list(owner), owner, task.id));
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
            {saved && !revision ? (
                <>
                    <p>
                        POD tersimpan · {saved.command.client_uuid.slice(0, 8)}.
                        Status terbaru ada di Lainnya. Menunggu review; bukan
                        picking selesai.
                    </p>
                    {businessRejected(saved) && (
                        <button
                            class="secondary"
                            disabled={busy}
                            onClick={() => void startCorrection()}
                        >
                            Koreksi POD ditolak
                        </button>
                    )}
                    {history.length > 1 && (
                        <details>
                            <summary>Riwayat POD ({history.length})</summary>
                            {history.map((h) => (
                                <p key={h.key}>
                                    {h.command.client_uuid.slice(0, 8)} ·{" "}
                                    {
                                        {
                                            queued: "Menunggu sync",
                                            sending: "Mengirim",
                                            accepted: "Diterima simulator",
                                            needs_approval: "Menunggu approval",
                                            rejected: "Ditolak",
                                            auth_required: "Sesi diperlukan",
                                        }[h.state]
                                    }{" "}
                                    ·{" "}
                                    {h.command.type === "delivery.pod.submit"
                                        ? `${h.command.payload.recipient} · ${{ delivered: "Diterima penuh", partial: "Diterima sebagian", rejected: "Ditolak seluruhnya" }[h.command.payload.outcome]} · ${h.command.payload.lines.map((l) => `${l.received}`).join(", ")} karton${h.command.payload.correction_reason ? ` · ${h.command.payload.correction_reason}` : ""}`
                                        : ""}
                                </p>
                            ))}
                        </details>
                    )}
                    {saved.command.type === "delivery.pod.submit" && (
                        <>
                            {saved.command.payload.correction_reason && (
                                <p>
                                    Alasan koreksi:{" "}
                                    {saved.command.payload.correction_reason} ·
                                    atas{" "}
                                    {saved.command.payload.supersedes_uuid?.slice(
                                        0,
                                        8,
                                    )}
                                </p>
                            )}
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
                    {revision && (
                        <>
                            <p>
                                Koreksi atas{" "}
                                {revision.command.client_uuid.slice(0, 8)}.
                                Pengajuan sebelumnya tetap tersimpan. Foto baru
                                wajib.
                            </p>
                            <label>
                                Alasan koreksi
                                <textarea
                                    value={correctionReason}
                                    maxLength={500}
                                    onInput={(e) =>
                                        setCorrectionReason(
                                            e.currentTarget.value,
                                        )
                                    }
                                />
                            </label>
                            <button
                                class="secondary"
                                onClick={() => setRevision(undefined)}
                            >
                                Kembali ke POD tersimpan
                            </button>
                        </>
                    )}
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
