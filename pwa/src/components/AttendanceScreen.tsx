import { useEffect, useMemo, useRef, useState } from "preact/hooks";
import type { Identity, Snapshot } from "../domain/contracts";
import { distanceMeters } from "../domain/format";
import { renderEvidencePackage } from "../domain/evidence-render";
import { isDemoMode } from "../domain/running-mode";
import type { MapFix } from "../domain/checkin-map";
import type { FieldStore } from "../storage/store";
import {
    ActionCaption,
    BottomSheet,
    Button,
    Callout,
    Card,
    Chip,
    Field,
    IconButton,
    ListRow,
    Screen,
    ScreenHeader,
} from "../ui";
import { useBackLayer } from "../ui/navigation";
import { CameraViewfinder, type CameraCaptureResult } from "./CameraViewfinder";
import { CheckinMap } from "./CheckinMap";
import type { EvidenceRef } from "./Evidence";

/** Batas akurasi GPS untuk absen dan check-in (DS: Status_gps). */
export const GPS_ACCURACY_LIMIT_M = 30;

/**
 * Layar penuh absen masuk/pulang (DS: Absen_info, Absen_dalam, Absen_luar, Absen_selfie, Absen_pulang).
 * Alur: lokasi → status area → Ambil selfie (kamera depan, terkunci di luar area) → Selfie tersimpan → simpan.
 * Bukti tetap lokal: hash, watermark, dan kedaluwarsa lokasi 60 detik tidak berubah.
 */
