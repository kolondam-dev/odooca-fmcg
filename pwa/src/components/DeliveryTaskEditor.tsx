import { CheckinMap } from "./CheckinMap";
import { useBackLayer } from "../ui/navigation";
import { deliveryWorkKey, restoreDeliveryWork } from "../domain/delivery-work";
import { MORNING_KEY } from "../domain/morning";
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
import { useEffect, useRef, useState } from "preact/hooks";
import { z } from "zod";
import {
    DeliveryDoReasonSchema,
    DeliveryItemReasonSchema,
    DeliveryPodSchema,
    podKey,
    type DeliveryTask,
} from "../domain/delivery-contracts";
import type { Snapshot } from "../domain/contracts";
import { businessRejected } from "../domain/outbox-state";
import {
    assertPodTaskSource,
    validatePod,
    validatePodMedia,
    podLineage,
} from "../domain/delivery";
import { assertLocalEvidence } from "../domain/evidence-package";
import { Select } from "../ui";
import {
    ActionCaption,
    Button,
    Callout,
    Card,
    CardHead,
    Chip,
    Field,
    KV,
    ListRow,
    RadioRow,
    Screen,
    ScreenHeader,
    Segmented,
    Textarea,
    Tracker,
} from "../ui";
import { BiayaTokoScreen } from "./BiayaTokoScreen";
import { EvidenceCapture, type EvidenceRef } from "./Evidence";
import type { Outbox } from "../domain/outbox";
import type { ExpenseSubmit } from "./BiayaTokoScreen";
import type { FieldStore, QueueItem } from "../storage/store";
type Mode = "full" | "partial" | "reject";
export function DeliveryTaskEditor({
    task,
    store,
    owner,
    engine,
    changed,
    queue,
    snapshot,
    submit,
    collect,
    close,
}: {
    task: DeliveryTask;
    store: FieldStore;
    owner: string;
    engine: Outbox;
    changed: () => void;
    queue: QueueItem[];
    snapshot: Snapshot;
    submit: ExpenseSubmit;
    /** Membuka Penagihan toko ini; tidak ada bila toko tanpa tagihan. */
    collect?: () => void;
    close: () => void;
}) {
    /** hub toko (Delivery_hub) -> layar serah terima (Pod_*) / Biaya toko. */
    const [form, setForm] = useState(false);
    const [biayaOpen, setBiayaOpen] = useState(false);
    const [formError, setFormError] = useState("");
    useBackLayer(true, close);
    const key = podKey(task);
    const [session, setSession] = useState<DeliveryPod["session"]>();
    const [opening, setOpening] = useState<EvidenceRef>();
    const [pinpoint, setPinpoint] = useState<VisitFix>();
    const [locationPreview, setLocationPreview] = useState<VisitFix>();
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
        setLines((prev) =>
            prev.map((line, i) =>
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
            ),
        );
    }
    /** Tab Terima semua / Sebagian / Tolak pada layar serah terima (DS: Pod_*). */
    const mode: Mode =
        outcome === "delivered"
            ? "full"
            : outcome === "partial"
              ? "partial"
              : "reject";
    function chooseMode(next: Mode) {
        if (next === mode) return;
        setFormError("");
        setDoReason("");
        setRequestedDate("");
        if (next === "partial") {
            setOutcome("partial");
            setLines(
                task.lines.map((l) => ({
                    id: l.id,
                    received: l.quantity,
                    reason: "",
                })),
            );
            setReason("");
            return;
        }
        const full = next === "full";
        setOutcome(full ? "delivered" : "rejected");
        setLines(
            task.lines.map((l) => ({
                id: l.id,
                received: full ? l.quantity : 0,
                reason: "",
            })),
        );
        setReason(full ? "Diterima semua" : "");
    }
    /** Alasan DO pada mode Tolak; memetakan ke status delivery seperti dropdown lama. */
    function chooseDoReason(selected: string) {
        setFormError("");
        setDoReason(selected);
        setReason(selected);
        if (selected === "REQUEST PENDING KIRIM") {
            setOutcome("pending_requested");
            setLines(
                task.lines.map((line) => ({
                    id: line.id,
                    received: 0,
                    reason: "",
                })),
            );
            return;
        }
        const mapped: Record<string, string> = {
            "TOKO TUTUP": "Toko Tutup",
            "TOKO TIDAK PUNYA UANG": "Tidak bisa bayar",
            "TOKO TIDAK DAPAT DIAKSES": "Toko tidak dapat diakses",
            "TOKO TIDAK ORDER": "Kesalahan Order",
        };
        setOutcome(mapped[selected] ? "cancel_delivery" : "rejected");
        if (mapped[selected]) setCancelReason(mapped[selected]);
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
            setForm(false);
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
    const locationGeneration = useRef(0);
    const [locating, setLocating] = useState(false);
    const [locationSimulated, setLocationSimulated] = useState(false);
    async function locateDelivery() {
        const ticket = ++locationGeneration.current;
        setLocating(true);
        setPinpoint(undefined);
        setMessage("");
        try {
            const fix = await captureVisitLocation((source) => {
                if (ticket === locationGeneration.current)
                    setLocationSimulated(source === "demo");
            });
            if (ticket !== locationGeneration.current) return;
            setLocationPreview(fix);
            requireVisitFix(fix, task.site);
            setPinpoint(fix);
            setPinpointSetAt(new Date().toISOString());
        } catch (error) {
            if (ticket === locationGeneration.current)
                setMessage(
                    error instanceof Error
                        ? error.message
                        : "Lokasi belum tersedia.",
                );
        } finally {
            if (ticket === locationGeneration.current) setLocating(false);
        }
    }
    useEffect(() => {
        if (ready && !session && (!saved || revision)) void locateDelivery();
        return () => {
            locationGeneration.current++;
        };
    }, [ready, opening, session, revision, saved]);
    /** Validasi form serah terima; mengembalikan pesan galat atau string kosong. */
    function validateForm(): string {
        if (recipient.trim().length < 2) return "Lengkapi nama penerima.";
        if (outcome === "partial") {
            if (!lines.some((l, i) => l.received < task.lines[i].quantity))
                return "Mode Sebagian: kurangi jumlah diterima pada minimal satu item, atau pilih Terima semua.";
            if (
                lines.some(
                    (line, index) =>
                        line.received < task.lines[index].quantity &&
                        (line.reason.trim() || line.item_reason || "").length <
                            3,
                )
            )
                return "Pilih alasan untuk setiap item yang tidak diterima lengkap.";
        } else if (reason.trim().length < 3)
            return mode === "reject"
                ? "Pilih alasan penolakan."
                : "Lengkapi catatan serah terima.";
        if (
            outcome === "pending_requested" &&
            !z.iso.date().safeParse(requestedDate).success
        )
            return "Tentukan estimasi tanggal kirim.";
        return "";
    }
    async function action(send: boolean) {
        const invalid = validateForm();
        setFormError(invalid);
        if (invalid) return;
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
                setForm(false);
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
    const done = !!saved && !revision;
    const doReasonLabel = (r: string) =>
        ({
            "SKU TIDAK SESUAI ORDER": "SKU tidak sesuai order",
            "REQUEST PENDING KIRIM": "Request pending kirim",
        })[r] ?? r.charAt(0) + r.slice(1).toLowerCase();
    const outcomeLabel = {
        delivered: "Fully Received",
        partial: "Received Partial",
        rejected: "Rejected",
        cancel_delivery: "Cancel Delivery",
        pending_requested: "Pending Requested",
    } as const;
    const totalPcs = task.lines.reduce((a, l) => a + l.quantity, 0);
    const drop = task.lines.map((l) => `${l.quantity} ${l.unit}`).join(", ");
    const headerTitle = `${task.id} · ${task.outlet}`;
    const note = message ? <Callout tone="info">{message}</Callout> : null;
    const frame = "ui-screen--over ui-screen--top";

    if (!ready)
        return (
            <Screen
                label={`Delivery ${task.id}`}
                class={frame}
                header={<ScreenHeader title={headerTitle} onBack={close} />}
            >
                <p aria-busy="true">
                    {message
                        ? "Data ditahan; perlu review."
                        : "Memulihkan data…"}
                </p>
                {note}
            </Screen>
        );

    /* 1. POD sudah tersimpan: ringkasan baca-saja, riwayat, koreksi bila ditolak. */
    if (done && saved) {
        const pod =
            saved.command.type === "delivery.pod.submit"
                ? saved.command.payload
                : undefined;
        return (
            <Screen
                label={`Delivery ${task.id}`}
                class={frame}
                header={
                    <ScreenHeader
                        title={headerTitle}
                        onBack={close}
                        status={{ tone: "ok", label: "Session closed" }}
                    />
                }
                footer={
                    businessRejected(saved) ? (
                        <Button
                            variant="sec"
                            disabled={busy}
                            onClick={() => void startCorrection()}
                        >
                            Koreksi POD ditolak
                        </Button>
                    ) : undefined
                }
            >
                {note}
                <Callout tone="info" icon="check">
                    Session closed · POD tersimpan ·{" "}
                    {saved.command.client_uuid.slice(0, 8)}. Status terbaru ada
                    di Lainnya. Menunggu review; bukan picking selesai.
                </Callout>
                {pod ? (
                    <Card>
                        <CardHead
                            title="Ringkasan penerimaan"
                            status={{
                                tone:
                                    pod.outcome === "delivered" ? "ok" : "warn",
                                label: outcomeLabel[pod.outcome],
                            }}
                        />
                        <KV label="Penerima" value={pod.recipient} />
                        {pod.correction_reason ? (
                            <KV
                                label="Alasan koreksi"
                                value={`${pod.correction_reason} · atas ${pod.supersedes_uuid?.slice(0, 8)}`}
                            />
                        ) : null}
                        {pod.lines.map((line) => {
                            const src = task.lines.find(
                                (l) => l.id === line.id,
                            );
                            return (
                                <ListRow
                                    key={line.id}
                                    title={src?.name ?? line.id}
                                    sub={`Diterima ${line.received} / ${src?.quantity} ${src?.unit} · alasan: ${line.item_reason ?? line.reason ?? "legacy"}${line.item_note && line.item_note !== line.item_reason ? ` · ${line.item_note}` : ""}`}
                                    divider
                                />
                            );
                        })}
                        {pod.reason ? (
                            <KV label="Catatan" value={pod.reason} />
                        ) : null}
                    </Card>
                ) : null}
                {pod ? (
                    <Card>
                        <EvidenceCapture
                            store={store}
                            owner={owner}
                            existingRef={pod.evidence}
                            readOnly
                            onChange={() => {}}
                        />
                    </Card>
                ) : null}
                {history.length > 1 ? (
                    <Card>
                        <CardHead title={`Riwayat POD (${history.length})`} />
                        {history.map((h) => (
                            <ListRow
                                key={h.key}
                                divider
                                title={`${h.command.client_uuid.slice(0, 8)} · ${
                                    {
                                        queued: "Menunggu sync",
                                        sending: "Mengirim",
                                        accepted: "Diterima simulator",
                                        needs_approval: "Menunggu approval",
                                        rejected: "Ditolak",
                                        auth_required: "Sesi diperlukan",
                                    }[h.state]
                                }`}
                                sub={
                                    h.command.type === "delivery.pod.submit"
                                        ? `${h.command.payload.recipient} · ${outcomeLabel[h.command.payload.outcome]} · ${h.command.payload.lines
                                              .map((l) => {
                                                  const src =
                                                      h.command.type ===
                                                      "delivery.pod.submit"
                                                          ? h.command.payload.source.lines.find(
                                                                (x) =>
                                                                    x.id ===
                                                                    l.id,
                                                            )
                                                          : undefined;
                                                  return `${src?.name ?? l.id}: ${l.received} ${src?.unit ?? "unit tidak tersedia"}`;
                                              })
                                              .join(
                                                  "; ",
                                              )}${h.command.payload.correction_reason ? ` · ${h.command.payload.correction_reason}` : ""}`
                                        : undefined
                                }
                            />
                        ))}
                    </Card>
                ) : null}
            </Screen>
        );
    }

    /* 2. Check-in toko (workflow v2 tanpa sesi aktif). */
    if (task.workflow_version === 2 && !session)
        return (
            <Screen
                label={`Delivery ${task.id}`}
                class={frame}
                header={
                    <ScreenHeader
                        title={`Check-in · ${task.outlet}`}
                        onBack={close}
                    />
                }
                footer={
                    <Button
                        icon="pin"
                        disabled={!opening || !pinpoint || locating || busy}
                        onClick={() => {
                            setBusy(true);
                            setMessage("");
                            void (async () => {
                                requireVisitFix(pinpoint!, task.site);
                                const daily = await store.draft(
                                    owner,
                                    MORNING_KEY,
                                );
                                const value = DeliverySessionSchema.parse({
                                    id: crypto.randomUUID(),
                                    owner,
                                    task_id: task.id,
                                    opened_at: new Date().toISOString(),
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
                    </Button>
                }
            >
                {note}
                <p class="ui-sub">{task.address}</p>
                <Card>
                    <CheckinMap
                        site={{
                            ...task.site,
                            name: task.outlet,
                            simulated: __DEMO__,
                        }}
                        fix={
                            locationPreview
                                ? {
                                      ...locationPreview,
                                      simulated: locationSimulated,
                                  }
                                : undefined
                        }
                        compact
                    />
                </Card>
                <Card>
                    <EvidenceCapture
                        store={store}
                        owner={owner}
                        existingRef={opening}
                        onChange={(ref) => {
                            setOpening(ref);
                            setPinpoint(undefined);
                        }}
                    />
                </Card>
                <Button
                    variant="sec"
                    size="md"
                    disabled={locating || busy}
                    onClick={() => void locateDelivery()}
                >
                    Perbarui lokasi delivery
                </Button>
                {pinpoint ? (
                    <Callout tone="info" icon="pin">
                        Pinpoint {pinpoint.latitude.toFixed(6)},{" "}
                        {pinpoint.longitude.toFixed(6)} · ±{pinpoint.accuracy} m
                    </Callout>
                ) : null}
            </Screen>
        );

    /* 3. Hub toko (Delivery_hub): tracker + langkah toko. */
    const hub = (
        <Screen
            label={`Delivery ${task.id}`}
            class={frame}
            header={
                <ScreenHeader
                    title={headerTitle}
                    onBack={close}
                    status={{ tone: "info", label: "Berjalan" }}
                />
            }
            sub={
                <Tracker
                    label={`Tahap ${task.id}`}
                    steps={[
                        { label: "Check-in", state: "done" },
                        { label: "Serah terima", state: "cur" },
                        { label: "Tagihan", state: "future" },
                        { label: "Biaya", state: "future" },
                        { label: "Selesai", state: "future" },
                    ]}
                />
            }
            footer={
                <Button icon="truck" onClick={() => setForm(true)}>
                    {revision ? "Mulai koreksi POD" : "Mulai serah terima"}
                </Button>
            }
        >
            {!form ? note : null}
            {revision ? (
                <Callout tone="warn">
                    Koreksi atas {revision.command.client_uuid.slice(0, 8)}.
                    Pengajuan sebelumnya tetap tersimpan. Foto baru wajib.
                </Callout>
            ) : null}
            <Card tight>
                <ListRow
                    icon="truck"
                    title="Serah terima"
                    sub={`Drop ${drop} (${totalPcs.toLocaleString("id-ID")} unit)`}
                    status={{ tone: "warn", label: "Belum" }}
                />
                {collect ? (
                    <ListRow
                        divider
                        icon="wallet"
                        title="Tagihan"
                        sub="Catat pembayaran faktur toko"
                        onClick={collect}
                    />
                ) : null}
                <ListRow
                    divider
                    icon="receipt"
                    title="Biaya operasional toko"
                    sub="Parkir, kuli bongkar, retribusi"
                    onClick={() => setBiayaOpen(true)}
                />
                <ListRow
                    divider
                    icon="camera"
                    title="Foto bukti · tanda tangan opsional"
                    sub="Di langkah serah terima"
                    status={{ tone: "warn", label: "Wajib" }}
                />
            </Card>
            {session ? (
                <p class="ui-sub">
                    Sesi delivery aktif · {session.id.slice(0, 8)}
                </p>
            ) : null}
        </Screen>
    );

    /* 4. Serah terima (Pod_semua / Pod_sebagian / Pod_tolak). */
    const days =
        outcome === "pending_requested" &&
        z.iso.date().safeParse(requestedDate).success
            ? Math.round(
                  (Date.parse(`${requestedDate}T00:00:00Z`) -
                      Date.parse(`${task.business_date}T00:00:00Z`)) /
                      86400000,
              )
            : undefined;
    const serah = (
        <Screen
            label={`Serah terima ${task.id}`}
            class={frame}
            header={
                <ScreenHeader
                    title={`Serah terima · ${task.outlet}`}
                    onBack={() => setForm(false)}
                />
            }
            footer={
                <>
                    <Button
                        icon="check"
                        disabled={!photo || busy}
                        onClick={() => void action(true)}
                    >
                        Selesai serah terima
                    </Button>
                    <Button
                        variant="sec"
                        size="md"
                        disabled={!photo || busy}
                        onClick={() => void action(false)}
                    >
                        Simpan draft POD
                    </Button>
                </>
            }
        >
            <fieldset disabled={busy} class="ui-fieldset">
                <Segmented<Mode>
                    label="Hasil serah terima"
                    value={mode}
                    onChange={chooseMode}
                    items={[
                        { value: "full", label: "Terima semua" },
                        { value: "partial", label: "Sebagian" },
                        { value: "reject", label: "Tolak" },
                    ]}
                />
                {note}
                {revision ? (
                    <Textarea
                        label="Alasan koreksi"
                        value={correctionReason}
                        maxLength={500}
                        onInput={setCorrectionReason}
                    />
                ) : null}
                {mode === "full" ? (
                    <Card>
                        {task.lines.map((l, i) => (
                            <ListRow
                                key={l.id}
                                divider={i > 0}
                                title={l.name}
                                sub={`Dipesan ${l.quantity} ${l.unit}`}
                                status={{
                                    tone: "ok",
                                    label: `Diterima ${l.quantity} ${l.unit}`,
                                }}
                            />
                        ))}
                        <KV
                            label="Total"
                            value={`${totalPcs.toLocaleString("id-ID")} unit`}
                        />
                    </Card>
                ) : null}
                {mode === "partial"
                    ? task.lines.map((l, i) => (
                          <Card key={l.id}>
                              <CardHead title={l.name} />
                              <Field
                                  label={`Diterima ${l.name}`}
                                  value={lines[i].received}
                                  inputMode="numeric"
                                  maxLength={4}
                                  hint={`Dipesan ${l.quantity} ${l.unit}${
                                      lines[i].received < l.quantity
                                          ? ` · ditolak ${l.quantity - lines[i].received}`
                                          : ""
                                  }`}
                                  onInput={(v) =>
                                      receive(i, Number(v.replace(/\D/g, "")))
                                  }
                              />
                              {lines[i].received < l.quantity ? (
                                  <>
                                      <Select
                                          label={`Alasan item ${l.name} (wajib)`}
                                          value={lines[i].item_reason ?? ""}
                                          placeholder="Pilih alasan item"
                                          options={DeliveryItemReasonSchema.options.map(
                                              (r) => ({
                                                  value: r,
                                                  label: r,
                                              }),
                                          )}
                                          onChange={(v) =>
                                              setLines((prev) =>
                                                  prev.map((line, j) =>
                                                      j === i
                                                          ? {
                                                                ...line,
                                                                item_reason:
                                                                    (v ||
                                                                        undefined) as typeof line.item_reason,
                                                            }
                                                          : line,
                                                  ),
                                              )
                                          }
                                      />
                                      <Field
                                          label={`Catatan item ${l.name}`}
                                          value={lines[i].reason}
                                          maxLength={500}
                                          onInput={(v) =>
                                              setLines((prev) =>
                                                  prev.map((a, j) =>
                                                      j === i
                                                          ? { ...a, reason: v }
                                                          : a,
                                                  ),
                                              )
                                          }
                                      />
                                  </>
                              ) : null}
                          </Card>
                      ))
                    : null}
                {mode === "reject" ? (
                    <>
                        <Card>
                            <KV
                                label="Dipesan"
                                value={`${totalPcs.toLocaleString("id-ID")} unit`}
                            />
                            <KV label="Diterima" value="0" />
                            <Chip tone="bad">Ditolak semua</Chip>
                        </Card>
                        <Card>
                            <CardHead title="Alasan penolakan" />
                            {DeliveryDoReasonSchema.options.map((r) => (
                                <RadioRow
                                    key={r}
                                    name={`alasan-do-${task.id}`}
                                    value={r}
                                    label={doReasonLabel(r)}
                                    selected={doReason === r}
                                    onSelect={chooseDoReason}
                                />
                            ))}
                        </Card>
                        {outcome === "pending_requested" ? (
                            <Field
                                label="Tanggal kirim ulang"
                                type="date"
                                value={requestedDate}
                                onInput={setRequestedDate}
                                hint={
                                    days !== undefined
                                        ? `${days} hari: ${days < 3 ? "butuh approval SPV." : "butuh approval SPV lalu Branch Manager."}`
                                        : "Kurang dari 3 hari: SPV; 3 hari atau lebih: SPV lalu Branch Manager."
                                }
                            />
                        ) : null}
                    </>
                ) : null}
                <Field
                    label="Penerima"
                    value={recipient}
                    maxLength={100}
                    onInput={setRecipient}
                />
                <Textarea
                    label={
                        mode === "partial"
                            ? "Catatan umum (alasan wajib per item terdampak)"
                            : "Catatan serah terima"
                    }
                    value={reason}
                    maxLength={500}
                    onInput={setReason}
                />
                <Card>
                    <EvidenceCapture
                        store={store}
                        owner={owner}
                        existingRef={photo}
                        onChange={setPhoto}
                    />
                </Card>
                {formError ? (
                    <Callout tone="bad" alert>
                        {formError}
                    </Callout>
                ) : null}
                {mode === "partial" ? (
                    <ActionCaption>
                        Alasan rusak atau expired wajib disertai foto.
                    </ActionCaption>
                ) : null}
            </fieldset>
        </Screen>
    );
    return (
        <>
            {hub}
            {form ? serah : null}
            {biayaOpen ? (
                <BiayaTokoScreen
                    snapshot={snapshot}
                    outlet={{ id: task.outlet_id, name: task.outlet }}
                    businessDate={task.business_date}
                    owner={owner}
                    store={store}
                    submit={submit}
                    close={() => setBiayaOpen(false)}
                />
            ) : null}
        </>
    );
}
