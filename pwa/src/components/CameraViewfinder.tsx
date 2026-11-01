import { useDialog } from "../ui/useDialog";
import { useBackLayer } from "../ui/navigation";
import { useEffect, useRef, useState } from "preact/hooks";
import { Icon } from "./Icon";

export interface CameraCaptureResult {
    blob: Blob;
    timestamp: number;
    fixTimestamp: number;
    latitude: number;
    longitude: number;
    accuracy: number;
    simulated?: boolean;
}

interface CameraViewfinderProps {
    title?: string;
    outletName?: string;
    salespersonName?: string;
    defaultCoordinates?: { latitude: number; longitude: number };
    rawCapture?: boolean;
    onCapture: (result: CameraCaptureResult) => void;
    onClose: () => void;
}

export function CameraViewfinder({
    title = "Kamera Bukti Lapangan",
    outletName,
    salespersonName = "Petugas",
    defaultCoordinates,
    onCapture,
    onClose,
    rawCapture = false,
}: CameraViewfinderProps) {
    const dialogRef = useDialog<HTMLDivElement>(onClose);
    useBackLayer(true, onClose);
    const videoRef = useRef<HTMLVideoElement>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const [cameraActive, setCameraActive] = useState(false);
    const [cameraError, setCameraError] = useState("");
    const [facingMode, setFacingMode] = useState<"environment" | "user">(
        "environment",
    );
    const [hasMultipleCameras, setHasMultipleCameras] = useState(false);
    const [capturing, setCapturing] = useState(false);

    // Geolocation state
    const [coords, setCoords] = useState<{
        latitude: number;
        longitude: number;
        accuracy: number;
        timestamp: number;
        simulated?: boolean;
    }>(() => ({
        latitude: defaultCoordinates?.latitude ?? 1.487,
        longitude: defaultCoordinates?.longitude ?? 124.8428,
        accuracy: 10,
        timestamp: Date.now(),
        simulated: true,
    }));
    const [gpsStatus, setGpsStatus] = useState<
        "acquiring" | "locked" | "fallback"
    >("acquiring");

    // Real-time clock formatted in WITA (Asia/Makassar)
    const [currentTime, setCurrentTime] = useState("");

    useEffect(() => {
        function updateClock() {
            const now = new Date();
            setCurrentTime(
                new Intl.DateTimeFormat("id-ID", {
                    dateStyle: "medium",
                    timeStyle: "medium",
                    timeZone: "Asia/Makassar",
                }).format(now) + " WITA",
            );
        }
        updateClock();
        const timer = setInterval(updateClock, 1000);
        return () => clearInterval(timer);
    }, []);

    // Track GPS
    useEffect(() => {
        let watchId: number | undefined;
        if ("geolocation" in navigator) {
            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    setCoords({
                        latitude: pos.coords.latitude,
                        longitude: pos.coords.longitude,
                        accuracy: pos.coords.accuracy,
                        timestamp: pos.timestamp,
                        simulated: false,
                    });
                    setGpsStatus("locked");
                },
                () => {
                    setGpsStatus("fallback");
                },
                { enableHighAccuracy: true, timeout: 8000, maximumAge: 10000 },
            );

            watchId = navigator.geolocation.watchPosition(
                (pos) => {
                    setCoords({
                        latitude: pos.coords.latitude,
                        longitude: pos.coords.longitude,
                        accuracy: pos.coords.accuracy,
                        timestamp: pos.timestamp,
                        simulated: false,
                    });
                    setGpsStatus("locked");
                },
                () => {
                    // keep existing coords
                },
                { enableHighAccuracy: true, timeout: 15000, maximumAge: 5000 },
            );
        } else {
            setGpsStatus("fallback");
        }

        return () => {
            if (watchId !== undefined && "geolocation" in navigator) {
                navigator.geolocation.clearWatch(watchId);
            }
        };
    }, []);

    // Check available cameras
    useEffect(() => {
        if (navigator.mediaDevices?.enumerateDevices) {
            navigator.mediaDevices
                .enumerateDevices()
                .then((devices) => {
                    const videoDevices = devices.filter(
                        (d) => d.kind === "videoinput",
                    );
                    setHasMultipleCameras(videoDevices.length > 1);
                })
                .catch(() => {});
        }
    }, []);

    // Start video stream
    useEffect(() => {
        let isCancelled = false;

        async function startStream() {
            setCameraError("");
            if (streamRef.current) {
                streamRef.current.getTracks().forEach((track) => track.stop());
                streamRef.current = null;
            }

            if (!navigator.mediaDevices?.getUserMedia) {
                setCameraError(
                    "Kamera langsung tidak didukung browser ini. Gunakan pemicu kamera perangkat.",
                );
                return;
            }

            try {
                let stream: MediaStream;
                try {
                    stream = await navigator.mediaDevices.getUserMedia({
                        video: {
                            facingMode: { ideal: facingMode },
                            width: { ideal: 1920, min: 640 },
                            height: { ideal: 1080, min: 480 },
                        },
                        audio: false,
                    });
                } catch {
                    // Fallback to basic video constraints
                    stream = await navigator.mediaDevices.getUserMedia({
                        video: true,
                        audio: false,
                    });
                }

                if (isCancelled) {
                    stream.getTracks().forEach((track) => track.stop());
                    return;
                }

                streamRef.current = stream;
                if (videoRef.current) {
                    videoRef.current.srcObject = stream;
                    await videoRef.current.play().catch(() => {});
                }
                setCameraActive(true);
            } catch (err) {
                if (isCancelled) return;
                const message =
                    err instanceof Error ? err.message : String(err);
                if (
                    message.includes("Permission") ||
                    message.includes("denied")
                ) {
                    setCameraError(
                        "Izin kamera ditolak. Berikan izin kamera di pengaturan browser.",
                    );
                } else if (
                    message.includes("NotFound") ||
                    message.includes("Requested device not found") ||
                    message.includes("DevicesNotFoundError")
                ) {
                    setCameraError("Tidak ditemukan perangkat kamera fisik.");
                } else {
                    setCameraError(
                        "Kamera belum dapat dibuka. Tutup aplikasi kamera lain dan coba kembali.",
                    );
                }
                setCameraActive(false);
            }
        }

        void startStream();

        return () => {
            isCancelled = true;
            if (streamRef.current) {
                streamRef.current.getTracks().forEach((track) => track.stop());
                streamRef.current = null;
            }
        };
    }, [facingMode]);

    function stopAndClose() {
        if (streamRef.current) {
            streamRef.current.getTracks().forEach((track) => track.stop());
            streamRef.current = null;
        }
        onClose();
    }

    async function stampAndExport(
        source: CanvasImageSource,
        sourceWidth: number,
        sourceHeight: number,
    ): Promise<Blob> {
        const targetWidth = Math.max(800, sourceWidth);
        const scale = targetWidth / sourceWidth;
        const targetHeight = Math.round(sourceHeight * scale);

        const bannerHeight = rawCapture ? 0 : 110;
        const totalHeight = targetHeight + bannerHeight;

        const canvas = document.createElement("canvas");
        canvas.width = targetWidth;
        canvas.height = totalHeight;

        const ctx = canvas.getContext("2d");
        if (!ctx) throw new Error("Gagal membuat canvas watermark.");

        // Draw image frame
        ctx.drawImage(source, 0, 0, targetWidth, targetHeight);

        if (!rawCapture) {
            // Watermark Banner Background (Dark FMCG theme)
            ctx.fillStyle = "#0a192f";
            ctx.fillRect(0, targetHeight, targetWidth, bannerHeight);

            // Top accent line in gold/amber
            ctx.fillStyle = "#f59e0b";
            ctx.fillRect(0, targetHeight, targetWidth, 4);

            // Text styling
            ctx.fillStyle = "#ffffff";
            ctx.textBaseline = "middle";

            // Line 1: outlet & document context
            ctx.font =
                "bold 20px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
            const outletText = outletName
                ? `BUKTI DISPLAY · ${outletName}`
                : "BUKTI KUNJUNGAN LAPANGAN";
            ctx.fillText(outletText, 20, targetHeight + 28);

            // Line 2: Timestamp & GPS Coordinates
            ctx.font =
                "16px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
            ctx.fillStyle = "#cbd5e1";
            const timeText =
                currentTime || `${new Date().toLocaleTimeString("id-ID")} WITA`;
            const coordText = `GPS: ${coords.latitude.toFixed(6)}, ${coords.longitude.toFixed(6)} (±${Math.round(coords.accuracy)}m)`;
            ctx.fillText(
                `${timeText}   |   ${coordText}`,
                20,
                targetHeight + 58,
            );

            // Line 3: Officer Name & Verification Badge
            ctx.font =
                "14px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
            ctx.fillStyle = "#94a3b8";
            const officerText = `Petugas: ${salespersonName}   |   Status: bukti lokal, belum diverifikasi`;
            ctx.fillText(officerText, 20, targetHeight + 86);
        }
        // Convert to Blob
        return new Promise<Blob>((resolve, reject) => {
            canvas.toBlob(
                (blob) => {
                    if (blob) resolve(blob);
                    else
                        reject(
                            new Error("Gagal menghasilkan foto ber-watermark."),
                        );
                },
                "image/jpeg",
                0.86,
            );
        });
    }

    async function handleCapture() {
        if (!videoRef.current || capturing) return;
        setCapturing(true);

        try {
            const video = videoRef.current;
            const w = video.videoWidth || 1280;
            const h = video.videoHeight || 720;

            const blob = await stampAndExport(video, w, h);

            if (streamRef.current) {
                streamRef.current.getTracks().forEach((track) => track.stop());
                streamRef.current = null;
            }

            onCapture({
                blob,
                timestamp: Date.now(),
                fixTimestamp: coords.timestamp,
                latitude: coords.latitude,
                longitude: coords.longitude,
                accuracy: coords.accuracy,
                simulated: coords.simulated,
            });
        } catch (err) {
            setCameraError(
                err instanceof Error ? err.message : "Gagal mengambil foto.",
            );
            setCapturing(false);
        }
    }

    // Direct device camera input fallback handler
    async function handleFallbackFile(file?: File) {
        if (!file) return;
        setCapturing(true);
        try {
            const bitmap = await createImageBitmap(file);
            const blob = await stampAndExport(
                bitmap,
                bitmap.width,
                bitmap.height,
            );
            bitmap.close();

            if (streamRef.current) {
                streamRef.current.getTracks().forEach((track) => track.stop());
                streamRef.current = null;
            }

            onCapture({
                blob,
                timestamp: Date.now(),
                fixTimestamp: coords.timestamp,
                latitude: coords.latitude,
                longitude: coords.longitude,
                accuracy: coords.accuracy,
                simulated: coords.simulated,
            });
        } catch (err) {
            setCameraError(
                err instanceof Error ? err.message : "Gagal memproses foto.",
            );
            setCapturing(false);
        }
    }

    return (
        <div
            class="camera-modal-backdrop"
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-label={title}
        >
            <div class="camera-modal-content">
                {/* Header bar */}
                <header class="camera-header">
                    <div>
                        <h3>{title}</h3>
                        <p class="camera-subtitle">
                            {outletName || "Bukti kunjungan lapangan"}
                        </p>
                    </div>
                    <button
                        type="button"
                        class="camera-close-button"
                        onClick={stopAndClose}
                        aria-label="Tutup kamera"
                    >
                        <Icon name="close" size={24} />
                    </button>
                </header>

                {/* Video Viewfinder Area */}
                <div class="camera-viewfinder-container">
                    {cameraError ? (
                        <div class="camera-error-container">
                            <Icon name="warning" size={40} />
                            <p class="camera-error-message">{cameraError}</p>
                            <label class="camera-fallback-btn">
                                <Icon name="camera" size={20} />
                                Buka Kamera Perangkat
                                <input
                                    type="file"
                                    accept="image/*"
                                    capture="environment"
                                    style={{ display: "none" }}
                                    onChange={(e) =>
                                        void handleFallbackFile(
                                            e.currentTarget.files?.[0],
                                        )
                                    }
                                />
                            </label>
                        </div>
                    ) : (
                        <>
                            <video
                                ref={videoRef}
                                class="camera-video"
                                playsinline
                                autoplay
                                muted
                            />

                            {/* Framing reticle */}
                            <div class="camera-reticle" aria-hidden="true">
                                <div class="reticle-corner top-left" />
                                <div class="reticle-corner top-right" />
                                <div class="reticle-corner bottom-left" />
                                <div class="reticle-corner bottom-right" />
                            </div>

                            {/* Live Metadata Badges */}
                            <div class="camera-live-overlay">
                                <div class="camera-badge time-badge">
                                    <Icon name="clock" size={14} />
                                    <span>{currentTime}</span>
                                </div>
                                <div
                                    class={`camera-badge gps-badge ${gpsStatus === "locked" ? "gps-locked" : "gps-searching"}`}
                                >
                                    <Icon name="pin" size={14} />
                                    <span>
                                        {gpsStatus === "locked"
                                            ? `${coords.latitude.toFixed(5)}, ${coords.longitude.toFixed(5)} (±${Math.round(coords.accuracy)}m)`
                                            : gpsStatus === "fallback"
                                              ? "GPS belum tersedia · titik simulasi"
                                              : "Mencari GPS…"}
                                    </span>
                                </div>
                            </div>
                        </>
                    )}
                </div>

                {/* Camera Controls Bar */}
                <footer class="camera-controls">
                    {hasMultipleCameras && cameraActive && !cameraError && (
                        <button
                            type="button"
                            class="camera-tool-button"
                            onClick={() =>
                                setFacingMode((m) =>
                                    m === "environment"
                                        ? "user"
                                        : "environment",
                                )
                            }
                            title="Balik kamera"
                        >
                            <Icon name="sync" size={22} />
                        </button>
                    )}

                    {cameraActive && !cameraError && (
                        <button
                            type="button"
                            class="camera-shutter-button"
                            onClick={() => void handleCapture()}
                            disabled={capturing}
                            aria-label="Ambil foto bukti"
                        >
                            <div class="shutter-inner" />
                        </button>
                    )}

                    <button
                        type="button"
                        class="camera-cancel-button"
                        onClick={stopAndClose}
                    >
                        Batal
                    </button>
                </footer>
            </div>
        </div>
    );
}
