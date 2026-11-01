import {
    deliveryWorkKey,
    restoreDeliveryWork,
    receivedOutcome,
} from "../domain/delivery-work";
import { FullDrawer } from "./FullDrawer";
import { DeliveryFee } from "./DeliveryFee";
import {
    MORNING_KEY,
    morningReady,
    type MorningRecord,
} from "../domain/morning";
import {
    DELIVERY_SESSION_KEY,
    statusOutcome,
    validateDeliverySession,
} from "../domain/delivery";
import {
    DeliverySessionSchema,
    type DeliveryPod,
} from "../domain/delivery-contracts";
import { captureVisitLocation } from "../domain/visits";
import { requireVisitFix } from "../domain/visit-validation";
import type { VisitFix } from "../domain/visit-contracts";
import { useEffect, useState } from "preact/hooks";
import { z } from "zod";
import {
    DeliveryTaskSchema,
    DeliveryDoReasonSchema,
    DeliveryItemReasonSchema,
    DeliveryPodSchema,
    podKey,
    type DeliveryTask,
} from "../domain/delivery-contracts";
import { businessRejected } from "../domain/outbox-state";
import {
    assertPodTaskSource,
    validatePod,
    validatePodMedia,
    podLineage,
} from "../domain/delivery";
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
            const morning = (await store.draft(owner, MORNING_KEY)) as
                | MorningRecord
                | undefined;
            if (!morningReady(morning, owner) || !morning?.deliveryManifest)
                throw new Error(
                    "Daily sync manifest wajib sebelum list Delivery.",
                );
            const manifest = z
                .array(DeliveryTaskSchema)
                .min(1)
                .parse(morning.deliveryManifest);
            if (
                manifest.some(
                    (s) =>
                        s.owner !== owner ||
                        s.business_date !== identity.businessDate,
                ) ||
                new Set(manifest.map(podKey)).size !== manifest.length
            )
                throw new Error(
                    "Manifest tidak cocok dengan petugas/hari ini.",
                );
            let value = await store.draft(owner, cache);
            if (value === undefined) {
                // Daily sync already fetched this bundle. No network is needed to
                // materialize the validated local projection for the first visit.
                value = await store.createDraftIfAbsent(owner, cache, manifest);
            }
            const parsed = z.array(DeliveryTaskSchema).min(1).parse(value);
            if (JSON.stringify(parsed) !== JSON.stringify(manifest))
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
    const [phase, setPhase] = useState<"checkin" | "items" | "close">(
        "checkin",
    );
    const [posOpen, setPosOpen] = useState(false);
    function wizard(mode: "full" | "half" | "reject") {
        const values = task.lines.map((line) => ({
            id: line.id,
            received:
                mode === "full"
                    ? line.quantity
                    : mode === "half"
                      ? Math.floor(line.quantity / 2)
                      : 0,
            reason: "",
        }));
        const total = values.reduce((sum, line) => sum + line.received, 0);
        setDoReason("");
        setLines(values);
        setOutcome(
            mode === "full" ? "delivered" : total ? "partial" : "rejected",
        );
        setReason(mode === "full" ? "Diterima semua" : "");
    }
    const key = podKey(task);
    const [session, setSession] = useState<DeliveryPod["session"]>();
    const [opening, setOpening] = useState<EvidenceRef>();
    const [pinpoint, setPinpoint] = useState<VisitFix>();
    const [pinpointSetAt, setPinpointSetAt] = useState<string>();
    const [doReason, setDoReason] = useState("");
    const [requestedDate, setRequestedDate] = useState("");
    const [cancelReason, setCancelReason] = useState("Toko Tutup");
    const [revision, setRevision] = useState<QueueItem>();
    const [correctionReason, setCorrectionReason] = useState("");
    const [history, setHistory] = useState<QueueItem[]>([]);
    const draftKey = `${key}:form${revision ? `:${revision.command.client_uuid}` : ""}`;
    const [recipient, setRecipient] = useState(""),
        [outcome, setOutcome] = useState<DeliveryPod["outcome"]>("delivered"),
        [reason, setReason] = useState("");
    const [lines, setLines] = useState<
            {
                id: string;
                received: number;
                reason: string;
                item_reason?: string;
                item_note?: string;
            }[]
        >(
            task.lines.map((l) => ({
                id: l.id,
                received: l.quantity,
                reason: "",
            })),
        ),
        [photo, setPhoto] = useState<EvidenceRef>();
    const [saved, setSaved] = useState<QueueItem>(),
        [ready, setReady] = useState(false),
        [busy, setBusy] = useState(false),
        [message, setMessage] = useState("");
    useEffect(() => {
        let active = true;
        void (async () => {
            const activeSession = (await store.draft(
                owner,
                DELIVERY_SESSION_KEY,
            )) as { session?: unknown; closed?: string } | undefined;
            if (activeSession?.session && !activeSession.closed) {
                const restoredSession = DeliverySessionSchema.parse(
                    activeSession.session,
                );
                if (restoredSession.task_id === task.id) {
                    validateDeliverySession(
                        restoredSession,
                        task,
                        owner,
                        new Date().toISOString(),
                    );
                    if (
                        JSON.stringify(
                            await store.draft(owner, MORNING_KEY),
                        ) !== JSON.stringify(restoredSession.daily_source)
                    )
                        throw new Error(
                            "Sesi delivery berbeda daily sync; perlu review.",
                        );
                    await assertLocalEvidence(
                        await store.getEvidence(
                            owner,
                            restoredSession.opening.id,
                        ),
                        restoredSession.opening,
                        owner,
                    );
                    if (active) setSession(restoredSession);
                }
            }
            const command = await store.draft(owner, key);
            if (command) {
                const row = (await store.list(owner)).find(
                    (r) =>
                        r.command.client_uuid ===
                        (command as { client_uuid: string }).client_uuid,
                );
                if (!row)
                    throw new Error("POD kehilangan antrean. Perlu review.");
                assertPodTaskSource(row, task, owner);
                await validatePodMedia(row, owner, store);
                if (active) {
                    setSaved(row);
                    setSession(undefined);
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
                        setDoReason(p.do_reason ?? "");
                        setRequestedDate(
                            p.request?.kind === "reschedule"
                                ? p.request.requested_date
                                : "",
                        );
                        setCancelReason(
                            p.request?.kind === "cancel"
                                ? p.request.sub_reason
                                : "Toko Tutup",
                        );
                        setLines(
                            p.lines.map((l) => ({
                                ...l,
                                reason: l.item_note ?? l.reason ?? "",
                            })),
                        );
                        setPhoto(p.evidence);
                    }
                }
            }
            if (
                !command &&
                (await store.draft(owner, draftKey)) === undefined
            ) {
                const scratch = await store.draft(owner, deliveryWorkKey(task));
                if (scratch !== undefined) {
                    const value = restoreDeliveryWork(scratch, task);
                    if (active) {
                        setRecipient(value.recipient);
                        setOutcome(value.outcome);
                        setLines(value.lines);
                        setReason(value.reason);
                        setDoReason(value.doReason);
                        setRequestedDate(value.requestedDate);
                        setCancelReason(value.cancelReason);
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
    useEffect(() => {
        if (ready && !saved && !revision)
            void store
                .draft(owner, deliveryWorkKey(task), {
                    source: task,
                    recipient,
                    outcome,
                    reason,
                    doReason,
                    requestedDate,
                    cancelReason,
                    lines,
                })
                .catch(() => setMessage("Draft penerimaan gagal disimpan."));
    }, [
        ready,
        saved,
        revision,
        recipient,
        outcome,
        reason,
        doReason,
        requestedDate,
        cancelReason,
        lines,
    ]);
    function receive(index: number, value: number) {
        const next = lines.map((line, i) =>
            i === index
                ? {
                      ...line,
                      received: Math.max(
                          0,
                          Math.min(
                              task.lines[i].quantity,
                              Math.trunc(value) || 0,
                          ),
                      ),
                  }
                : line,
        );
        const status = receivedOutcome(next, task.lines);
        setLines(next);
        setOutcome(status);
        if (status === "delivered") setDoReason("");
        if (status === "delivered" && !reason.trim())
            setReason("Diterima semua");
    }
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
            setLines(
                p.lines.map((l) => ({
                    ...l,
                    reason: l.item_note ?? l.reason ?? "",
                })),
            );
            setReason(p.reason);
            setDoReason(p.do_reason ?? "");
            setRequestedDate(
                p.request?.kind === "reschedule"
                    ? p.request.requested_date
                    : "",
            );
            setCancelReason(
                p.request?.kind === "cancel"
                    ? p.request.sub_reason
                    : "Toko Tutup",
            );
            setPhoto(draft ? p.evidence : undefined);
            setCorrectionReason(draft ? (p.correction_reason ?? "") : "");
            const activeSession = (await store.draft(
                owner,
                DELIVERY_SESSION_KEY,
            )) as { session?: unknown; closed?: string } | undefined;
            setSession(
                activeSession?.session &&
                    !activeSession.closed &&
                    DeliverySessionSchema.parse(activeSession.session)
                        .task_id === task.id
                    ? DeliverySessionSchema.parse(activeSession.session)
                    : undefined,
            );
            setOpening(undefined);
            setPinpoint(undefined);
            setRevision(current);
            setPhase("checkin");
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
    function previewReceipt() {
        if (recipient.trim().length < 2) {
            setMessage("Lengkapi nama penerima.");
            return;
        }
        if (
            outcome === "partial" &&
            lines.some(
                (line, index) =>
                    line.received < task.lines[index].quantity &&
                    (line.reason.trim() || line.item_reason || "").length < 3,
            )
        ) {
            setMessage(
                "Pilih alasan untuk setiap item yang tidak diterima lengkap.",
            );
            return;
        }
        if (outcome !== "partial" && reason.trim().length < 3) {
            setMessage("Lengkapi alasan status DO.");
            return;
        }
        if (
            outcome === "pending_requested" &&
            !z.iso.date().safeParse(requestedDate).success
        ) {
            setMessage("Tentukan estimasi tanggal kirim.");
            return;
        }
        setMessage("");
        setPosOpen(false);
        setPhase("close");
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
                ...(doReason ? { do_reason: doReason } : {}),
                ...(task.site.demo_unrestricted &&
                outcome === "pending_requested"
                    ? {
                          request: {
                              kind: "reschedule",
                              requested_date: requestedDate,
                          },
                      }
                    : task.site.demo_unrestricted &&
                        outcome === "cancel_delivery"
                      ? {
                            request: {
                                kind: "cancel",
                                sub_reason: cancelReason,
                            },
                        }
                      : {}),
                recipient,
                outcome,
                reason: reason.trim(),
                lines: lines.map((l) => ({
                    ...l,
                    item_note: l.reason.trim() || undefined,
                    reason:
                        outcome === "partial"
                            ? l.reason.trim() || l.item_reason || ""
                            : reason.trim(),
                })),
                ...(task.workflow_version === 2
                    ? {
                          delivery_status: Object.entries(statusOutcome).find(
                              ([, v]) => v === outcome,
                          )?.[0],
                          session,
                      }
                    : {}),
                evidence: photo,
            });
            if (p.session)
                await assertLocalEvidence(
                    await store.getEvidence(owner, p.session.opening.id),
                    p.session.opening,
                    owner,
                );
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
                setSession(undefined);
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
        <details class="delivery-task" aria-busy={(!ready && !message) || busy}>
            <summary>
                <Icon name="store" size={20} /> {task.id} · {task.outlet}{" "}
                {saved && !revision
                    ? "· Session closed"
                    : session
                      ? "· Sesi aktif"
                      : "· Belum dimulai"}
            </summary>
            <button
                type="button"
                class="secondary delivery-back"
                onClick={(event) => {
                    const details = event.currentTarget.closest("details");
                    if (details) details.open = false;
                }}
            >
                Kembali ke daftar DO
            </button>
            <p class="delivery-address">{task.address}</p>
            <nav class="workflow-tabs" aria-label={`Tahap ${task.id}`}>
                <button
                    aria-pressed={phase === "checkin"}
                    onClick={() => setPhase("checkin")}
                >
                    Check-in toko
                </button>
                <button
                    aria-pressed={phase === "items"}
                    disabled={
                        (task.workflow_version === 2 && !session) ||
                        (!!saved && !revision)
                    }
                    onClick={() => {
                        setPhase("items");
                        setPosOpen(true);
                    }}
                >
                    Open session
                </button>
                <button
                    aria-pressed={phase === "close"}
                    disabled={
                        task.workflow_version === 2 &&
                        !session &&
                        (!saved || !!revision)
                    }
                    onClick={() => setPhase("close")}
                >
                    Close session
                </button>
            </nav>
            {message && <p role="status">{message}</p>}
            {saved && !revision ? (
                <>
                    <p>
                        Session closed · POD tersimpan ·{" "}
                        {saved.command.client_uuid.slice(0, 8)}. Status terbaru
                        ada di Lainnya. Menunggu review; bukan picking selesai.
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
                                        ? `${h.command.payload.recipient} · ${{ delivered: "Fully Received", partial: "Received Partial", rejected: "Rejected", cancel_delivery: "Cancel Delivery", pending_requested: "Pending Requested" }[h.command.payload.outcome]} · ${h.command.payload.lines
                                              .map((l) => {
                                                  const source =
                                                      h.command.type ===
                                                      "delivery.pod.submit"
                                                          ? h.command.payload.source.lines.find(
                                                                (s) =>
                                                                    s.id ===
                                                                    l.id,
                                                            )
                                                          : undefined;
                                                  return `${source?.name ?? l.id}: ${l.received} ${source?.unit ?? "unit tidak tersedia"}`;
                                              })
                                              .join(
                                                  "; ",
                                              )}${h.command.payload.correction_reason ? ` · ${h.command.payload.correction_reason}` : ""}`
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
                                        delivered: "Fully Received",
                                        partial: "Received Partial",
                                        rejected: "Rejected",
                                        cancel_delivery: "Cancel Delivery",
                                        pending_requested: "Pending Requested",
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
                                        {
                                            task.lines.find(
                                                (l) => l.id === line.id,
                                            )?.unit
                                        }{" "}
                                        · alasan:{" "}
                                        {line.item_reason ??
                                            line.reason ??
                                            "legacy"}
                                        {line.item_note &&
                                        line.item_note !== line.item_reason
                                            ? ` · ${line.item_note}`
                                            : ""}
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
                <>
                    {task.workflow_version === 2 && !session && (
                        <fieldset disabled={busy} hidden={phase !== "checkin"}>
                            <h3>Check-in toko</h3>
                            <p>
                                Foto toko → set pinpoint → mulai sesi. Tutup
                                sesi aktif sebelum pindah DO.
                            </p>
                            <EvidenceCapture
                                store={store}
                                owner={owner}
                                existingRef={opening}
                                onChange={(ref) => {
                                    setOpening(ref);
                                    setPinpoint(undefined);
                                }}
                            />
                            <button
                                class="secondary"
                                disabled={!opening}
                                onClick={() => {
                                    setBusy(true);
                                    setMessage("");
                                    void captureVisitLocation()
                                        .then((fix) => {
                                            requireVisitFix(fix, task.site);
                                            setPinpoint(fix);
                                            setPinpointSetAt(
                                                new Date().toISOString(),
                                            );
                                        })
                                        .catch((e) => setMessage(e.message))
                                        .finally(() => setBusy(false));
                                }}
                            >
                                Set pinpoint delivery
                            </button>
                            {pinpoint && (
                                <p>
                                    Pinpoint {pinpoint.latitude.toFixed(6)},{" "}
                                    {pinpoint.longitude.toFixed(6)} · ±
                                    {pinpoint.accuracy} m
                                </p>
                            )}
                            <button
                                class="primary"
                                disabled={!opening || !pinpoint}
                                onClick={() => {
                                    setBusy(true);
                                    setMessage("");
                                    void (async () => {
                                        requireVisitFix(pinpoint!, task.site);
                                        const daily = await store.draft(
                                            owner,
                                            MORNING_KEY,
                                        );
                                        const value =
                                            DeliverySessionSchema.parse({
                                                id: crypto.randomUUID(),
                                                owner,
                                                task_id: task.id,
                                                opened_at:
                                                    new Date().toISOString(),
                                                opening,
                                                pinpoint,
                                                pinpoint_set_at: pinpointSetAt,
                                                daily_source: daily,
                                            });
                                        setSession(
                                            await store.openDeliverySession(
                                                owner,
                                                task,
                                                value,
                                            ),
                                        );
                                    })()
                                        .catch((e) => setMessage(e.message))
                                        .finally(() => setBusy(false));
                                }}
                            >
                                Mulai sesi delivery
                            </button>
                        </fieldset>
                    )}
                    {(task.workflow_version !== 2 || session) && (
                        <div>
                            {posOpen && (
                                <FullDrawer
                                    title={`Items ${task.id}`}
                                    close={() => {
                                        setPosOpen(false);
                                        setPhase("close");
                                    }}
                                >
                                    <fieldset disabled={busy}>
                                        {message && (
                                            <p role="alert">{message}</p>
                                        )}
                                        <div class="delivery-wizard">
                                            <button
                                                type="button"
                                                onClick={() => wizard("full")}
                                            >
                                                Terima semua
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => wizard("half")}
                                            >
                                                Terima setengah
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => wizard("reject")}
                                            >
                                                Tolak semua
                                            </button>
                                        </div>
                                        {revision && (
                                            <>
                                                <p>
                                                    Koreksi atas{" "}
                                                    {revision.command.client_uuid.slice(
                                                        0,
                                                        8,
                                                    )}
                                                    . Pengajuan sebelumnya tetap
                                                    tersimpan. Foto baru wajib.
                                                </p>
                                                <label>
                                                    Alasan koreksi
                                                    <textarea
                                                        value={correctionReason}
                                                        maxLength={500}
                                                        onInput={(e) =>
                                                            setCorrectionReason(
                                                                e.currentTarget
                                                                    .value,
                                                            )
                                                        }
                                                    />
                                                </label>
                                                <button
                                                    class="secondary"
                                                    onClick={() =>
                                                        setRevision(undefined)
                                                    }
                                                >
                                                    Kembali ke POD tersimpan
                                                </button>
                                            </>
                                        )}
                                        {session && (
                                            <p>
                                                Sesi delivery aktif ·{" "}
                                                {session.id.slice(0, 8)}. Proses
                                                intra sesi, lalu foto closing
                                                serah-terima barang/faktur/uang.
                                            </p>
                                        )}
                                        <label>
                                            Penerima
                                            <input
                                                value={recipient}
                                                maxLength={100}
                                                onInput={(e) =>
                                                    setRecipient(
                                                        e.currentTarget.value,
                                                    )
                                                }
                                            />
                                        </label>
                                        <label>
                                            Hasil serah terima
                                            <select
                                                aria-label="Hasil serah terima"
                                                value={
                                                    outcome ===
                                                        "cancel_delivery" ||
                                                    outcome ===
                                                        "pending_requested"
                                                        ? "rejected"
                                                        : outcome
                                                }
                                                onChange={(e) => {
                                                    const next = e.currentTarget
                                                        .value as typeof outcome;
                                                    setOutcome(next);
                                                    setDoReason("");
                                                    if (next === "delivered")
                                                        setLines(
                                                            task.lines.map(
                                                                (l) => ({
                                                                    id: l.id,
                                                                    received:
                                                                        l.quantity,
                                                                    reason: "",
                                                                }),
                                                            ),
                                                        );
                                                    else if (next !== "partial")
                                                        setLines(
                                                            task.lines.map(
                                                                (l) => ({
                                                                    id: l.id,
                                                                    received: 0,
                                                                    reason: "",
                                                                }),
                                                            ),
                                                        );
                                                }}
                                            >
                                                <option value="delivered">
                                                    DITERIMA SEMUA
                                                </option>
                                                <option value="partial">
                                                    DITERIMA PARSIAL
                                                </option>
                                                <option value="rejected">
                                                    DITOLAK SEMUA
                                                </option>
                                            </select>
                                        </label>
                                        {outcome !== "delivered" && (
                                            <label>
                                                Alasan DO
                                                <select
                                                    aria-label="Alasan DO"
                                                    value={doReason}
                                                    onChange={(event) => {
                                                        const selected =
                                                            event.currentTarget
                                                                .value;
                                                        setDoReason(selected);
                                                        setReason(selected);
                                                        if (
                                                            selected ===
                                                            "REQUEST PENDING KIRIM"
                                                        ) {
                                                            setOutcome(
                                                                "pending_requested",
                                                            );
                                                            setLines(
                                                                task.lines.map(
                                                                    (line) => ({
                                                                        id: line.id,
                                                                        received: 0,
                                                                        reason: "",
                                                                    }),
                                                                ),
                                                            );
                                                        } else if (
                                                            outcome !==
                                                            "partial"
                                                        ) {
                                                            const mapped: Record<
                                                                string,
                                                                string
                                                            > = {
                                                                "TOKO TUTUP":
                                                                    "Toko Tutup",
                                                                "TOKO TIDAK PUNYA UANG":
                                                                    "Tidak bisa bayar",
                                                                "TOKO TIDAK DAPAT DIAKSES":
                                                                    "Toko tidak dapat diakses",
                                                                "TOKO TIDAK ORDER":
                                                                    "Kesalahan Order",
                                                            };
                                                            setOutcome(
                                                                mapped[selected]
                                                                    ? "cancel_delivery"
                                                                    : "rejected",
                                                            );
                                                            if (
                                                                mapped[selected]
                                                            )
                                                                setCancelReason(
                                                                    mapped[
                                                                        selected
                                                                    ],
                                                                );
                                                        }
                                                    }}
                                                >
                                                    <option value="">
                                                        Pilih alasan DO
                                                    </option>
                                                    {DeliveryDoReasonSchema.options.map(
                                                        (reason) => (
                                                            <option
                                                                key={reason}
                                                            >
                                                                {reason}
                                                            </option>
                                                        ),
                                                    )}
                                                </select>
                                            </label>
                                        )}
                                        {outcome === "pending_requested" && (
                                            <label>
                                                Tanggal kirim ulang
                                                <input
                                                    aria-label="Tanggal kirim ulang"
                                                    type="date"
                                                    value={requestedDate}
                                                    onInput={(e) =>
                                                        setRequestedDate(
                                                            e.currentTarget
                                                                .value,
                                                        )
                                                    }
                                                />
                                                <small>
                                                    Kurang dari3 hari: SPV; 3
                                                    hari atau lebih: SPV +
                                                    Branch Manager.
                                                </small>
                                            </label>
                                        )}
                                        {task.lines.map((l, i) => (
                                            <label key={l.id}>
                                                {l.name} · dikirim {l.quantity}{" "}
                                                {l.unit}
                                                <input
                                                    disabled={
                                                        outcome ===
                                                            "pending_requested" ||
                                                        outcome ===
                                                            "cancel_delivery"
                                                    }
                                                    aria-label={`Diterima ${l.name}`}
                                                    type="number"
                                                    min={0}
                                                    max={l.quantity}
                                                    value={lines[i].received}
                                                    onInput={(event) =>
                                                        receive(
                                                            i,
                                                            Number(
                                                                event
                                                                    .currentTarget
                                                                    .value,
                                                            ),
                                                        )
                                                    }
                                                />
                                                <small>
                                                    {outcome ===
                                                        "cancel_delivery" ||
                                                    outcome ===
                                                        "pending_requested"
                                                        ? "Belum diterima"
                                                        : "Ditolak"}{" "}
                                                    {l.quantity -
                                                        lines[i].received}{" "}
                                                    {l.unit}
                                                </small>
                                                {(outcome === "partial" ||
                                                    outcome === "rejected") &&
                                                    lines[i].received <
                                                        l.quantity && (
                                                        <>
                                                            <select
                                                                aria-label={`Pilihan alasan item ${l.name}`}
                                                                value={
                                                                    lines[i]
                                                                        .item_reason ??
                                                                    ""
                                                                }
                                                                onChange={(
                                                                    event,
                                                                ) =>
                                                                    setLines(
                                                                        lines.map(
                                                                            (
                                                                                line,
                                                                                j,
                                                                            ) =>
                                                                                j ===
                                                                                i
                                                                                    ? {
                                                                                          ...line,
                                                                                          item_reason:
                                                                                              event
                                                                                                  .currentTarget
                                                                                                  .value ||
                                                                                              undefined,
                                                                                          reason:
                                                                                              event
                                                                                                  .currentTarget
                                                                                                  .value ||
                                                                                              line.reason,
                                                                                      }
                                                                                    : line,
                                                                        ),
                                                                    )
                                                                }
                                                            >
                                                                <option value="">
                                                                    Pilih alasan
                                                                    item
                                                                </option>
                                                                {DeliveryItemReasonSchema.options.map(
                                                                    (
                                                                        reason,
                                                                    ) => (
                                                                        <option
                                                                            key={
                                                                                reason
                                                                            }
                                                                        >
                                                                            {
                                                                                reason
                                                                            }
                                                                        </option>
                                                                    ),
                                                                )}
                                                            </select>
                                                            <textarea
                                                                aria-label={`Alasan item ${l.name}`}
                                                                required
                                                                minLength={3}
                                                                maxLength={500}
                                                                value={
                                                                    lines[i]
                                                                        .reason
                                                                }
                                                                onInput={(e) =>
                                                                    setLines(
                                                                        lines.map(
                                                                            (
                                                                                a,
                                                                                j,
                                                                            ) =>
                                                                                j ===
                                                                                i
                                                                                    ? {
                                                                                          ...a,
                                                                                          reason: e
                                                                                              .currentTarget
                                                                                              .value,
                                                                                      }
                                                                                    : a,
                                                                        ),
                                                                    )
                                                                }
                                                            />
                                                        </>
                                                    )}
                                            </label>
                                        ))}
                                        <label>
                                            {outcome === "partial"
                                                ? "Catatan umum (alasan wajib per item terdampak)"
                                                : "Alasan status (direkam ke semua item)"}
                                            <textarea
                                                value={reason}
                                                maxLength={500}
                                                onInput={(e) =>
                                                    setReason(
                                                        e.currentTarget.value,
                                                    )
                                                }
                                            />
                                        </label>
                                        <button
                                            type="button"
                                            class="primary full"
                                            onClick={previewReceipt}
                                        >
                                            Preview penerimaan
                                        </button>
                                    </fieldset>
                                </FullDrawer>
                            )}
                            <div
                                hidden={phase !== "close"}
                                class="delivery-closing"
                            >
                                <h3>Ringkasan penerimaan</h3>
                                <p>
                                    {outcome === "delivered"
                                        ? "DITERIMA SEMUA"
                                        : outcome === "partial"
                                          ? "DITERIMA PARSIAL"
                                          : "DITOLAK SEMUA"}
                                </p>
                                <ul>
                                    {task.lines.map((line, index) => (
                                        <li key={line.id}>
                                            {line.name}: {lines[index].received}{" "}
                                            / {line.quantity} {line.unit}
                                            {lines[index].item_reason &&
                                                ` · ${lines[index].item_reason}`}
                                            {lines[index].reason &&
                                                lines[index].reason !==
                                                    lines[index].item_reason &&
                                                ` · ${lines[index].reason}`}
                                        </li>
                                    ))}
                                </ul>
                                <button
                                    type="button"
                                    class="secondary"
                                    onClick={() => {
                                        setPhase("items");
                                        setPosOpen(true);
                                    }}
                                >
                                    Ubah penerimaan
                                </button>
                                <label>
                                    Catatan penutupan DO
                                    <textarea
                                        aria-label="Catatan penutupan DO"
                                        maxLength={500}
                                        value={reason}
                                        onInput={(event) =>
                                            setReason(event.currentTarget.value)
                                        }
                                    />
                                </label>
                                <DeliveryFee
                                    {...{ task, store, owner, engine, changed }}
                                    scope="delivery"
                                />
                                <DeliveryFee
                                    {...{ task, store, owner, engine, changed }}
                                    scope="outlet"
                                />
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
                            </div>
                        </div>
                    )}
                </>
            ) : (
                <p>
                    {message
                        ? "Data ditahan; perlu review."
                        : "Memulihkan data…"}
                </p>
            )}
        </details>
    );
}