export function AttendanceScreen({
    event,
    store,
    owner,
    identity,
    office,
    startSession,
    close,
}: {
    event: "check_in" | "check_out";
    store: FieldStore;
    owner: string;
    identity: Identity;
    office?: Snapshot["office"];
    startSession: (
        event: "check_in" | "check_out",
        evidence: EvidenceRef,
    ) => Promise<void>;
    close: () => void;
}) {
    const [evidence, setEvidence] = useState<EvidenceRef>();
    const [fix, setFix] = useState<MapFix & { timestamp: number }>();
    const [address, setAddress] = useState("");
    const [photo, setPhoto] = useState<Blob>();
    const [captured, setCaptured] = useState("");
    const [camera, setCamera] = useState(false);
    const [rules, setRules] = useState(false);
    const [notice, setNotice] = useState<"accuracy" | "denied">();
    const [working, setWorking] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");
    const generation = useRef(0);
    useBackLayer(true, close);
    const opener = useRef<Element | null>(document.activeElement);
    useEffect(
        () => () => {
            const el = opener.current;
            if (el instanceof HTMLElement && el.isConnected)
                setTimeout(() => el.focus(), 0);
        },
        [],
    );
    const pulang = event === "check_out";
    const companyName =
        identity.companyName ?? `Perusahaan #${identity.companyId}`;
    const mapSite = office
        ? { ...office, simulated: office.coordinate_status !== "verified" }
        : undefined;
    // Area hanya mengunci bila titik master terverifikasi dan bukan mode demo (selaras CameraViewfinder).
    const enforced = !!mapSite && !mapSite.simulated && !isDemoMode();
    const distance =
        fix && mapSite
            ? distanceMeters(
                  fix.latitude,
                  fix.longitude,
                  mapSite.latitude,
                  mapSite.longitude,
              )
            : undefined;
    const beyond =
        distance !== undefined && mapSite
            ? Math.max(0, Math.round(distance - mapSite.radius))
            : 0;
    const outside = beyond > 0;
    const blocked = enforced && outside;
    // Akurasi di atas batas mengunci selfie (kecuali mode demo), selaras DS Status_gps.
    const lowAccuracy =
        !!fix && !isDemoMode() && fix.accuracy > GPS_ACCURACY_LIMIT_M;

    function locate(precise: boolean) {
        const ticket = ++generation.current;
        setEvidence(undefined);
        setPhoto(undefined);
        setCaptured("");
        setWorking(true);
        setError("");
        if (!navigator.geolocation) {
            setWorking(false);
            setError("Lokasi tidak didukung perangkat ini.");
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (position) => {
                if (ticket !== generation.current) return;
                setFix({
                    latitude: position.coords.latitude,
                    longitude: position.coords.longitude,
                    accuracy: position.coords.accuracy,
                    timestamp: position.timestamp,
                });
                if (
                    !isDemoMode() &&
                    position.coords.accuracy > GPS_ACCURACY_LIMIT_M
                )
                    setNotice("accuracy");
                setWorking(false);
            },
            (failure) => {
                if (ticket !== generation.current) return;
                setWorking(false);
                setFix(undefined);
                if (failure.code === 1) setNotice("denied");
                setError(
                    failure.code === 1
                        ? "Izin lokasi ditolak. Aktifkan izin lokasi di browser."
                        : "Lokasi belum diperoleh. Coba kembali.",
                );
            },
            {
                enableHighAccuracy: precise,
                maximumAge: precise ? 0 : 30000,
                timeout: 12000,
            },
        );
    }
    useEffect(() => {
        locate(false);
        return () => {
            generation.current++;
        };
    }, []);
    // URL diturunkan sinkron dari foto aktif: gambar yang tampil tidak pernah tertinggal dari bukti yang disimpan.
    const preview = useMemo(
        () => (photo ? URL.createObjectURL(photo) : ""),
        [photo],
    );
    useEffect(
        () => () => {
            if (preview) URL.revokeObjectURL(preview);
        },
        [preview],
    );

    async function capture(result: CameraCaptureResult) {
        setCamera(false);
        if (!fix) return;
        const ticket = ++generation.current;
        setWorking(true);
        setError("");
        setEvidence(undefined);
        try {
            if (!isDemoMode() && Date.now() - fix.timestamp > 60000)
                throw new Error(
                    "Lokasi kedaluwarsa. Perbarui lokasi, lalu foto ulang.",
                );
            const at = new Date(result.timestamp).toISOString();
            const ref = {
                id: crypto.randomUUID(),
                latitude: fix.latitude,
                longitude: fix.longitude,
                accuracy: fix.accuracy,
                capturedAt: at,
            };
            const row = await renderEvidencePackage(
                result.blob,
                owner,
                ref,
                at,
                new Date(fix.timestamp).toISOString(),
                __DEMO__ || isDemoMode(),
                {
                    company: companyName,
                    employee: identity.name,
                    address: address.trim(),
                },
            );
            if (ticket !== generation.current) return;
            await store.saveEvidence(row);
            if (ticket !== generation.current) return;
            setPhoto(row.blob);
            setCaptured(at);
            setEvidence({ ...ref, packageHash: row.visual!.bindingSha256 });
        } catch (failure) {
            if (ticket === generation.current) {
                // Tanpa bukti aktif, kembali ke langkah lokasi agar Perbarui lokasi tersedia (tidak buntu).
                setPhoto(undefined);
                setCaptured("");
                setError(
                    failure instanceof Error
                        ? failure.message
                        : "Foto gagal disimpan. Coba kembali.",
                );
            }
        } finally {
            if (ticket === generation.current) setWorking(false);
        }
    }
    async function save() {
        if (!evidence || saving) return;
        setSaving(true);
        setError("");
        try {
            await startSession(event, evidence);
            close();
        } catch (failure) {
            setError(
                failure instanceof Error
                    ? failure.message
                    : "Absen belum tersimpan. Coba lagi.",
            );
        } finally {
            setSaving(false);
        }
    }
    const busy = working || saving;
    const chip = !fix ? (
        <Chip tone="neu" icon="pin">
            {working ? "Mencari lokasi…" : "Lokasi belum diperoleh"}
        </Chip>
    ) : !mapSite ? null : outside ? (
        <Chip tone="warn" icon="warning">
            Di luar area · {beyond} m dari batas
            {enforced ? "" : " (diabaikan: titik uji/demo)"}
        </Chip>
    ) : (
        <Chip tone="ok" icon="check">
            Di dalam area · {Math.round(distance!)} m dari titik absen
        </Chip>
    );
    const time = captured
        ? `${new Date(captured).toLocaleString("id-ID", { timeZone: "Asia/Makassar" })} WITA`
        : "";
    return (
        <Screen
            label="Absensi foto dan lokasi"
            header={
                <ScreenHeader
                    title={pulang ? "Absen pulang" : "Absen masuk"}
                    onBack={() => {
                        if (!busy) close();
                    }}
                    right={
                        <IconButton
                            icon="info"
                            label="Aturan geofence"
                            onClick={() => setRules(true)}
                        />
                    }
                />
            }
            footer={
                photo ? (
                    <>
                        <Button
                            icon="check"
                            disabled={busy || !evidence}
                            onClick={() => void save()}
                        >
                            {saving
                                ? "Menyimpan…"
                                : pulang
                                  ? "Absen pulang"
                                  : "Absen masuk"}
                        </Button>
                        <ActionCaption>
                            Foto dan lokasi tersimpan di perangkat · belum
                            diverifikasi server.
                        </ActionCaption>
                    </>
                ) : (
                    <>
                        <Button
                            variant="sec"
                            icon="pin"
                            disabled={busy}
                            onClick={() => locate(true)}
                        >
                            Perbarui lokasi
                        </Button>
                        <Button
                            icon="camera"
                            disabled={
                                busy ||
                                !fix ||
                                !address.trim() ||
                                !mapSite ||
                                blocked ||
                                lowAccuracy
                            }
                            onClick={() => setCamera(true)}
                        >
                            {pulang ? "Ambil selfie pulang" : "Ambil selfie"}
                        </Button>
                    </>
                )
            }
        >
            <section
                class="attendance-capture"
                aria-label="Lokasi dan foto absensi"
                aria-busy={busy}
            >
                {photo ? (
                    <>
                        <div class="att-selfie">
                            <img
                                src={preview}
                                class="att-selfie__img"
                                alt="Foto absensi dengan watermark"
                            />
                            <span class="att-selfie__cap">
                                Selfie tersimpan
                            </span>
                        </div>
                        <Card>
                            <ListRow
                                icon="pin"
                                title="Lokasi"
                                sub={address}
                                status={
                                    mapSite
                                        ? outside
                                            ? {
                                                  tone: "warn",
                                                  label: "Di luar area",
                                              }
                                            : {
                                                  tone: "ok",
                                                  label: "Di dalam area",
                                              }
                                        : undefined
                                }
                            />
                            <ListRow
                                icon="clock"
                                title="Waktu"
                                sub={time}
                                divider
                            />
                        </Card>
                        <Button
                            variant="sec"
                            icon="camera"
                            disabled={busy}
                            onClick={() => setCamera(true)}
                        >
                            Ulangi foto
                        </Button>
                    </>
                ) : (
                    <>
                        {mapSite ? (
                            <CheckinMap compact site={mapSite} fix={fix} />
                        ) : (
                            <Callout tone="warn">
                                Master lokasi kantor belum tersedia. Hubungi
                                admin.
                            </Callout>
                        )}
                        {chip}
                        {blocked ? (
                            <Card>
                                <strong>
                                    Absen hanya bisa di dalam area kantor.
                                </strong>
                                <span>
                                    Dekati titik absen, lalu perbarui lokasi.
                                </span>
                            </Card>
                        ) : null}
                        {lowAccuracy ? (
                            <Callout tone="warn" icon="warning">
                                Akurasi saat ini ±{Math.round(fix!.accuracy)} m.
                                Batas untuk absen dan check-in adalah ±
                                {GPS_ACCURACY_LIMIT_M} m.
                            </Callout>
                        ) : null}
                        {fix ? (
                            <p class="ev__fix">
                                {fix.latitude.toFixed(6)},{" "}
                                {fix.longitude.toFixed(6)} · ±
                                {Math.round(fix.accuracy)} m
                            </p>
                        ) : null}
                        <Field
                            label="Alamat / nama lokasi"
                            value={address}
                            maxLength={140}
                            required
                            placeholder="Alamat lengkap lokasi Anda saat ini"
                            disabled={busy || camera}
                            onInput={setAddress}
                        />
                    </>
                )}
                {busy ? <p role="status">Menyiapkan bukti…</p> : null}
                {error ? (
                    <Callout tone="bad" alert>
                        {error}
                    </Callout>
                ) : null}
            </section>
            {camera ? (
                <CameraViewfinder
                    rawCapture
                    initialFacing="user"
                    title="Foto absensi"
                    salespersonName={identity.name}
                    outletName={mapSite?.name}
                    fence={
                        enforced && mapSite
                            ? {
                                  latitude: mapSite.latitude,
                                  longitude: mapSite.longitude,
                                  radius: mapSite.radius,
                              }
                            : undefined
                    }
                    onCapture={(result) => void capture(result)}
                    onClose={() => setCamera(false)}
                />
            ) : null}
            {notice === "accuracy" && fix ? (
                <BottomSheet
                    title="Akurasi lokasi rendah"
                    onClose={() => setNotice(undefined)}
                >
                    <Callout tone="warn" icon="warning">
                        Akurasi saat ini ±{Math.round(fix.accuracy)} m. Batas
                        untuk absen dan check-in adalah ±{GPS_ACCURACY_LIMIT_M}{" "}
                        m.
                    </Callout>
                    <p class="ui-sheet__text">
                        Pindah ke tempat terbuka, jauhi bangunan tinggi, lalu
                        coba lagi.
                    </p>
                    <Button
                        icon="sync"
                        onClick={() => {
                            setNotice(undefined);
                            locate(true);
                        }}
                    >
                        Coba lagi
                    </Button>
                    <Button variant="sec" onClick={() => setNotice(undefined)}>
                        Tutup
                    </Button>
                </BottomSheet>
            ) : null}
            {notice === "denied" ? (
                <BottomSheet
                    title="Akses lokasi ditolak"
                    onClose={() => setNotice(undefined)}
                >
                    <p class="ui-sheet__text">
                        Absen butuh lokasi. Buka pengaturan browser, izinkan
                        lokasi untuk aplikasi ini, lalu coba lagi. Berlaku juga
                        untuk kamera.
                    </p>
                    <Button
                        onClick={() => {
                            setNotice(undefined);
                            locate(true);
                        }}
                    >
                        Coba lagi
                    </Button>
                    <Button variant="sec" onClick={() => setNotice(undefined)}>
                        Tutup
                    </Button>
                </BottomSheet>
            ) : null}
            {rules ? (
                <BottomSheet
                    title="Aturan geofence"
                    onClose={() => setRules(false)}
                >
                    <Card tight>
                        <ListRow
                            icon="pin"
                            title="Area absen"
                            sub="Absen dan check-in sah hanya di dalam radius area."
                        />
                        <ListRow
                            icon="camera"
                            title="Hanya kamera"
                            sub="Foto langsung dari kamera, tanpa unggah galeri. Absen dan check-in wajib kamera depan."
                            divider
                        />
                        <ListRow
                            icon="info"
                            title="Peta"
                            sub="Peta hanya panduan; validasi dilakukan server."
                            divider
                        />
                    </Card>
                    <Button onClick={() => setRules(false)}>Mengerti</Button>
                </BottomSheet>
            ) : null}
        </Screen>
    );
}
