import { useEffect, useState } from "preact/hooks";
import { checkinMap, type MapFix, type MapSite } from "../domain/checkin-map";
import { distanceMeters } from "../domain/format";

// Display-only: this component never authorizes a check-in or changes evidence.
export function CheckinMap({ site, fix }: { site: MapSite; fix?: MapFix }) {
    const scope = JSON.stringify([site, fix]);
    const [enabled, setEnabled] = useState(false);
    const [zoom, setZoom] = useState<number>();
    const [failed, setFailed] = useState(false);
    const [loaded, setLoaded] = useState<string[]>([]);
    useEffect(() => {
        setZoom(undefined);
        setEnabled(false);
        setFailed(false);
        setLoaded([]);
    }, [scope]);
    let map: ReturnType<typeof checkinMap> | undefined;
    try {
        map = checkinMap(site, fix, zoom);
    } catch {
        /* Keep hook order stable even for corrupt coordinates. */
    }
    const tileKey = map?.tiles.map((t) => t.key).join(",") ?? "";
    const ready = map?.tiles.every((t) => loaded.includes(t.key)) ?? false;
    useEffect(() => {
        if (!enabled || ready) return;
        const id = setTimeout(() => setFailed(true), 10000);
        return () => clearTimeout(id);
    }, [enabled, tileKey, ready]);
    if (!map)
        return (
            <p role="status">
                Preview peta tidak tersedia: koordinat tujuan/perangkat tidak
                valid.
            </p>
        );
    const distance = fix
        ? distanceMeters(
              site.latitude,
              site.longitude,
              fix.latitude,
              fix.longitude,
          )
        : undefined;
    const status = !fix
        ? "Posisi perangkat belum tersedia"
        : distance! + fix.accuracy <= site.radius
          ? "Di dalam radius"
          : distance! - fix.accuracy > site.radius
            ? "Di luar radius"
            : "Akurasi belum pasti";
    return (
        <section class="checkin-map" aria-label={`Preview peta ${site.name}`}>
            <strong>Preview peta · {site.name}</strong>
            {(site.simulated || fix?.simulated) && (
                <p class="notice">
                    MODE UJI ·{" "}
                    {site.simulated
                        ? "Titik tujuan simulasi"
                        : "Titik tujuan dari paket demo"}
                    {fix?.simulated
                        ? " · Posisi simulasi / akurasi placeholder"
                        : " · Posisi perangkat bila tersedia"}
                    . Bukan validasi kehadiran resmi.
                </p>
            )}
            <p>
                {status} · Radius {site.radius} m
                {distance !== undefined && (
                    <>
                        {" "}
                        · Jarak {Math.round(distance)} m · Akurasi ±
                        {Math.round(fix!.accuracy)} m
                    </>
                )}
            </p>
            <div class="checkin-map-canvas">
                {enabled &&
                    map.tiles.map((t) => (
                        <img
                            key={t.key}
                            src={t.url}
                            alt=""
                            referrerPolicy="strict-origin-when-cross-origin"
                            style={{
                                position: "absolute",
                                left: `${(t.x / 512) * 100}%`,
                                top: `${(t.y / 320) * 100}%`,
                                width: "50%",
                                height: "80%",
                                maxWidth: "none",
                            }}
                            onLoad={() =>
                                setLoaded((v) =>
                                    v.includes(t.key) ? v : [...v, t.key],
                                )
                            }
                            onError={() => setFailed(true)}
                        />
                    ))}
                <svg
                    viewBox="0 0 512 320"
                    role="img"
                    aria-label="Titik tujuan hijau, posisi perangkat biru, lingkaran radius dan akurasi"
                >
                    <circle
                        cx={map.site.x}
                        cy={map.site.y}
                        r={map.site.radius}
                        fill="#15803d22"
                        stroke="#15803d"
                        stroke-width="2"
                    />
                    {fix && (
                        <>
                            <line
                                x1={map.site.x}
                                y1={map.site.y}
                                x2={map.fix.x}
                                y2={map.fix.y}
                                stroke="#334155"
                                stroke-dasharray="5 4"
                            />
                            <circle
                                cx={map.fix.x}
                                cy={map.fix.y}
                                r={map.fix.radius}
                                fill="#2563eb22"
                                stroke="#2563eb"
                                stroke-dasharray="4 3"
                            />
                        </>
                    )}
                    <circle
                        cx={map.site.x}
                        cy={map.site.y}
                        r="7"
                        fill="#15803d"
                        stroke="white"
                        stroke-width="2"
                    />
                    {fix && (
                        <circle
                            cx={map.fix.x}
                            cy={map.fix.y}
                            r="5"
                            fill="#2563eb"
                            stroke="white"
                            stroke-width="2"
                        />
                    )}
                </svg>
            </div>
            <small>
                Status jarak geometris, bukan izin check-in. Hijau:
                tujuan/radius · Biru: posisi/akurasi. {site.latitude.toFixed(6)}
                , {site.longitude.toFixed(6)}
                {fix && (
                    <>
                        {" "}
                        · Posisi {fix.latitude.toFixed(6)},{" "}
                        {fix.longitude.toFixed(6)}
                    </>
                )}
            </small>
            {!enabled ? (
                <>
                    <p class="footnote">
                        Muat peta jalan menghubungi OpenStreetMap dan membagikan
                        area peta serta alamat IP. Foto dan identitas tidak
                        dikirim. Diagram titik tetap tersedia tanpa jaringan.
                    </p>
                    <button
                        type="button"
                        class="secondary"
                        onClick={() => {
                            setFailed(false);
                            setLoaded([]);
                            setEnabled(true);
                        }}
                    >
                        Muat peta jalan
                    </button>
                </>
            ) : (
                <>
                    <div class="map-controls">
                        <button
                            type="button"
                            class="secondary"
                            aria-label="Perbesar peta"
                            disabled={map.zoom >= 19}
                            onClick={() => {
                                setFailed(false);
                                setZoom(map.zoom + 1);
                            }}
                        >
                            +
                        </button>
                        <button
                            type="button"
                            class="secondary"
                            aria-label="Perkecil peta"
                            disabled={map.zoom <= 0}
                            onClick={() => {
                                setFailed(false);
                                setZoom(map.zoom - 1);
                            }}
                        >
                            −
                        </button>
                        <button
                            type="button"
                            class="secondary"
                            onClick={() => {
                                setFailed(false);
                                setZoom(undefined);
                            }}
                        >
                            Tampilkan kedua titik
                        </button>
                        <button
                            type="button"
                            class="secondary"
                            onClick={() => setEnabled(false)}
                        >
                            Tutup peta jalan
                        </button>
                    </div>
                    {failed ? (
                        <p role="status">
                            Peta jalan gagal atau belum lengkap. Diagram titik
                            tetap tersedia; ini bukan bukti keberhasilan
                            check-in.
                        </p>
                    ) : (
                        !ready && <p role="status">Memuat peta jalan…</p>
                    )}
                </>
            )}
            <small>
                ©{" "}
                <a
                    href="https://www.openstreetmap.org/copyright"
                    target="_blank"
                    rel="noreferrer"
                >
                    OpenStreetMap contributors
                </a>{" "}
                ·{" "}
                <a
                    href="https://www.openstreetmap.org/fixthemap"
                    target="_blank"
                    rel="noreferrer"
                >
                    Laporkan masalah peta
                </a>
            </small>
        </section>
    );
}
